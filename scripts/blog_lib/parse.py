"""Parse Gemini Markdown + YAML frontmatter + json-ld fence."""

from __future__ import annotations

import json
import re
from typing import Any

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)
JSON_LD_RE = re.compile(
    r"```(?:json-ld|json)\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


def parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    text = raw.strip()
    # Strip accidental model preambles
    if "---" in text:
        text = text[text.index("---") :]
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("missing YAML frontmatter (--- ... ---)")
    meta = _parse_simple_yaml(m.group(1))
    body = m.group(2).strip()
    return meta, body


def extract_json_ld(body: str) -> tuple[str, dict[str, Any] | list[Any] | None]:
    m = JSON_LD_RE.search(body)
    if not m:
        return body, None
    cleaned = (body[: m.start()] + body[m.end() :]).strip()
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid json-ld block: {e}") from e
    return cleaned, data


def _parse_simple_yaml(block: str) -> dict[str, Any]:
    """Minimal YAML subset: key: value, quoted strings, [lists], numbers."""
    result: dict[str, Any] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        result[key] = _parse_scalar(rest)
    return result


def _parse_scalar(value: str) -> Any:
    if value == "" or value.lower() in ("null", "~"):
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        items = []
        for part in _split_csv(inner):
            items.append(_parse_scalar(part.strip()))
        return items
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value


def _split_csv(inner: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    in_quote: str | None = None
    for ch in inner:
        if in_quote:
            buf.append(ch)
            if ch == in_quote:
                in_quote = None
            continue
        if ch in ('"', "'"):
            in_quote = ch
            buf.append(ch)
            continue
        if ch == ",":
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def slugify(text: str, *, locale: str = "fr", max_len: int = 70) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:max_len].strip("-")
    if locale in ("en", "es") and not slug.endswith(f"-{locale}"):
        # reserve room for suffix
        base = slug[: max_len - 3].rstrip("-")
        slug = f"{base}-{locale}"
    return slug or "post"
