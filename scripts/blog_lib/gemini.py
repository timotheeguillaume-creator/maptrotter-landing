"""Google Gemini API client with free-tier retries, backoff, and model fallbacks."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger("blog.gemini")

# gemini-2.0-flash was retired (HTTP 404). Prefer 3.8 Flash; fall back when it is
# overloaded (503 high demand) or retired — cron must not die on a single model.
DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_FALLBACK_MODELS = ("gemini-3.6-flash", "gemini-3.5-flash-lite")
# Per-model attempts stay small so we rotate off a hot model instead of burning ~10m.
ATTEMPTS_PER_MODEL = 3
BACKOFF_SECONDS = (20, 40, 80)
REQUEST_TIMEOUT = 90
# Blog drafts: keep thinking low so thought tokens do not eat maxOutputTokens.
DEFAULT_THINKING_LEVEL = "low"
DEFAULT_MAX_OUTPUT_TOKENS = 16384


class GeminiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status: int | None = None,
        model: str | None = None,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.status = status
        self.model = model


def _endpoint(model: str, api_key: str) -> str:
    return (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )


def _resolve_models(primary: str | None) -> list[str]:
    """Primary + fallbacks, de-duplicated, order preserved."""
    primary = (primary or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL).strip()
    raw = os.environ.get("GEMINI_MODEL_FALLBACKS", "").strip()
    if raw:
        fallbacks = [m.strip() for m in raw.split(",") if m.strip()]
    else:
        fallbacks = list(DEFAULT_FALLBACK_MODELS)
    models: list[str] = []
    for m in [primary, *fallbacks]:
        if m and m not in models:
            models.append(m)
    return models


def _build_body(prompt: str, *, with_thinking: bool) -> dict[str, Any]:
    # Gemini 3.x: do not send temperature/top_p/top_k (deprecated; may 400 later).
    gen: dict[str, Any] = {"maxOutputTokens": DEFAULT_MAX_OUTPUT_TOKENS}
    if with_thinking:
        gen["thinkingConfig"] = {"thinkingLevel": DEFAULT_THINKING_LEVEL}
    return {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen,
    }


def _is_capacity_or_missing(status: int | None, body: str) -> bool:
    if status in (429, 503):
        return True
    if status == 404:
        return True
    lowered = (body or "").lower()
    return "high demand" in lowered or "unavailable" in lowered


def _call_one_model(
    prompt: str,
    *,
    api_key: str,
    model: str,
    max_attempts: int,
) -> str:
    url = _endpoint(model, api_key)
    with_thinking = True
    last_err: GeminiError | None = None

    for attempt in range(1, max_attempts + 1):
        started = time.monotonic()
        body = _build_body(prompt, with_thinking=with_thinking)
        data = json.dumps(body).encode("utf-8")
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
            # Some Flash-Lite variants reject thinkingConfig — drop it once and retry.
            if (
                status == 400
                and with_thinking
                and "thinking" in err_body.lower()
            ):
                log.warning(
                    "gemini_http status=400 model=%s thinkingConfig rejected; retrying without",
                    model,
                )
                with_thinking = False
                last_err = GeminiError(
                    f"HTTP {status}: {err_body}",
                    retryable=True,
                    status=status,
                    model=model,
                )
                continue
            retryable = status in (429, 500, 502, 503, 504)
            last_err = GeminiError(
                f"HTTP {status}: {err_body}",
                retryable=retryable,
                status=status,
                model=model,
            )
            log.warning(
                "gemini_http status=%s attempt=%s model=%s retryable=%s",
                status,
                attempt,
                model,
                retryable,
            )
            # Retired / unknown model → caller should switch models immediately.
            if status == 404:
                raise last_err from e
            # Auth / hard client errors → do not burn more attempts.
            if status in (400, 401, 403) or not retryable:
                raise last_err from e
            if attempt >= max_attempts:
                raise last_err from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = GeminiError(str(e), retryable=True, model=model)
            log.warning("gemini_net attempt=%s model=%s err=%s", attempt, model, e)
            if attempt >= max_attempts:
                raise last_err from e

        wait = BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)]
        log.info("gemini_backoff sleep=%ss model=%s", wait, model)
        time.sleep(wait)

    raise last_err or GeminiError("Gemini failed with no detail", model=model)


def call_gemini(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    max_attempts: int | None = None,
) -> str:
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiError("GEMINI_API_KEY is missing", retryable=False)

    models = _resolve_models(model)
    attempts = max_attempts if max_attempts is not None else ATTEMPTS_PER_MODEL
    errors: list[str] = []

    for i, m in enumerate(models):
        log.info(
            "gemini_try model=%s (%s/%s) attempts_per_model=%s",
            m,
            i + 1,
            len(models),
            attempts,
        )
        try:
            return _call_one_model(
                prompt, api_key=api_key, model=m, max_attempts=attempts
            )
        except GeminiError as e:
            errors.append(f"{m}: {e}")
            # Hard auth failure: no point trying other models with same key.
            if e.status in (401, 403):
                raise GeminiError(
                    f"Gemini auth failed on {m} (HTTP {e.status}). "
                    "Check GEMINI_API_KEY. "
                    + "; ".join(errors),
                    retryable=False,
                    status=e.status,
                    model=m,
                ) from e
            has_next = i + 1 < len(models)
            if has_next and (
                e.retryable or _is_capacity_or_missing(e.status, str(e))
            ):
                log.warning(
                    "gemini_fallback from=%s to=%s reason=%s",
                    m,
                    models[i + 1],
                    e,
                )
                continue
            if has_next and e.status == 400:
                # Unexpected 400 after thinking strip — try next model anyway.
                log.warning(
                    "gemini_fallback from=%s to=%s reason=http_400",
                    m,
                    models[i + 1],
                )
                continue
            raise

    summary = "; ".join(errors) if errors else "no models tried"
    raise GeminiError(
        "All Gemini models failed (capacity/unavailable or errors). "
        f"Tried: {', '.join(models)}. Details: {summary}. "
        "Retry later, or set GEMINI_MODEL / GEMINI_MODEL_FALLBACKS to live models.",
        retryable=True,
        status=503,
        model=models[-1] if models else None,
    )


def _extract_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise GeminiError(f"empty candidates: {json.dumps(payload)[:300]}")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    texts = [
        p.get("text", "")
        for p in parts
        if isinstance(p, dict) and p.get("text") and not p.get("thought")
    ]
    text = "".join(texts).strip()
    if not text:
        raise GeminiError("empty model text")
    return text
