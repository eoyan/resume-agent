#Ollma API 호출

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import requests
from requests import exceptions as requests_exceptions


class OllamaClientError(RuntimeError):
    pass


class OllamaClient:
    def __init__(
        self,
        model: str = "qwen2.5:1.5b",
        base_url: str = "http://127.0.0.1:11434",
        timeout: int = 600,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def set_model(self, model: str) -> None:
        self.model = model

    def list_models(self) -> List[str]:
        response = requests.get(f"{self.base_url}/api/tags", timeout=10)
        response.raise_for_status()
        data = response.json()
        return [item["name"] for item in data.get("models", [])]

    def health(self) -> Dict[str, Any]:
        try:
            models = self.list_models()
            return {
                "available": True,
                "model": self.model,
                "installed": self.model in models,
                "models": models,
            }
        except requests.RequestException as error:
            return {
                "available": False,
                "model": self.model,
                "installed": False,
                "models": [],
                "error": str(error),
            }

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.2,
        format_json: bool = False,
    ) -> str | Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if format_json:
            payload["format"] = "json"

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=(10, self.timeout),
            )
            response.raise_for_status()
            data = response.json()
        except requests_exceptions.ReadTimeout as error:
            raise OllamaClientError(
                "Ollama 응답 대기 시간이 초과되었습니다. "
                f"현재 read timeout은 {self.timeout}초입니다. "
                "문서 길이를 줄이거나 OLLAMA_TIMEOUT 값을 더 크게 설정해 보세요."
            ) from error
        except requests.RequestException as error:
            raise OllamaClientError(f"Ollama 요청 실패: {error}") from error

        content = data.get("message", {}).get("content", "")
        if not format_json:
            return content
        return self._parse_json_content(content)

    def _parse_json_content(self, content: str) -> Dict[str, Any]:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        candidate = self._extract_outer_json(content)
        if candidate is None:
            raise OllamaClientError("모델 응답에서 JSON 객체를 찾지 못했습니다.")

        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as error:
            raise OllamaClientError("모델 응답 JSON 파싱에 실패했습니다.") from error

        if not isinstance(parsed, dict):
            raise OllamaClientError("모델 응답 JSON이 객체 형태가 아닙니다.")
        return parsed

    def _extract_outer_json(self, text: str) -> Optional[str]:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return text[start : end + 1]
