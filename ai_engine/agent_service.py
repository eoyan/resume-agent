from __future__ import annotations

import json
import re
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
        result = self.llm_client.chat(prompt, temperature=0.2, format_json=True)
        normalized = self._normalize_autofill_result(result, document_name)
        return self._ensure_narrative_answers(
            normalized,
            profile=profile,
            document_text=document_text,
        )

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
4. answers[].question에는 원문 필드명이나 서술형 문항 제목을 반드시 넣는다.
5. 서술형 문항은 3~5문장으로 작성하고, 근거-직무연결-성장계획이 드러나게 쓴다.
6. "관심과 기술적 능력이 있다", "적합하다고 생각한다"처럼 추상적인 한 줄 답변은 금지한다.
7. 답변 앞에 "지원 동기:", "주요 기술 또는 프로젝트 경험:" 같은 라벨을 붙이지 않는다.
8. 자기소개 문항은 이름, 생년월일, 주소, 전화번호, 이메일을 나열하지 말고 지원 직무와 연결된 소개로 작성한다.
9. 기술스택과 자격증은 참고 근거로만 쓰고, 키워드 목록처럼 나열하지 않는다.
10. 최종 결과는 반드시 하나의 JSON 객체만 반환한다.

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

    def _normalize_autofill_result(self, raw: Dict[str, Any], document_name: str) -> Dict[str, Any]:
        answers: List[Dict[str, Any]] = []
        for item in raw.get("answers", []) if isinstance(raw.get("answers"), list) else []:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", "")).strip()
            section = str(item.get("section", "")).strip()
            field_key = str(item.get("field_key", "")).strip()
            answers.append(
                {
                    "section": section or "기타",
                    "question": question or section or field_key,
                    "field_key": field_key,
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

    def _ensure_narrative_answers(
        self,
        result: Dict[str, Any],
        *,
        profile: Dict[str, Any],
        document_text: str,
    ) -> Dict[str, Any]:
        answers = result.get("answers", [])
        if not isinstance(answers, list):
            return result

        changed = False
        narrative_questions = self._extract_narrative_questions(document_text)

        for item in answers:
            if not isinstance(item, dict):
                continue
            question_text = " ".join(
                str(item.get(key, "")).strip()
                for key in ("question", "section", "field_key")
                if str(item.get(key, "")).strip()
            )
            kind = self._narrative_kind(question_text)
            if not kind:
                continue

            current = str(item.get("answer", "")).strip()
            if self._is_low_quality_narrative_answer(current, item):
                question = str(item.get("question", "")).strip()
                item["answer"] = self._build_fallback_narrative_answer(
                    question=question,
                    kind=kind,
                    profile=profile,
                )
                item["confidence"] = "medium"
                item["reason"] = "서술형 문항이 비어 있거나 품질 기준에 맞지 않아 프로필 기반 fallback으로 채웠습니다."
                changed = True

        existing_kinds = {
            self._narrative_kind(
                " ".join(
                    str(item.get(key, "")).strip()
                    for key in ("question", "section", "field_key")
                    if isinstance(item, dict) and str(item.get(key, "")).strip()
                )
            )
            for item in answers
            if isinstance(item, dict)
        }
        for question in narrative_questions:
            kind = self._narrative_kind(question)
            if not kind or kind in existing_kinds:
                continue
            answers.append(
                {
                    "section": "서술형",
                    "question": question,
                    "field_key": kind,
                    "answer": self._build_fallback_narrative_answer(
                        question=question,
                        kind=kind,
                        profile=profile,
                    ),
                    "confidence": "medium",
                    "source": ["희망직무", "기술스택", "학력", "추가메모"],
                    "reason": "문서의 서술형 문항을 감지해 프로필 기반 fallback으로 채웠습니다.",
                }
            )
            existing_kinds.add(kind)
            changed = True

        if changed:
            result["rendered_draft"] = self._build_fallback_draft(
                answers,
                result.get("missing_information", []),
            )
        return result

    def _extract_narrative_questions(self, document_text: str) -> List[str]:
        questions: List[str] = []
        seen: set[str] = set()
        for raw_line in str(document_text or "").splitlines():
            line = " ".join(raw_line.strip().split())
            if not line:
                continue
            match = re.match(r"^\d+[\).]\s*(.+)$", line)
            if not match:
                continue
            question = match.group(1).strip()
            if not self._narrative_kind(question):
                continue
            normalized = self._normalize_text_key(question)
            if normalized in seen:
                continue
            seen.add(normalized)
            questions.append(question)
        return questions

    def _build_fallback_narrative_answer(
        self,
        *,
        question: str,
        kind: str,
        profile: Dict[str, Any],
    ) -> str:
        role = str(profile.get("희망직무", "")).strip() or "지원 직무"
        education = profile.get("학력") if isinstance(profile.get("학력"), dict) else {}
        major = str(education.get("전공", "")).strip()
        university = str(education.get("대학교", "")).strip()
        skills = [str(value).strip() for value in profile.get("기술스택", []) if str(value).strip()]
        memo = str(profile.get("추가메모", "")).strip()

        skill_focus = ", ".join(skills[:3]) if skills else "직무 관련 기술"
        school_context = " ".join(part for part in [university, major] if part) or "전공 학습 과정"
        portfolio_note = " 공개 포트폴리오는 더 보강이 필요하지만," if "포트폴리오" in memo else ""

        if kind == "intro":
            return (
                f"저는 {role} 분야에서 사용자의 문제를 실제 기능으로 풀어내는 과정에 관심을 두고 성장해 왔습니다. "
                f"{school_context}을 바탕으로 개발의 기본기를 다졌고, {skill_focus}를 활용해 작은 기능이라도 직접 구현하고 개선하는 연습을 이어가고 있습니다. "
                f"아직 실무 경험은 많지 않지만, 모르는 부분을 빠르게 학습하고 결과물로 정리하려는 태도를 강점으로 삼고 있습니다. "
                f"앞으로도 맡은 기능의 목적을 이해하고 팀이 신뢰할 수 있는 결과물을 만드는 개발자가 되고 싶습니다."
            )
        if kind == "strength":
            return (
                f"{role} 직무와 관련한 제 강점은 학습한 기술을 단순히 아는 데서 멈추지 않고, 실제 화면과 기능 흐름으로 연결해 보려는 태도입니다. "
                f"{skill_focus}를 중심으로 구현 과정을 반복하며 요구사항을 작은 단위로 나누고, 동작 결과를 확인하면서 개선하는 습관을 길러 왔습니다. "
                f"또한 전공 과정에서 익힌 기본 지식을 바탕으로 문제의 원인을 찾고 정리하는 데 익숙해지고 있습니다. "
                f"이런 점을 바탕으로 입사 후에도 빠르게 업무 흐름을 익히고 팀의 개발 방식에 맞춰 성장하겠습니다."
            )
        if kind == "experience":
            return (
                f"가장 자신 있게 설명할 수 있는 경험은 {role}에 필요한 기술을 학습하며 기능 단위의 결과물로 정리해 온 과정입니다. "
                f"{portfolio_note} {skill_focus}를 활용해 화면 구성, 데이터 처리, 동작 흐름을 직접 구현해 보며 개발 과정에서 중요한 것은 완성뿐 아니라 구조를 이해하는 것이라는 점을 배웠습니다. "
                f"문제가 생겼을 때 원인을 나누어 확인하고, 다시 재현 가능한 방식으로 정리하는 연습도 함께 해 왔습니다. "
                f"앞으로는 이 경험을 더 구체적인 프로젝트 사례로 발전시켜 실무에서도 설명 가능한 역량으로 만들겠습니다."
            ).replace("  ", " ").strip()
        if kind == "motivation":
            return (
                f"{role} 직무에 지원한 이유는 제가 학습한 기술을 실제 사용자가 만나는 결과물로 연결하는 일에 매력을 느꼈기 때문입니다. "
                f"{school_context}에서 기초를 다지며 개발은 단순히 코드를 작성하는 일이 아니라 요구사항을 이해하고 더 나은 사용 경험으로 바꾸는 과정이라고 생각하게 되었습니다. "
                f"{skill_focus}를 중심으로 역량을 쌓아 온 만큼, 입사 후에는 작은 기능부터 안정적으로 완성하며 팀에 기여하고 싶습니다. "
                f"부족한 부분은 빠르게 배우고 기록하면서 실무에 맞는 개발자로 성장하겠습니다."
            )
        if kind == "future":
            return (
                f"입사 후에는 먼저 팀의 코드와 업무 프로세스를 정확히 이해하고, 맡은 기능을 안정적으로 완성하는 데 집중하겠습니다. "
                f"{role} 업무에서는 구현 능력뿐 아니라 문제를 재현하고 원인을 공유하며 함께 개선하는 태도가 중요하다고 생각합니다. "
                f"제가 쌓아 온 {skill_focus} 기반 역량을 바탕으로 작은 작업도 책임감 있게 마무리하고, 필요한 부분은 문서화하며 협업에 도움이 되는 구성원이 되겠습니다. "
                f"장기적으로는 사용자와 팀 모두에게 신뢰받는 개발자로 성장하고 싶습니다."
            )
        return (
            f"{role} 직무와 연결해 지금까지 쌓아 온 학습 경험과 태도를 바탕으로 답변드리겠습니다. "
            f"{skill_focus}를 중심으로 기본기를 다져 왔고, 부족한 부분은 프로젝트와 기록을 통해 계속 보완하고 있습니다. "
            f"입사 후에는 빠르게 배우고 꾸준히 개선하며 팀에 기여하겠습니다."
        )

    def _narrative_kind(self, text: str) -> str:
        normalized = self._normalize_text_key(text)
        if not normalized:
            return ""
        if self._is_non_narrative_key(normalized):
            return ""
        if any(keyword in normalized for keyword in ["입사후포부", "futureplan", "포부"]):
            return "future"
        if any(keyword in normalized for keyword in ["지원동기", "motivation", "동기"]):
            return "motivation"
        if any(keyword in normalized for keyword in ["강점", "strength"]):
            return "strength"
        if any(keyword in normalized for keyword in ["프로젝트", "경험", "experience"]):
            return "experience"
        if any(keyword in normalized for keyword in ["자기소개", "본인소개", "selfintroduction", "소개"]):
            return "intro"
        return ""

    def _is_non_narrative_key(self, normalized: str) -> bool:
        non_narrative_keywords = [
            "협업툴",
            "사용가능언어",
            "보유기술스택",
            "기술스택",
            "보유자격증",
            "관련자격증",
            "github",
            "블로그",
            "어학점수",
            "수상경력",
            "병역",
            "추가확인",
            "자기소개및서술형문항",
        ]
        return any(keyword in normalized for keyword in non_narrative_keywords)

    def _is_substantial_narrative_answer(self, answer: str) -> bool:
        text = " ".join(str(answer or "").split())
        if len(text) < 180:
            return False
        weak_phrases = [
            "적합하다고 생각합니다",
            "적합합니다",
            "기술적 능력이 있습니다",
            "열정과 기술적 능력",
            "다양한 언어를 사용하여",
            "프로젝트에 적응할 수 있는 능력",
            "디자인 기법을 활용하여",
            "기여한 경험과",
            "능력을 활용하여",
            "더욱 성공적인 결과를",
        ]
        return not any(phrase in text for phrase in weak_phrases)

    def _is_low_quality_narrative_answer(self, answer: str, item: Dict[str, Any]) -> bool:
        text = " ".join(str(answer or "").split())
        if self._is_echo_answer(text, item):
            return True
        if not self._is_substantial_narrative_answer(text):
            return True
        if self._has_question_label_prefix(text, item):
            return True
        if self._looks_like_keyword_dump(text):
            return True
        if self._is_intro_question(item) and self._contains_personal_info_dump(text):
            return True
        return False

    def _is_echo_answer(self, answer: str, item: Dict[str, Any]) -> bool:
        answer_key = self._normalize_text_key(answer)
        if not answer_key:
            return True
        for key in ("question", "section", "field_key"):
            value_key = self._normalize_text_key(str(item.get(key, "")))
            if value_key and answer_key == value_key:
                return True
        return False

    def _has_question_label_prefix(self, answer: str, item: Dict[str, Any]) -> bool:
        if ":" not in answer:
            return False
        prefix = answer.split(":", 1)[0].strip()
        prefix_key = self._normalize_text_key(prefix)
        if not prefix_key:
            return False
        for key in ("question", "section"):
            value_key = self._normalize_text_key(str(item.get(key, "")))
            if value_key and (prefix_key in value_key or value_key in prefix_key):
                return True
        return False

    def _looks_like_keyword_dump(self, answer: str) -> bool:
        text = " ".join(str(answer or "").split())
        comma_count = text.count(",")
        if comma_count >= 4 and len(text) < 260:
            return True
        weak_patterns = [
            "다양한 언어",
            "다양한 자격증",
            "기술적 능력",
            "능력을 가지고 있습니다",
        ]
        return any(pattern in text for pattern in weak_patterns)

    def _is_intro_question(self, item: Dict[str, Any]) -> bool:
        text = " ".join(
            str(item.get(key, "")).strip()
            for key in ("question", "section", "field_key")
            if str(item.get(key, "")).strip()
        )
        normalized = self._normalize_text_key(text)
        return any(keyword in normalized for keyword in ["자기소개", "본인소개", "selfintroduction", "소개"])

    def _contains_personal_info_dump(self, answer: str) -> bool:
        text = str(answer or "")
        personal_markers = [
            "생년월일",
            "전화번호",
            "이메일",
            "주소",
            "거주",
            "@",
            "010-",
        ]
        if any(marker in text for marker in personal_markers):
            return True
        return bool(re.search(r"\b\d{4}[-./]\d{1,2}[-./]\d{1,2}\b", text))

    def _normalize_text_key(self, text: str) -> str:
        return "".join(char for char in str(text or "").lower() if char.isalnum())

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
