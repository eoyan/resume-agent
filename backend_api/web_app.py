from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from ai_engine.agent_service import PersonaAutoFillAgent
from ai_engine.ollama_client import OllamaClient, OllamaClientError
from data_layer.document_parser import DocumentParseError, DocumentParser
from data_layer.profile_utils import DEFAULT_PROFILE_TEMPLATE, normalize_profile_payload
from data_layer.repository import PersonaRepository
from data_layer.result_exporter import ResultExportError, ResultExporter


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend_ui"
DATA_DIR = PROJECT_ROOT / "data_layer"
RUNTIME_STORAGE_DIR = DATA_DIR / "runtime_storage"
UPLOADS_DIR = RUNTIME_STORAGE_DIR / "uploads"
GENERATED_DIR = RUNTIME_STORAGE_DIR / "generated"
SEED_PATH = DATA_DIR / "seed" / "my_info_data.json"
DB_PATH = RUNTIME_STORAGE_DIR / "persona.db"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MODEL_NAME = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "600"))

app = Flask(
    __name__,
    template_folder=str(FRONTEND_DIR / "templates"),
    static_folder=str(FRONTEND_DIR / "static"),
)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
app.config["JSON_AS_ASCII"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.jinja_env.auto_reload = True

repository = PersonaRepository(DB_PATH)
document_parser = DocumentParser()
result_exporter = ResultExporter(GENERATED_DIR)
ollama_client = OllamaClient(
    model=DEFAULT_MODEL_NAME,
    base_url=OLLAMA_BASE_URL,
    timeout=OLLAMA_TIMEOUT,
)
persona_agent = PersonaAutoFillAgent(ollama_client)

UPLOAD_JOBS: Dict[str, Dict[str, Any]] = {}
UPLOAD_JOBS_LOCK = threading.Lock()

MODEL_PRESETS = {
    "qwen2.5:3b": {
        "label": "구체적 응답",
        "description": "속도는 느리지만 문항 해석과 답변 구성이 더 자세합니다.",
        "tier": "detailed",
    },
    "qwen2.5:1.5b": {
        "label": "표준",
        "description": "속도와 답변 품질의 균형을 맞춘 기본 선택입니다.",
        "tier": "standard",
    },
    "qwen2.5:0.5b": {
        "label": "빠른 응답",
        "description": "속도는 빠르지만 답변은 더 짧고 단순할 수 있습니다.",
        "tier": "fast",
    },
}


class UploadWorkflowError(RuntimeError):
    def __init__(self, code: str, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_seed_profile() -> None:
    if repository.get_profile() is not None:
        return
    if not SEED_PATH.exists():
        repository.save_profile(DEFAULT_PROFILE_TEMPLATE, source="empty")
        return
    raw = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    repository.save_profile(normalize_profile_payload(raw), source="seed")


def serialize_state() -> dict:
    profile = repository.get_profile() or DEFAULT_PROFILE_TEMPLATE
    llm_health = ollama_client.health()
    return {
        "profile": profile,
        "documents": repository.list_documents(limit=8),
        "runs": repository.list_autofill_runs(limit=8),
        "llm": {
            **llm_health,
            "model_options": build_model_options(llm_health.get("models", [])),
        },
    }


def build_model_options(installed_models: list[str]) -> list[dict]:
    options = []
    ordered_names = ["qwen2.5:3b", "qwen2.5:1.5b", "qwen2.5:0.5b"]
    remaining_names = sorted(
        name for name in installed_models
        if name not in ordered_names
    )

    for name in [*ordered_names, *remaining_names]:
        if name not in installed_models:
            continue
        preset = MODEL_PRESETS.get(
            name,
            {
                "label": "로컬 모델",
                "description": "Ollama에 설치된 로컬 모델입니다.",
                "tier": "custom",
            },
        )
        options.append(
            {
                "name": name,
                "label": preset["label"],
                "description": preset["description"],
                "tier": preset["tier"],
                "selected": name == ollama_client.model,
            }
        )

    return options


def asset_version(filename: str) -> int:
    path = FRONTEND_DIR / "static" / filename
    if path.exists():
        return int(path.stat().st_mtime)
    return 0


def estimate_total_seconds(extension: str) -> int:
    return {
        ".txt": 10,
        ".md": 10,
        ".json": 10,
        ".docx": 24,
        ".pdf": 40,
    }.get(extension.lower(), 25)


def extract_live_preview_fields(text: str, limit: int = 16) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    seen: set[str] = set()

    for raw_line in text.splitlines():
        line = " ".join(raw_line.strip().split())
        if not line or line.startswith("[PAGE "):
            continue

        candidates = [line]
        if "|" in line:
            candidates.extend(part.strip() for part in line.split("|"))

        for candidate in candidates:
            label = candidate.strip(" _-·")
            normalized = re.sub(r"[^0-9a-zA-Z가-힣]", "", label.lower())
            if not normalized or normalized in seen:
                continue
            if not looks_like_form_field(label):
                continue

            seen.add(normalized)
            fields.append(
                {
                    "label": label[:120],
                    "status": "waiting",
                }
            )
            if len(fields) >= limit:
                return fields

    return fields


def looks_like_form_field(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) < 2 or len(text) > 140:
        return False

    visible = [char for char in text if not char.isspace()]
    if not visible:
        return False
    punctuation_ratio = sum(1 for char in visible if char in "_-=[]()|.:,/") / len(visible)
    if punctuation_ratio > 0.65:
        return False

    if re.match(r"^\d+[\).]", text):
        return True
    if text.endswith("?"):
        return True

    keywords = [
        "이름",
        "생년월일",
        "나이",
        "이메일",
        "전화번호",
        "주소",
        "희망직무",
        "지원직무",
        "취미",
        "기술스택",
        "자격증",
        "경력",
        "학력",
        "대학교",
        "전공",
        "학점",
        "졸업",
        "자기소개",
        "소개",
        "강점",
        "경험",
        "프로젝트",
        "지원 동기",
        "지원동기",
        "입사 후 포부",
        "입사후포부",
        "작성해 주세요",
        "작성해주세요",
    ]
    return any(keyword in text for keyword in keywords)


def prepare_upload_request() -> Dict[str, Any]:
    profile = repository.get_profile()
    if profile is None:
        raise UploadWorkflowError("profile_not_found", "저장된 프로필이 없습니다.", 400)

    uploaded_file = request.files.get("file")
    instruction = (request.form.get("instruction") or "").strip()
    if uploaded_file is None or uploaded_file.filename is None or not uploaded_file.filename.strip():
        raise UploadWorkflowError("file_required", "업로드할 파일을 선택하세요.", 400)

    original_name = uploaded_file.filename.strip()
    safe_name = secure_filename(original_name) or "uploaded_document"
    extension = Path(original_name).suffix.lower()
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    stored_path = UPLOADS_DIR / stored_name
    uploaded_file.save(stored_path)

    return {
        "profile": profile,
        "instruction": instruction,
        "original_name": original_name,
        "extension": extension or "",
        "mime_type": uploaded_file.mimetype or "",
        "stored_name": stored_name,
        "stored_path": stored_path,
    }


def build_upload_response(
    *,
    document: Dict[str, Any],
    autofill_result: Dict[str, Any],
    download_files: list[dict[str, Any]],
    run: Dict[str, Any],
    download_error: Optional[str] = None,
) -> Dict[str, Any]:
    response_payload = {
        "message": "문서를 분석하고 자동 작성 초안을 생성했습니다.",
        "document": {
            "id": document["id"],
            "original_name": document["original_name"],
            "created_at": document["created_at"],
            "preview": document_parser.preview(document["extracted_text"]),
            "character_count": len(document["extracted_text"]),
            "extension": document["extension"],
        },
        "autofill_summary": {
            "document_type": autofill_result.get("document_type", "미분류 문서"),
            "summary": autofill_result.get("summary", "문서 요약이 생성되지 않았습니다."),
            "answer_count": len(autofill_result.get("answers", [])),
            "missing_count": len(autofill_result.get("missing_information", [])),
        },
        "downloads": download_files,
        "autofill_result": {
            "detected_sections": autofill_result.get("detected_sections", []),
            "answers": autofill_result.get("answers", []),
            "missing_information": autofill_result.get("missing_information", []),
            "rendered_draft": autofill_result.get("rendered_draft", ""),
        },
        "run": run,
    }
    if download_error:
        response_payload["download_error"] = download_error
    return response_payload


def execute_upload_workflow(
    *,
    profile: Dict[str, Any],
    instruction: str,
    original_name: str,
    extension: str,
    mime_type: str,
    stored_name: str,
    stored_path: Path,
    progress_callback: Optional[Callable[[int, str, str, str, Optional[Dict[str, Any]]], None]] = None,
) -> Dict[str, Any]:
    def emit(
        progress: int,
        stage_code: str,
        stage_label: str,
        message: str,
        live_preview: Optional[Dict[str, Any]] = None,
    ) -> None:
        if progress_callback:
            progress_callback(progress, stage_code, stage_label, message, live_preview)

    emit(16, "parse_document", "문서 텍스트 추출 중", "업로드한 문서의 텍스트와 레이아웃을 읽고 있습니다.")
    try:
        extracted_text = document_parser.extract_text(stored_path)
    except (DocumentParseError, json.JSONDecodeError) as error:
        stored_path.unlink(missing_ok=True)
        raise UploadWorkflowError("document_parse_failed", str(error), 400) from error

    if not extracted_text.strip():
        stored_path.unlink(missing_ok=True)
        raise UploadWorkflowError("document_empty", "문서에서 읽을 수 있는 텍스트가 없습니다.", 400)

    emit(34, "store_document", "문서 저장 중", "추출된 문서 내용을 로컬 저장소에 기록하고 있습니다.")
    document = repository.save_document(
        original_name=original_name,
        stored_name=stored_name,
        mime_type=mime_type,
        extension=extension,
        extracted_text=extracted_text,
    )

    emit(
        42,
        "generate_ai",
        "AI 답변 생성 대기 중",
        "문서 원문을 읽었습니다. 이제 AI가 채울 항목을 분석합니다.",
        {
            "phase": "document_ready",
            "document": {
                "original_name": original_name,
                "extension": extension,
                "character_count": len(extracted_text),
                "preview": document_parser.preview(extracted_text, limit=3200),
                "fields": extract_live_preview_fields(extracted_text),
            },
        },
    )

    emit(58, "generate_ai", "AI 답변 생성 중", "로컬 AI가 문항을 해석하고 답변 초안을 작성하고 있습니다.")
    try:
        autofill_result = persona_agent.autofill_document(
            profile=profile,
            document_name=original_name,
            document_text=extracted_text,
            instruction=instruction,
        )
    except OllamaClientError as error:
        raise UploadWorkflowError("ollama_request_failed", str(error), 502) from error

    emit(84, "export_result", "결과 문서 생성 중", "원본 PDF 또는 다운로드 문서를 정리하고 있습니다.")
    download_files = []
    download_error = None
    try:
        download_files = result_exporter.export_autofill_result(
            original_name=original_name,
            profile=profile,
            autofill_result=autofill_result,
            source_document_path=stored_path,
        )
    except ResultExportError as error:
        download_error = str(error)

    emit(94, "save_history", "실행 기록 저장 중", "자동 작성 결과를 로컬 DB에 저장하고 있습니다.")
    run_payload = dict(autofill_result)
    if download_files:
        run_payload["downloads"] = download_files
    run = repository.save_autofill_run(document["id"], instruction, run_payload)

    return build_upload_response(
        document=document,
        autofill_result=autofill_result,
        download_files=download_files,
        run=run,
        download_error=download_error,
    )


def create_upload_job(original_name: str, extension: str) -> str:
    job_id = uuid.uuid4().hex
    created_ts = time.time()
    job = {
        "job_id": job_id,
        "status": "queued",
        "progress": 6,
        "stage_code": "queued",
        "stage_label": "작업 대기 중",
        "message": "서버에 파일을 저장했습니다. 잠시 후 처리를 시작합니다.",
        "original_name": original_name,
        "extension": extension,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "created_ts": created_ts,
        "started_ts": created_ts,
        "estimated_total_seconds": estimate_total_seconds(extension),
    }
    with UPLOAD_JOBS_LOCK:
        UPLOAD_JOBS[job_id] = job
    return job_id


def update_upload_job(job_id: str, **updates: Any) -> Dict[str, Any]:
    with UPLOAD_JOBS_LOCK:
        job = UPLOAD_JOBS[job_id]
        job.update(updates)
        job["updated_at"] = utc_now_iso()
        return dict(job)


def get_upload_job(job_id: str) -> Optional[Dict[str, Any]]:
    with UPLOAD_JOBS_LOCK:
        job = UPLOAD_JOBS.get(job_id)
        return dict(job) if job is not None else None


def serialize_upload_job(job: Dict[str, Any]) -> Dict[str, Any]:
    base_ts = float(job.get("started_ts") or job.get("created_ts") or time.time())
    end_ts = float(job.get("finished_ts") or time.time())
    elapsed_seconds = round(max(0.0, end_ts - base_ts), 1)

    estimated_total = int(job.get("estimated_total_seconds") or 0)
    estimated_remaining = None
    if job.get("status") in {"queued", "running"} and estimated_total > 0:
        remaining_value = int(round(estimated_total - elapsed_seconds))
        estimated_remaining = remaining_value if remaining_value > 0 else None

    payload = {
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": int(job.get("progress", 0)),
        "stage_code": job.get("stage_code", "queued"),
        "stage_label": job.get("stage_label", "대기 중"),
        "message": job.get("message", ""),
        "original_name": job.get("original_name", ""),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "completed_at": job.get("completed_at"),
        "elapsed_seconds": elapsed_seconds,
        "estimated_total_seconds": estimated_total or None,
        "estimated_remaining_seconds": estimated_remaining,
    }
    if "result" in job:
        payload["result"] = job["result"]
    if "live_preview" in job:
        payload["live_preview"] = job["live_preview"]
    if "error" in job:
        payload["error"] = job["error"]
    if "detail" in job:
        payload["detail"] = job["detail"]
    return payload


def run_upload_job(job_id: str, payload: Dict[str, Any]) -> None:
    update_upload_job(
        job_id,
        status="running",
        stage_code="parse_document",
        stage_label="문서 텍스트 추출 중",
        message="업로드한 문서의 텍스트를 읽고 있습니다.",
        progress=12,
        started_ts=time.time(),
    )

    def callback(
        progress: int,
        stage_code: str,
        stage_label: str,
        message: str,
        live_preview: Optional[Dict[str, Any]] = None,
    ) -> None:
        updates: Dict[str, Any] = {
            "status": "running",
            "progress": progress,
            "stage_code": stage_code,
            "stage_label": stage_label,
            "message": message,
        }
        if live_preview is not None:
            updates["live_preview"] = live_preview
        update_upload_job(job_id, **updates)

    try:
        result = execute_upload_workflow(progress_callback=callback, **payload)
    except UploadWorkflowError as error:
        update_upload_job(
            job_id,
            status="failed",
            stage_code="failed",
            stage_label="작업 실패",
            message="문서 처리에 실패했습니다.",
            error=error.code,
            detail=error.detail,
            completed_at=utc_now_iso(),
            finished_ts=time.time(),
        )
        return
    except Exception as error:
        update_upload_job(
            job_id,
            status="failed",
            stage_code="failed",
            stage_label="작업 실패",
            message="예상하지 못한 오류가 발생했습니다.",
            error="internal_error",
            detail=str(error),
            completed_at=utc_now_iso(),
            finished_ts=time.time(),
        )
        return

    update_upload_job(
        job_id,
        status="completed",
        progress=100,
        stage_code="completed",
        stage_label="완료",
        message=result["message"],
        result=result,
        completed_at=utc_now_iso(),
        finished_ts=time.time(),
    )


ensure_seed_profile()


@app.get("/")
def index():
    return render_template(
        "index.html",
        model_name=ollama_client.model,
        style_version=asset_version("style.css"),
        app_js_version=asset_version("app.js"),
    )


@app.get("/api/state")
def get_state():
    return jsonify(serialize_state())


@app.post("/api/llm/model")
def select_llm_model():
    payload = request.get_json(silent=True) or {}
    model = str(payload.get("model") or "").strip()
    if not model:
        return jsonify({"error": "model_required"}), 400

    health = ollama_client.health()
    installed_models = health.get("models", [])
    if model not in installed_models:
        return jsonify(
            {
                "error": "model_not_installed",
                "detail": f"{model} 모델이 로컬 Ollama에 설치되어 있지 않습니다.",
                "models": installed_models,
            }
        ), 400

    ollama_client.set_model(model)
    return jsonify(serialize_state())


@app.get("/api/downloads/<path:stored_name>")
def download_generated_file(stored_name: str):
    return send_from_directory(GENERATED_DIR, stored_name, as_attachment=True)


@app.post("/api/profile/save")
def save_profile():
    payload = request.get_json(silent=True) or {}
    profile = normalize_profile_payload(payload.get("profile"))
    result = repository.save_profile(profile, source="manual")
    return jsonify(
        {
            "message": "프로필이 로컬 DB에 저장되었습니다.",
            "profile": result["profile"],
            "updated_at": result["updated_at"],
        }
    )


@app.post("/api/profile/load-seed")
def load_seed_profile():
    if not SEED_PATH.exists():
        return jsonify({"error": "seed_profile_not_found"}), 404

    raw = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    result = repository.save_profile(normalize_profile_payload(raw), source="seed")
    return jsonify(
        {
            "message": "샘플 프로필을 불러왔습니다.",
            "profile": result["profile"],
            "updated_at": result["updated_at"],
        }
    )


@app.post("/api/forms/upload-and-fill/start")
def start_upload_and_fill():
    try:
        payload = prepare_upload_request()
    except UploadWorkflowError as error:
        return jsonify({"error": error.code, "detail": error.detail}), error.status_code

    job_id = create_upload_job(payload["original_name"], payload["extension"])
    worker = threading.Thread(target=run_upload_job, args=(job_id, payload), daemon=True)
    worker.start()
    job = get_upload_job(job_id)
    return jsonify(serialize_upload_job(job or {"job_id": job_id, "status": "queued"})), 202


@app.get("/api/forms/upload-and-fill/jobs/<job_id>")
def get_upload_and_fill_job(job_id: str):
    job = get_upload_job(job_id)
    if job is None:
        return jsonify({"error": "job_not_found"}), 404
    return jsonify(serialize_upload_job(job))


@app.post("/api/forms/upload-and-fill")
def upload_and_fill():
    try:
        payload = prepare_upload_request()
        result = execute_upload_workflow(**payload)
    except UploadWorkflowError as error:
        return jsonify({"error": error.code, "detail": error.detail}), error.status_code
    return jsonify(result)


@app.post("/api/chat")
def chat_with_agent():
    profile = repository.get_profile()
    if profile is None:
        return jsonify({"error": "profile_not_found"}), 400

    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message_required"}), 400

    try:
        answer = persona_agent.answer_question(
            profile=profile,
            user_message=message,
        )
    except OllamaClientError as error:
        return jsonify({"error": "ollama_request_failed", "detail": str(error)}), 502

    return jsonify({"message": answer})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
