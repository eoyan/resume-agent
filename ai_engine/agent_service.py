from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ai_engine.ollama_client import OllamaClient


class PersonaAutoFillAgent:
    def __init__(self, llm_client: OllamaClient) -> None:
        self.llm_client = llm_client

    def autofill_document(
        self,
        *,
        profile: Dict[str, Any],
        document_name: str,
        document_text: str,
        instruction: str = "",
    ) -> Dict[str, Any]:
        prompt = self._build_autofill_prompt(
            profile=profile,
            document_name=document_name,
            document_text=document_text,
            instruction=instruction,
        )
        result = self.llm_client.chat(prompt, temperature=0.1, format_json=True)
        return self._normalize_autofill_result(result, document_name)

    def answer_question(
        self,
        *,
        profile: Dict[str, Any],
        user_message: str,
        document_context: Optional[str] = None,
    ) -> str:
        system_prompt = (
            "너는 로컬에 저장된 디지털 페르소나 기반 문서 작성 에이전트다.\n"
            "반드시 한국어로 답하고, 제공된 프로필 정보 밖의 사실은 단정하지 마라.\n"
            "사용자가 지원서 문항, 자기소개, 요약문, 이메일 초안을 요청하면 프로필을 근거로 작성하라.\n"
            "정보가 부족하면 부족한 항목을 먼저 짚고, 필요한 경우 대체 문장을 제시하라."
        )
        content_parts = [
            "프로필 JSON:",
            json.dumps(profile, ensure_ascii=False, indent=2),
            "",
            "사용자 요청:",
            user_message.strip(),
        ]
        if document_context:
            content_parts.extend(["", "참고 문서:", self._truncate_document(document_context)])

        response = self.llm_client.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n".join(content_parts)},
            ],
            temperature=0.3,
            format_json=False,
        )
        if not isinstance(response, str):
            raise RuntimeError("문답 응답 형식이 올바르지 않습니다.")
        return response.strip()

    def _build_autofill_prompt(
        self,
        *,
        profile: Dict[str, Any],
        document_name: str,
        document_text: str,
        instruction: str,
    ) -> List[Dict[str, str]]:
        system_prompt = """
너는 취업 지원서와 각종 입력 양식을 자동 작성하는 로컬 AI 에이전트다.
반드시 한국어로 동작하고, 제공된 프로필 정보만 사용해야 한다.
프로필에 없는 사실은 절대 지어내지 마라.

해야 할 일:
1. 업로드된 문서에서 입력 항목, 질문, 서술 문항을 식별한다.
2. 프로필 JSON을 근거로 각 항목에 들어갈 답변 초안을 작성한다.
3. 정보가 없는 항목은 빈 답변 대신 missing_information에 따로 모은다.
4. 최종 결과는 반드시 하나의 JSON 객체만 반환한다.

JSON 스키마:
{
  "document_type": "문서 유형",
  "summary": "문서 요약",
  "detected_sections": ["섹션1", "섹션2"],
  "answers": [
    {
      "section": "섹션명",
      "question": "질문 또는 필드명",
      "field_key": "snake_case_key",
      "answer": "자동 작성 결과",
      "confidence": "high|medium|low",
      "source": ["프로필 근거 키1", "프로필 근거 키2"],
      "reason": "왜 이런 답변을 채웠는지"
    }
  ],
  "missing_information": [
    {
      "question": "누락된 항목",
      "reason": "프로필에 정보가 없는 이유"
    }
  ],
  "rendered_draft": "질문과 답변을 사람이 바로 복붙할 수 있게 정리한 최종 초안"
}
""".strip()

        user_prompt = "\n".join(
            [
                f"업로드 문서명: {document_name}",
                f"추가 지시: {instruction or '없음'}",
                "",
                "프로필 JSON:",
                json.dumps(profile, ensure_ascii=False, indent=2),
                "",
                "문서 원문:",
                self._truncate_document(document_text),
            ]
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _truncate_document(self, text: str, max_chars: int = 18000) -> str:
        cleaned = self._compact_document_text(text)
        max_chars = 7000
        if len(cleaned) <= max_chars:
            return cleaned
        head = cleaned[: int(max_chars * 0.75)]
        tail = cleaned[-int(max_chars * 0.25) :]
        return (
            head.rstrip()
            + "\n\n[중간 일부 생략]\n\n"
            + tail.lstrip()
        )

    def _compact_document_text(self, text: str) -> str:
        kept_lines: List[str] = []
        previous_line = None

        for raw_line in text.splitlines():
            line = " ".join(raw_line.strip().split())
            if not line:
                continue

            visible_chars = [char for char in line if not char.isspace()]
            if visible_chars:
                punctuation_ratio = sum(
                    1 for char in visible_chars if char in "_-=[]()|.:,/"
                ) / len(visible_chars)
                if punctuation_ratio > 0.7 and len(line) > 12:
                    continue

            if line == previous_line:
                continue

            kept_lines.append(line)
            previous_line = line

        return "\n".join(kept_lines)

    def _normalize_autofill_result(
        self, raw: Dict[str, Any], document_name: str
    ) -> Dict[str, Any]:
        answers: List[Dict[str, Any]] = []
        for item in raw.get("answers", []) if isinstance(raw.get("answers"), list) else []:
            if not isinstance(item, dict):
                continue
            answers.append(
                {
                    "section": str(item.get("section", "")).strip() or "기타",
                    "question": str(item.get("question", "")).strip(),
                    "field_key": str(item.get("field_key", "")).strip(),
                    "answer": str(item.get("answer", "")).strip(),
                    "confidence": str(item.get("confidence", "medium")).strip() or "medium",
                    "source": [
                        str(source).strip()
                        for source in item.get("source", [])
                        if str(source).strip()
                    ],
                    "reason": str(item.get("reason", "")).strip(),
                }
            )

        missing_information: List[Dict[str, str]] = []
        for item in raw.get("missing_information", []) if isinstance(raw.get("missing_information"), list) else []:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", "")).strip()
            reason = str(item.get("reason", "")).strip()
            if question or reason:
                missing_information.append(
                    {
                        "question": question,
                        "reason": reason,
                    }
                )

        rendered_draft = str(raw.get("rendered_draft", "")).strip()
        if not rendered_draft:
            rendered_draft = self._build_fallback_draft(answers, missing_information)

        return {
            "document_name": document_name,
            "document_type": str(raw.get("document_type", "")).strip() or "미분류 문서",
            "summary": str(raw.get("summary", "")).strip() or "문서 요약이 생성되지 않았습니다.",
            "detected_sections": [
                str(section).strip()
                for section in raw.get("detected_sections", [])
                if str(section).strip()
            ],
            "answers": answers,
            "missing_information": missing_information,
            "rendered_draft": rendered_draft,
        }

    def _build_fallback_draft(
        self,
        answers: List[Dict[str, Any]],
        missing_information: List[Dict[str, str]],
    ) -> str:
        lines: List[str] = []
        current_section = None
        for item in answers:
            section = item["section"]
            if section != current_section:
                current_section = section
                lines.append(f"[{section}]")
            lines.append(f"- {item['question']}: {item['answer']}")

        if missing_information:
            lines.append("")
            lines.append("[추가 확인 필요]")
            for item in missing_information:
                lines.append(f"- {item['question']}: {item['reason']}")
        return "\n".join(lines).strip()

