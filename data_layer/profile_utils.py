from __future__ import annotations

import copy
from typing import Any, Dict, List


DEFAULT_PROFILE_TEMPLATE: Dict[str, Any] = {
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
        "졸업년도": "",
    },
    "자격증": [],
    "희망직무": "",
    "추가메모": "",
}


def _to_clean_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_clean_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = str(value).split(",")
    cleaned: List[str] = []
    for item in items:
        text = _to_clean_string(item)
        if text:
            cleaned.append(text)
    return cleaned


def normalize_profile_payload(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    raw = raw or {}
    profile = copy.deepcopy(DEFAULT_PROFILE_TEMPLATE)

    profile["이름"] = _to_clean_string(raw.get("이름"))
    profile["생년월일"] = _to_clean_string(raw.get("생년월일"))
    profile["나이"] = _to_clean_string(raw.get("나이"))
    profile["취미"] = _to_clean_list(raw.get("취미"))
    profile["경력"] = _to_clean_string(raw.get("경력"))
    profile["기술스택"] = _to_clean_list(raw.get("기술스택"))
    profile["이메일"] = _to_clean_string(raw.get("이메일"))
    profile["전화번호"] = _to_clean_string(raw.get("전화번호"))
    profile["주소"] = _to_clean_string(raw.get("주소"))
    profile["자격증"] = _to_clean_list(raw.get("자격증"))
    profile["희망직무"] = _to_clean_string(raw.get("희망직무"))
    profile["추가메모"] = _to_clean_string(raw.get("추가메모"))

    education = raw.get("학력") if isinstance(raw.get("학력"), dict) else {}
    profile["학력"] = {
        "대학교": _to_clean_string(education.get("대학교")),
        "전공": _to_clean_string(education.get("전공")),
        "학점": _to_clean_string(education.get("학점")),
        "졸업년도": _to_clean_string(education.get("졸업년도")),
    }
    return profile

