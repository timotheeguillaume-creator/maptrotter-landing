"""Topic selection from keyword-dictionary.json with cluster-coverage scoring."""

from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Iterable


# Soft Australia-first bias while the AU wave is still under-covered
_AU_MAJOR = {
    "sydney",
    "melbourne",
    "brisbane",
    "perth",
    "adelaide",
    "canberra",
    "gold coast",
    "newcastle",
}
_AU_SECONDARY = {
    "hobart",
    "darwin",
    "cairns",
    "wollongong",
    "geelong",
    "townsville",
    "toowoomba",
    "ballarat",
    "launceston",
    "sunshine coast",
    "fremantle",
    "byron bay",
}
_OCEANIA = {"auckland", "wellington", "christchurch"}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _norm(text: str) -> str:
    s = unicodedata.normalize("NFD", (text or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _token_set(text: str) -> set[str]:
    return {t for t in _norm(text).split() if len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _rollout_bonus(city: str | None) -> float:
    if not city:
        return 0.0
    c = city.casefold()
    if c in _AU_MAJOR:
        return 2.5
    if c in _AU_SECONDARY:
        return 1.5
    if c in _OCEANIA:
        return 0.75
    return 0.0


def _coverage_maps(
    keywords: list[dict[str, Any]],
) -> tuple[Counter[str], Counter[str], Counter[str], Counter[tuple[str, str]]]:
    """Aggregate usedCount across cluster / city / locale / city×intent."""
    by_cluster: Counter[str] = Counter()
    by_city: Counter[str] = Counter()
    by_locale: Counter[str] = Counter()
    by_city_intent: Counter[tuple[str, str]] = Counter()
    for k in keywords:
        if k.get("status", "active") != "active":
            continue
        used = int(k.get("usedCount") or 0)
        cluster = k.get("clusterId") or ""
        city = (k.get("city") or "").casefold()
        locale = k.get("locale") or ""
        intent = k.get("intent") or ""
        by_cluster[cluster] += used
        if city:
            by_city[city] += used
        by_locale[locale] += used
        if city and intent:
            by_city_intent[(city, intent)] += used
    return by_cluster, by_city, by_locale, by_city_intent


def _recent_axis_usage(
    keywords: list[dict[str, Any]],
    cutoff: date,
) -> tuple[Counter[str], Counter[str], Counter[str]]:
    recent_cities: Counter[str] = Counter()
    recent_locales: Counter[str] = Counter()
    recent_intents: Counter[str] = Counter()
    for k in keywords:
        last = _parse_date(k.get("lastUsed"))
        if not last or last < cutoff:
            continue
        city = (k.get("city") or "").casefold()
        if city:
            recent_cities[city] += 1
        recent_locales[k.get("locale") or ""] += 1
        recent_intents[k.get("intent") or ""] += 1
    return recent_cities, recent_locales, recent_intents


def score_topic(
    k: dict[str, Any],
    *,
    by_cluster: Counter[str],
    by_city: Counter[str],
    by_locale: Counter[str],
    by_city_intent: Counter[tuple[str, str]],
    recent_cities: Counter[str],
    recent_locales: Counter[str],
    recent_intents: Counter[str],
    recent_phrase_tokens: list[set[str]],
    rng: random.Random,
) -> float:
    """
    Higher = better pick for a 2-posts/week cadence.

    Maximizes new cluster coverage, decays usedCount, rotates city×intent×locale,
    soft Australia-first bias, and rejects near-duplicate phrases vs recent titles.
    """
    used = int(k.get("usedCount") or 0)
    priority = int(k.get("priority") or 0)
    cluster = k.get("clusterId") or ""
    city = (k.get("city") or "").casefold()
    locale = k.get("locale") or ""
    intent = k.get("intent") or ""
    phrase_tokens = _token_set(str(k.get("phrase") or ""))

    # Near-duplicate guard: hard penalty if too similar to a recent phrase/title
    max_sim = max((_jaccard(phrase_tokens, t) for t in recent_phrase_tokens), default=0.0)
    if max_sim >= 0.72:
        return -1e6

    cluster_used = by_cluster.get(cluster, 0)
    city_used = by_city.get(city, 0) if city else 0
    locale_used = by_locale.get(locale, 0)
    pair_used = by_city_intent.get((city, intent), 0) if city else 0

    # Prefer never-published clusters / cities / city×intent pairs
    new_cluster = 6.0 if cluster_used == 0 else max(0.0, 4.0 - cluster_used)
    new_city = 3.0 if city and city_used == 0 else (1.5 if city and city_used == 1 else 0.0)
    new_pair = 2.5 if city and pair_used == 0 else 0.0

    # Locale balance: mild preference for under-used locales in the dictionary so far
    locale_balance = 2.0 / (1.0 + locale_used)

    # Decay on this row's usedCount (exponential soft decay)
    used_decay = used * 3.5

    # Avoid repeating same city / locale / intent in the last cooldown window
    recent_penalty = (
        recent_cities.get(city, 0) * 4.0
        + recent_locales.get(locale, 0) * 1.5
        + recent_intents.get(intent, 0) * 1.25
    )

    score = (
        priority * 1.8
        + new_cluster
        + new_city
        + new_pair
        + locale_balance
        + _rollout_bonus(k.get("city"))
        - used_decay
        - recent_penalty
        - max_sim * 5.0
        + rng.random() * 0.15  # tiny stable jitter
    )
    return score


def pick_topic(
    dictionary: dict[str, Any],
    *,
    today: date | None = None,
    locale: str | None = None,
    city: str | None = None,
    cooldown_days: int = 14,
    recent_titles: Iterable[str] | None = None,
) -> dict[str, Any] | None:
    """
    Among status=active keywords, score for cluster coverage + rotation.

    Prefer unused clusterId, under-covered city×intent, lower usedCount, higher
    priority; skip clusterId+city used within cooldown_days; soft Australia-first.
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

    by_cluster, by_city, by_locale, by_city_intent = _coverage_maps(keywords)
    recent_cities, recent_locales, recent_intents = _recent_axis_usage(keywords, cutoff)

    recent_phrase_tokens: list[set[str]] = []
    for k in keywords:
        last = _parse_date(k.get("lastUsed"))
        if last and last >= cutoff and k.get("phrase"):
            recent_phrase_tokens.append(_token_set(str(k["phrase"])))
    if recent_titles:
        for title in recent_titles:
            recent_phrase_tokens.append(_token_set(title))

    scored: list[tuple[float, dict[str, Any]]] = []
    for k in candidates:
        s = score_topic(
            k,
            by_cluster=by_cluster,
            by_city=by_city,
            by_locale=by_locale,
            by_city_intent=by_city_intent,
            recent_cities=recent_cities,
            recent_locales=recent_locales,
            recent_intents=recent_intents,
            recent_phrase_tokens=recent_phrase_tokens,
            rng=rng,
        )
        if s > -1e5:
            scored.append((s, k))

    if not scored:
        # Fallback: ignore similarity hard-fail
        scored = [
            (
                score_topic(
                    k,
                    by_cluster=by_cluster,
                    by_city=by_city,
                    by_locale=by_locale,
                    by_city_intent=by_city_intent,
                    recent_cities=recent_cities,
                    recent_locales=recent_locales,
                    recent_intents=recent_intents,
                    recent_phrase_tokens=[],
                    rng=rng,
                ),
                k,
            )
            for k in candidates
        ]

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


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
