"""OpenAI-compatible chat client built on the standard library only.

Works with Ollama (/v1), vLLM, LM Studio, llama.cpp server, or any service
exposing POST /v1/chat/completions.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class ChatError(RuntimeError):
    pass


class ChatClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        model: str = "",
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def chat(self, messages, *, temperature=None, max_tokens=None, model=None,
             response_format=None):
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        if response_format:
            payload["response_format"] = response_format
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
            raise ChatError(f"HTTP {exc.code} from {url}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ChatError(f"Cannot reach {url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ChatError(f"Timed out after {self.timeout}s calling {url}") from exc

        try:
            obj = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ChatError(f"Non-JSON response from {url}: {body[:400]}") from exc

        choices = obj.get("choices") or []
        if not choices:
            raise ChatError(f"No choices in response: {body[:400]}")
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
        return {
            "content": content,
            "reasoning": reasoning,
            "usage": obj.get("usage") or {},
            "raw": obj,
        }
