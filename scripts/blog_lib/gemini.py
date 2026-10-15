"""Google Gemini API client with free-tier retries / exponential backoff."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger("blog.gemini")

DEFAULT_MODEL = "gemini-2.0-flash"
BACKOFF_SECONDS = (30, 60, 120, 240, 300)
REQUEST_TIMEOUT = 90
MAX_ATTEMPTS = 5


class GeminiError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


def _endpoint(model: str, api_key: str) -> str:
    return (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )


def call_gemini(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> str:
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiError("GEMINI_API_KEY is missing", retryable=False)
    model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL

    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192,
        },
    }
    data = json.dumps(body).encode("utf-8")
    url = _endpoint(model, api_key)

    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        started = time.monotonic()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            latency = time.monotonic() - started
            text = _extract_text(payload)
            log.info(
                "gemini_ok attempt=%s latency=%.1fs model=%s chars=%s",
                attempt,
                latency,
                model,
                len(text),
            )
            return text
        except urllib.error.HTTPError as e:
            status = e.code
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            retryable = status in (429, 500, 502, 503, 504)
            last_err = GeminiError(
                f"HTTP {status}: {err_body}",
                retryable=retryable,
                status=status,
            )
            log.warning(
                "gemini_http status=%s attempt=%s retryable=%s",
                status,
                attempt,
                retryable,
            )
            if not retryable or attempt >= max_attempts:
                raise last_err from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = GeminiError(str(e), retryable=True)
            log.warning("gemini_net attempt=%s err=%s", attempt, e)
            if attempt >= max_attempts:
                raise last_err from e

        wait = BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)]
        log.info("gemini_backoff sleep=%ss", wait)
        time.sleep(wait)

    raise last_err or GeminiError("Gemini failed with no detail")


def _extract_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise GeminiError(f"empty candidates: {json.dumps(payload)[:300]}")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
    text = "".join(texts).strip()
    if not text:
        raise GeminiError("empty model text")
    return text
