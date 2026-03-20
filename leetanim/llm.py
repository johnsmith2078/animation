from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.client import IncompleteRead, RemoteDisconnected
from typing import Any


@dataclass
class OpenAICompatibleLLM:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    temperature: float = 0.2
    max_tokens: int | None = 900
    timeout_sec: int = 120
    max_retries: int = 3
    retry_backoff_sec: float = 1.5
    max_continuations: int = 3

    @classmethod
    def from_env(cls) -> "OpenAICompatibleLLM | None":
        api_key = os.getenv("LEETANIM_LLM_API_KEY", "").strip()
        model = os.getenv("LEETANIM_LLM_MODEL", "").strip()
        if not api_key or not model:
            return None
        base_url = os.getenv("LEETANIM_LLM_BASE_URL", "https://api.openai.com/v1").strip()
        temperature = float(os.getenv("LEETANIM_LLM_TEMPERATURE", "0.2"))
        max_tokens_raw = os.getenv("LEETANIM_LLM_MAX_TOKENS", "900").strip()
        timeout_sec = int(os.getenv("LEETANIM_LLM_TIMEOUT_SEC", "120"))
        max_retries = int(os.getenv("LEETANIM_LLM_MAX_RETRIES", "3"))
        retry_backoff_sec = float(os.getenv("LEETANIM_LLM_RETRY_BACKOFF_SEC", "1.5"))
        max_continuations = int(os.getenv("LEETANIM_LLM_MAX_CONTINUATIONS", "3"))
        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            temperature=temperature,
            max_tokens=(int(max_tokens_raw) if max_tokens_raw else None),
            timeout_sec=timeout_sec,
            max_retries=max(0, max_retries),
            retry_backoff_sec=max(0.1, retry_backoff_sec),
            max_continuations=max(0, max_continuations),
        )

    def _endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _should_retry_http_status(self, status_code: int) -> bool:
        return status_code in {408, 409, 425, 429, 500, 502, 503, 504}

    def _sleep_before_retry(self, attempt_index: int) -> None:
        delay = self.retry_backoff_sec * (2**attempt_index)
        time.sleep(min(delay, 8.0))

    @staticmethod
    def _extract_message_text(message: dict[str, Any]) -> str:
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

    @staticmethod
    def _merge_text(existing: str, continuation: str) -> str:
        if not existing:
            return continuation
        if not continuation:
            return existing

        max_overlap = min(len(existing), len(continuation), 200)
        for overlap in range(max_overlap, 0, -1):
            if existing[-overlap:] == continuation[:overlap]:
                return existing + continuation[overlap:]
        return existing + continuation

    @staticmethod
    def _continuation_prompt() -> str:
        return (
            "继续刚才的回答，从中断处自然接着写。"
            "不要重复已经输出过的内容，不要重新起头。"
            "如果上文停在句子中间，就把句子补完，并完整自然地收尾。"
            "只输出续写部分。"
        )

    def _chat_once(self, messages: list[dict[str, str]], max_tokens: int | None) -> tuple[str, str | None]:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": messages,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        request_body = json.dumps(payload).encode("utf-8")
        attempts = self.max_retries + 1
        raw: str | None = None
        last_error: Exception | None = None

        for attempt_index in range(attempts):
            request = urllib.request.Request(
                self._endpoint(),
                data=request_body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                    raw = response.read().decode("utf-8")
                break
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if attempt_index < attempts - 1 and self._should_retry_http_status(exc.code):
                    last_error = exc
                    self._sleep_before_retry(attempt_index)
                    continue
                raise RuntimeError(f"LLM HTTP {exc.code}: {body}") from exc
            except (
                IncompleteRead,
                RemoteDisconnected,
                ConnectionResetError,
                TimeoutError,
                socket.timeout,
                urllib.error.URLError,
            ) as exc:
                last_error = exc
                if attempt_index < attempts - 1:
                    self._sleep_before_retry(attempt_index)
                    continue
                raise RuntimeError(f"LLM network error after {attempts} attempts: {exc}") from exc

        if raw is None:
            raise RuntimeError(f"LLM request failed without response body: {last_error}")

        data: dict[str, Any] = json.loads(raw)
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"Unexpected LLM response: {data}")

        choice = choices[0]
        message = choice.get("message", {})
        return self._extract_message_text(message), choice.get("finish_reason")

    def chat(self, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:
        resolved_max_tokens = self.max_tokens if max_tokens is None else max_tokens
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        combined = ""
        finish_reason: str | None = None

        for continuation_index in range(self.max_continuations + 1):
            chunk, finish_reason = self._chat_once(messages, resolved_max_tokens)
            combined = self._merge_text(combined, chunk)
            if finish_reason != "length":
                return combined.strip()

            messages.append({"role": "assistant", "content": chunk})
            messages.append({"role": "user", "content": self._continuation_prompt()})

        raise RuntimeError(
            f"LLM response still truncated after {self.max_continuations + 1} attempts; "
            "increase LEETANIM_LLM_MAX_CONTINUATIONS or stage max_tokens"
        )
