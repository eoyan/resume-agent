# 디지털 페르소나 문서 자동화 시스템 정리

## 1. 프로젝트 한 줄 설명
사용자 프로필을 로컬 DB에 저장하고, 업로드한 지원서/이력서/PDF/DOCX 문서를 로컬 LLM(Ollama)로 해석하여 자동입력 초안을 생성하고 다운로드 가능한 DOCX로 내보내는 시스템이다.

---

## 2. 전체 실행 흐름

### 2-1. 실행 시작점
- 실행 파일: `app.py`
- 역할: Flask 서버 시작
- 실제 앱 본체 import: `backend_api/web_app.py`

### 2-2. 사용자 기준 실행 흐름
1. 사용자가 브라우저에서 `/` 접속
2. Flask가 `frontend_ui/templates/index.html` 렌더링
3. 프론트 JS(`frontend_ui/static/app.js`)가 `/api/state` 호출
4. 백엔드가 현재 프로필, 최근 문서, 최근 실행 기록, LLM 상태를 반환
5. 사용자가 프로필 입력 후 `/api/profile/save`로 로컬 DB 저장
6. 사용자가 PDF/DOCX/TXT/JSON 문서를 업로드
7. 백엔드가 업로드 파일을 `data_layer/runtime_storage/uploads/`에 저장
8. `DocumentParser`가 문서를 텍스트로 추출
9. 추출 텍스트와 저장된 프로필을 `PersonaAutoFillAgent`에 전달
10. `OllamaClient`가 로컬 Ollama API(`/api/chat`) 호출
11. 모델 응답을 정규화해서 `answers`, `missing_information`, `rendered_draft` 구조로 변환
12. `ResultExporter`가 채워진 결과 DOCX를 `data_layer/runtime_storage/generated/`에 생성
13. 실행 결과를 SQLite DB(`persona.db`)에 저장
14. 프론트가 아래 정보를 화면에 표시
    - 채워진 결과 미리보기
    - 항목별 답변 목록
    - 추가 확인 필요 항목
    - 다운로드 버튼
    - 에이전트 입력용 문서 미리보기

### 2-3. 내부 호출 흐름
```text
app.py
  -> backend_api/web_app.py
      -> PersonaRepository
      -> DocumentParser
      -> PersonaAutoFillAgent
          -> OllamaClient
      -> ResultExporter
      -> frontend_ui/templates/index.html
      -> frontend_ui/static/app.js
```

---

## 3. 사용 API 정리

### 3-1. 내부 Flask API
| Method | Path | 역할 | 호출 주체 |
|---|---|---|---|
| GET | `/` | 메인 페이지 렌더링 | 브라우저 |
| GET | `/api/state` | 프로필, 문서 목록, 실행 목록, LLM 상태 조회 | `app.js` 초기 로드 |
| POST | `/api/profile/save` | 입력한 프로필을 로컬 DB에 저장 | `app.js` |
| POST | `/api/profile/load-seed` | 샘플 프로필 JSON 로드 | `app.js` |
| POST | `/api/forms/upload-and-fill` | 문서 업로드, 파싱, 자동작성, 결과 저장, 다운로드 정보 반환 | `app.js` |
| GET | `/api/downloads/<stored_name>` | 생성된 DOCX 다운로드 | 브라우저 |
| POST | `/api/chat` | 저장 프로필 기반 질의 응답 | 현재 UI에서는 미사용, 확장용 |

### 3-2. 외부 API
| 대상 | URL | 용도 |
|---|---|---|
| Ollama | `http://127.0.0.1:11434/api/tags` | 모델 설치/상태 확인 |
| Ollama | `http://127.0.0.1:11434/api/chat` | 자동작성 및 질의 응답 |

### 3-3. 현재 핵심 API
현재 실제 메인 기능은 사실상 아래 3개다.
- `/api/state`
- `/api/profile/save`
- `/api/forms/upload-and-fill`

---

## 4. 컨텍스트(DB) 관리 방식

### 4-1. 로컬 컨텍스트의 의미
이 시스템의 컨텍스트는 크게 3개다.
1. 사용자 프로필 컨텍스트
2. 업로드된 문서 컨텍스트
3. 자동작성 결과 컨텍스트

### 4-2. 저장 위치
- SQLite DB: `data_layer/runtime_storage/persona.db`
- 업로드 원본 파일: `data_layer/runtime_storage/uploads/`
- 생성된 결과 문서: `data_layer/runtime_storage/generated/`
- 초기 샘플 프로필: `data_layer/seed/my_info_data.json`

### 4-3. DB 스키마
#### `persona_profile`
- 사용자 프로필 1건만 저장하는 싱글톤 테이블
- `id = 1` 고정
- 컬럼
  - `payload_json`: 프로필 JSON 전체
  - `source`: `manual`, `seed`, `empty`
  - `updated_at`: 마지막 수정 시각

#### `documents`
- 업로드된 문서 메타데이터 저장
- 컬럼
  - `original_name`
  - `stored_name`
  - `mime_type`
  - `extension`
  - `extracted_text`
  - `created_at`

#### `autofill_runs`
- 자동작성 실행 기록 저장
- 컬럼
  - `document_id`
  - `instruction`
  - `result_json`
  - `created_at`

### 4-4. 컨텍스트 사용 방식
- 프로필은 항상 DB에서 읽어서 LLM 프롬프트에 포함된다.
- 업로드 문서는 텍스트로 추출된 뒤 LLM 프롬프트에 포함된다.
- 실행 결과는 DB에 JSON으로 저장된다.
- 즉, LLM 입력 컨텍스트는 `프로필 JSON + 문서 텍스트 + 추가 지시` 구조다.

---

## 5. 폴더 구조와 책임

```text
files-mentioned-by-the-user-agent/
├── app.py
├── backend_api/
│   └── web_app.py
├── ai_engine/
│   ├── agent_service.py
│   └── ollama_client.py
├── data_layer/
│   ├── repository.py
│   ├── profile_utils.py
│   ├── document_parser.py
│   ├── result_exporter.py
│   ├── seed/
│   │   └── my_info_data.json
│   ├── runtime_storage/
│   │   ├── persona.db
│   │   ├── uploads/
│   │   └── generated/
│   └── samples/
├── frontend_ui/
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── app.js
│       └── style.css
├── README.md
├── TEAM_STRUCTURE.md
└── requirements.txt
```

---

## 6. 파일별 기능 정리

### 6-1. `app.py`
- Flask 실행 진입점
- 실제 로직은 없고 `backend_api.web_app`의 `app`만 실행한다.

### 6-2. `backend_api/web_app.py`
- Flask 앱 본체
- 라우팅, 업로드, 파싱, AI 호출, DB 저장, 다운로드 응답까지 전부 연결
- 사실상 시스템의 메인 오케스트레이터

### 6-3. `ai_engine/agent_service.py`
- LLM에 전달할 프롬프트 구성
- 모델 응답을 시스템이 쓰기 좋은 구조로 정규화
- 자동작성 결과를 `answers / missing_information / rendered_draft` 형태로 맞춤

### 6-4. `ai_engine/ollama_client.py`
- 로컬 Ollama 서버와 HTTP 통신
- 모델 상태 확인, `/api/chat` 요청, JSON 파싱 처리 담당

### 6-5. `data_layer/repository.py`
- SQLite 접근 계층
- 프로필 저장/조회, 문서 저장/조회, 자동작성 결과 기록 저장/조회 담당

### 6-6. `data_layer/profile_utils.py`
- 입력된 프로필 데이터를 정규화
- 문자열, 배열, 학력 중첩 구조를 표준 형태로 맞춤

### 6-7. `data_layer/document_parser.py`
- 업로드 파일의 텍스트 추출 담당
- 지원 형식: `txt`, `md`, `json`, `docx`, `pdf`
- PDF는 페이지 단위 텍스트 추출 후 정리
- 프리뷰용 요약 텍스트도 생성

### 6-8. `data_layer/result_exporter.py`
- AI 자동작성 결과를 DOCX 파일로 렌더링
- 최종 다운로드 가능한 문서를 생성

### 6-9. `frontend_ui/templates/index.html`
- 메인 페이지 DOM 구조
- 프로필 입력 영역
- 문서 업로드 영역
- 채워진 결과 미리보기
- 원문 미리보기
- 다운로드 버튼 영역

### 6-10. `frontend_ui/static/app.js`
- 프론트엔드 상태 관리 및 API 호출 담당
- 프로필 저장, 샘플 로드, 업로드 요청, 화면 렌더링 처리

### 6-11. `frontend_ui/static/style.css`
- 전체 UI 스타일 정의

---

## 7. 함수별 기능 정리

### 7-1. `backend_api/web_app.py`
| 함수 | 역할 |
|---|---|
| `ensure_seed_profile()` | DB에 프로필이 없으면 seed 또는 빈 템플릿으로 초기화 |
| `serialize_state()` | 초기 화면에 필요한 state JSON 생성 |
| `asset_version()` | 정적 파일 cache busting용 버전값 생성 |
| `index()` | 메인 HTML 렌더링 |
| `get_state()` | `/api/state` 응답 |
| `download_generated_file()` | 생성된 DOCX 파일 다운로드 |
| `save_profile()` | 프로필 JSON 정규화 후 DB 저장 |
| `load_seed_profile()` | 샘플 프로필 로드 후 저장 |
| `upload_and_fill()` | 업로드 저장 -> 문서 파싱 -> LLM 호출 -> 결과 DOCX 생성 -> DB 기록 -> 응답 반환 |
| `chat_with_agent()` | 저장 프로필 기반 단문 질의 응답 |

### 7-2. `ai_engine/agent_service.py`
| 함수 | 역할 |
|---|---|
| `autofill_document()` | 자동작성 전체 실행 진입점 |
| `answer_question()` | 자유 질의 응답 처리 |
| `_build_autofill_prompt()` | 자동작성용 system/user prompt 구성 |
| `_truncate_document()` | 긴 문서를 LLM 입력 길이에 맞게 축약 |
| `_compact_document_text()` | 문서 노이즈 제거 및 중복 라인 축소 |
| `_normalize_autofill_result()` | 모델 JSON 응답을 시스템 표준 구조로 정리 |
| `_build_fallback_draft()` | 모델이 `rendered_draft`를 안 주면 fallback 초안 생성 |

### 7-3. `ai_engine/ollama_client.py`
| 함수 | 역할 |
|---|---|
| `list_models()` | 설치된 모델 목록 조회 |
| `health()` | Ollama 연결 여부 및 모델 설치 여부 확인 |
| `chat()` | Ollama `/api/chat` 호출 |
| `_parse_json_content()` | 모델 응답에서 JSON 객체 파싱 |
| `_extract_outer_json()` | 텍스트 내 바깥 JSON 블록 추출 |

### 7-4. `data_layer/repository.py`
| 함수 | 역할 |
|---|---|
| `utc_now_iso()` | UTC ISO timestamp 생성 |
| `_connect()` | SQLite 연결 생성 |
| `_init_db()` | 필요한 테이블 초기화 |
| `get_profile()` | 현재 프로필 1건 조회 |
| `save_profile()` | 프로필 저장 또는 갱신 |
| `save_document()` | 업로드 문서 메타데이터 저장 |
| `get_document()` | 문서 1건 조회 |
| `list_documents()` | 최근 문서 목록 조회 |
| `save_autofill_run()` | 자동작성 실행 결과 저장 |
| `get_autofill_run()` | 실행 결과 1건 조회 |
| `list_autofill_runs()` | 최근 실행 목록 조회 |

### 7-5. `data_layer/profile_utils.py`
| 함수 | 역할 |
|---|---|
| `_to_clean_string()` | 값을 문자열로 정리 |
| `_to_clean_list()` | 배열/콤마 구분 문자열을 리스트로 정리 |
| `normalize_profile_payload()` | 프로필 구조를 표준 템플릿에 맞게 정규화 |

### 7-6. `data_layer/document_parser.py`
| 함수 | 역할 |
|---|---|
| `extract_text()` | 확장자별 문서 텍스트 추출 진입점 |
| `preview()` | 화면용 미리보기 텍스트 생성 |
| `_extract_docx()` | DOCX 본문/표 텍스트 추출 |
| `_extract_pdf()` | PDF 페이지별 텍스트 추출 |
| `_extract_pdf_page_text()` | layout 추출 우선, fallback 추출 |
| `_clean_text()` | 줄바꿈/공백 정리 |
| `_clean_line()` | 한 줄 단위 공백 정리 |

### 7-7. `data_layer/result_exporter.py`
| 함수 | 역할 |
|---|---|
| `export_autofill_result()` | DOCX 생성 후 다운로드 메타데이터 반환 |
| `_build_docx()` | 실제 DOCX 문서 내용 작성 |
| `_safe_stem()` | 안전한 파일명 생성 |

### 7-8. `frontend_ui/static/app.js`
| 함수 | 역할 |
|---|---|
| `splitCommaValues()` | 콤마 구분 입력값을 배열로 변환 |
| `collectProfileForm()` | 폼 값을 profile JSON으로 수집 |
| `populateProfileForm()` | profile JSON을 화면 폼에 채움 |
| `renderState()` | 초기 상태와 LLM 상태 렌더링 |
| `renderDownloadButtons()` | 다운로드 버튼 렌더링 |
| `renderAutofillResult()` | 채워진 결과, 항목별 답변, 누락 항목 렌더링 |
| `fetchState()` | `/api/state` 호출 |
| `saveProfile()` | `/api/profile/save` 호출 |
| `loadSeedProfile()` | `/api/profile/load-seed` 호출 |
| `submitUpload()` | `/api/forms/upload-and-fill` 호출 후 결과 화면 반영 |

---

## 8. 현재 시스템의 핵심 데이터 구조

### 8-1. 프로필 JSON
```json
{
  "이름": "",
  "생년월일": "",
  "나이": "",
  "취미": [],
  "경력": "",
  "기술스택": [],
  "이메일": "",
  "전화번호": "",
  "주소": "",
  "학력": {
    "대학교": "",
    "전공": "",
    "학점": "",
    "졸업년도": ""
  },
  "자격증": [],
  "희망직무": "",
  "추가메모": ""
}
```

### 8-2. 자동작성 결과 JSON
```json
{
  "document_type": "이력서",
  "summary": "문서 요약",
  "detected_sections": ["기본 정보", "자기소개"],
  "answers": [
    {
      "section": "기본 정보",
      "question": "이름",
      "field_key": "name",
      "answer": "홍길동",
      "confidence": "high",
      "source": ["이름"],
      "reason": "프로필 정보 사용"
    }
  ],
  "missing_information": [
    {
      "question": "포트폴리오 링크",
      "reason": "프로필에 없음"
    }
  ],
  "rendered_draft": "사람이 바로 복붙 가능한 최종 초안"
}
```

