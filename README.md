# Digital Persona Autofill Agent

로컬 DB에 개인 정보를 저장하고, 업로드한 지원 양식을 로컬 Ollama 모델로 해석해 자동 작성 초안을 생성하는 Flask 앱이다.

## 포함 기능

- SQLite 기반 로컬 프로필 저장
- `my_info_data.json` 시드 데이터 자동 로드
- Ollama HTTP API(`http://127.0.0.1:11434`) 연동
- `txt`, `md`, `json`, `docx`, `pdf` 업로드 및 텍스트 추출
- 문항 추출 + 자동 작성 결과 + 누락 정보 표시
- 저장된 프로필 기반 AI 질의
- 업로드 문서 / 자동 작성 결과 이력 저장

## 실행

```bash
pip install -r requirements.txt
python3 app.py
```

브라우저에서 `http://127.0.0.1:5050` 접속.

## 전제 조건

- 로컬에 Ollama 서버가 실행 중이어야 한다.
- 기본 모델은 `qwen2.5:1.5b` 이다.
- `docx`, `pdf` 파싱에는 `python-docx`, `pypdf`가 필요하다.
- Codex 샌드박스 안에서 실행하면 localhost 접근 승인 절차가 필요할 수 있다.

## 주요 파일

- `app.py`: Flask 서버와 API 엔드포인트
- `agent.py`: 로컬 페르소나 자동 작성 에이전트
- `ollama_client.py`: Ollama HTTP API 호출
- `document_parser.py`: 업로드 문서 텍스트 추출
- `storage.py`: SQLite 저장소
- `profile_utils.py`: 프로필 정규화
