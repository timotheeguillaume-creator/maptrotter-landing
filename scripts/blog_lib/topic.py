"""Topic selection from keyword-dictionary.json with rotation."""

from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta
from typing import Any


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def pick_topic(
    dictionary: dict[str, Any],
    *,
    today: date | None = None,
    locale: str | None = None,
    city: str | None = None,
    cooldown_days: int = 14,
) -> dict[str, Any] | None:
    """
    Among status=active keywords, prefer low usedCount then high priority.
    Stable daily shuffle; skip clusterId+city used within cooldown_days.
    """
    today = today or date.today()
    keywords = dictionary.get("keywords") or []
    active = [k for k in keywords if k.get("status", "active") == "active"]
    if locale:
        active = [k for k in active if k.get("locale") == locale]
    if city:
        city_l = city.casefold()
        active = [k for k in active if (k.get("city") or "").casefold() == city_l]

    recent_pairs: set[tuple[str, str]] = set()
    cutoff = today - timedelta(days=cooldown_days)
    for k in keywords:
        last = _parse_date(k.get("lastUsed"))
        if last and last >= cutoff:
            recent_pairs.add(
                ((k.get("clusterId") or ""), (k.get("city") or "").casefold())
            )

    candidates = [
        k
        for k in active
        if ((k.get("clusterId") or ""), (k.get("city") or "").casefold())
        not in recent_pairs
    ]
    if not candidates:
        candidates = active
    if not candidates:
        return None

    seed = int(hashlib.sha256(today.isoformat().encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    def sort_key(k: dict[str, Any]) -> tuple:
        return (
            int(k.get("usedCount") or 0),
            -int(k.get("priority") or 0),
            rng.random(),
        )

    candidates.sort(key=sort_key)
    return candidates[0]


def mark_used(
    dictionary: dict[str, Any],
    keyword_id: str,
    *,
    when: date | None = None,
) -> None:
    when = when or date.today()
    for k in dictionary.get("keywords") or []:
        if k.get("id") == keyword_id:
            k["usedCount"] = int(k.get("usedCount") or 0) + 1
            k["lastUsed"] = when.isoformat()
            break
    dictionary["updated"] = when.isoformat()


def iso_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
