from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class OpenAICompatibleLLM:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    temperature: float = 0.2
    timeout_sec: int = 120

    @classmethod
    def from_env(cls) -> "OpenAICompatibleLLM | None":
        api_key = os.getenv("LEETANIM_LLM_API_KEY", "").strip()
        model = os.getenv("LEETANIM_LLM_MODEL", "").strip()
        if not api_key or not model:
            return None
        base_url = os.getenv("LEETANIM_LLM_BASE_URL", "https://api.openai.com/v1").strip()
        temperature = float(os.getenv("LEETANIM_LLM_TEMPERATURE", "0.2"))
        timeout_sec = int(os.getenv("LEETANIM_LLM_TIMEOUT_SEC", "120"))
        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            temperature=temperature,
            timeout_sec=timeout_sec,
        )

    def _endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        request = urllib.request.Request(
            self._endpoint(),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM network error: {exc}") from exc

        data: dict[str, Any] = json.loads(raw)
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"Unexpected LLM response: {data}")

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") in {"text", "output_text"} and item.get("text"):
                        parts.append(str(item["text"]))
                    elif item.get("content"):
                        parts.append(str(item["content"]))
            return "\n".join(part.strip() for part in parts if part.strip())
        return str(content).strip()
