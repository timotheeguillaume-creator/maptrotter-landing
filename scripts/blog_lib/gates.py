"""Quality gates before commit (E-E-A-T / structure / brand voice)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GateResult:
    ok: bool
    failures: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.failures.append(msg)


BANNED_PATTERNS = [
    re.compile(r"\blorem ipsum\b", re.I),
    re.compile(r"en tant qu['’]ia\b", re.I),
    re.compile(r"\bas an ai\b", re.I),
    re.compile(r"como ia\b", re.I),
    re.compile(r"\[placeholder\]", re.I),
    re.compile(r"TODO:?\s*replace", re.I),
]

PRICE_CLAIM = re.compile(
    r"\b(\d+[.,]\d{2}\s*€|\€\s*\d+|\$\s*\d+|\d+\s*(euros?|dollars?))\b",
    re.I,
)
HOUR_CLAIM = re.compile(
    r"\b((ouvre|open|abre)\s+(de|from|desde)\s+\d{1,2}h|\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2})\b",
    re.I,
)


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w’']+\b", text, flags=re.UNICODE))


def run_gates(
    meta: dict[str, Any],
    markdown: str,
    json_ld: dict[str, Any] | list[Any] | None,
    *,
    recent_titles: list[str] | None = None,
    recent_bodies: list[str] | None = None,
) -> GateResult:
    result = GateResult(ok=True)
    locale = (meta.get("locale") or "fr").lower()
    title = str(meta.get("title") or "")
    slug = str(meta.get("slug") or "")
    body = markdown

    if not title:
        result.fail("missing frontmatter title")
    if not slug or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        result.fail("slug must be kebab-case ascii")

    h1s = re.findall(r"(?m)^#\s+(.+)$", body)
    if len(h1s) != 1:
        result.fail(f"expected exactly 1 H1, found {len(h1s)}")
    h2s = re.findall(r"(?m)^##\s+(.+)$", body)
    if len(h2s) < 3:
        result.fail(f"expected ≥3 H2, found {len(h2s)}")

    da_match = re.search(
        r"(?im)^##\s*Direct Answer\s*\n+(.+?)(?=\n##\s|\Z)",
        body,
        re.DOTALL,
    )
    if not da_match:
        result.fail("missing ## Direct Answer section")
    else:
        da_words = word_count(da_match.group(1))
        # Soft band around the prompt target (~40–80); allow a little slack so
        # transient model variance does not kill the cron.
        if da_words < 25 or da_words > 150:
            result.fail(f"Direct Answer word count out of range ({da_words}; want ~40–80, hard 25–150)")

    faq_match = re.search(r"(?im)^##\s*FAQ\b", body)
    if not faq_match:
        result.fail("missing ## FAQ section")
    else:
        faq_block = body[faq_match.start() :]
        q_count = len(re.findall(r"(?m)^\*\*[^*?]+\?\*\*", faq_block))
        if q_count < 3:
            # also accept Q: style
            q_count = max(q_count, len(re.findall(r"(?m)^\*\*.+\?\*\*", faq_block)))
        if q_count < 3:
            result.fail(f"FAQ needs ≥3 Q/A, found {q_count}")

    words = word_count(body)
    # Pilot / dry-run fixtures may be shorter; enforce plan bounds for live posts
    if words < 600:
        result.fail(f"too short: {words} words (<600)")
    if words > 2500:
        result.fail(f"too long: {words} words (>2500)")

    mt_count = len(re.findall(r"MapTrotter", body + " " + title))
    if mt_count < 2:
        result.fail(f"MapTrotter mentions too few ({mt_count}; want 2–5)")
    if mt_count > 8:
        result.fail(f"MapTrotter mentions too many ({mt_count}; max 8)")

    if not re.search(r"\[([^\]]+)\]\((/|/blog\.html)\)", body):
        result.fail("missing internal link to / or /blog.html")

    for pat in BANNED_PATTERNS:
        if pat.search(body) or pat.search(title):
            result.fail(f"banned pattern: {pat.pattern}")

    # Soft: flag dense price/hour claims without disclaimer
    if PRICE_CLAIM.search(body) or HOUR_CLAIM.search(body):
        if not re.search(r"disclaimer|vérif|check|sujet.*chang|may change|puede cambiar", body, re.I):
            result.fail("precise price/hour claim without disclaimer")

    phrase = str(meta.get("phrase") or meta.get("primaryKeyword") or "")
    if phrase:
        # naïve density: phrase should not appear every ~40 words
        occ = len(re.findall(re.escape(phrase), body, flags=re.I))
        if words > 0 and occ > max(8, words // 40):
            result.fail(f"keyword density too high for «{phrase}» ({occ}×)")

    if json_ld is None:
        result.fail("missing json-ld block")
    else:
        _gate_json_ld(result, json_ld)

    # Similarity vs recent posts
    recent_titles = recent_titles or []
    for prev in recent_titles:
        if _title_too_close(title, prev):
            result.fail(f"title too similar to recent post: {prev!r}")
            break
    recent_bodies = recent_bodies or []
    for prev in recent_bodies[:5]:
        if _jaccard_shingles(body, prev) > 0.55:
            result.fail("body too similar to a recent post (Jaccard shingles)")
            break

    # Locale heuristics (light)
    if locale == "fr" and not re.search(r"\b(le|la|les|des|une|pour|avec|dans)\b", body, re.I):
        result.fail("locale fr but French function words not detected")
    if locale == "en" and not re.search(r"\b(the|and|with|for|your|you)\b", body, re.I):
        result.fail("locale en but English function words not detected")
    if locale == "es" and not re.search(r"\b(el|la|los|las|para|con|una)\b", body, re.I):
        result.fail("locale es but Spanish function words not detected")

    return result


def _gate_json_ld(result: GateResult, data: dict[str, Any] | list[Any]) -> None:
    try:
        json.dumps(data)
    except (TypeError, ValueError) as e:
        result.fail(f"json-ld not serializable: {e}")
        return

    graph: list[Any]
    if isinstance(data, list):
        graph = data
    elif isinstance(data, dict) and "@graph" in data:
        graph = list(data["@graph"] or [])
    else:
        graph = [data]

    types = {item.get("@type") for item in graph if isinstance(item, dict)}
    if not ({"BlogPosting", "Article"} & types):
        result.fail("json-ld missing BlogPosting/Article")
    if "FAQPage" not in types:
        result.fail("json-ld missing FAQPage")


def _title_too_close(a: str, b: str) -> bool:
    na = _norm(a)
    nb = _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return _jaccard_shingles(na, nb, n=2) > 0.7


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.casefold()).strip()


def _jaccard_shingles(a: str, b: str, n: int = 3) -> float:
    sa = _shingles(_norm(a), n)
    sb = _shingles(_norm(b), n)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _shingles(text: str, n: int) -> set[str]:
    tokens = re.findall(r"\w+", text, flags=re.UNICODE)
    if len(tokens) < n:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}
