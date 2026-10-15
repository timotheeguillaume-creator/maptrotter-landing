#!/usr/bin/env python3
"""
One-shot builder for MapTrotter SEO keyword dictionary (phase C1).

Generates data/keyword-dictionary.json from intentions × spot types ×
cities × locales (FR / EN / ES / IT / DE). Australia-first city rollout
(major → secondary → NZ Oceania anchors → legacy EU/NA seeds). Filters
absurd geo×spot combos and deduplicates by normalized phrase.

Usage:
  python3 scripts/build-dictionary.py
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "keyword-dictionary.json"

# Australia-first (prefs): majors → secondary → Oceania hubs → legacy seeds
CITIES_AU_MAJOR = [
    "Sydney",
    "Melbourne",
    "Brisbane",
    "Perth",
    "Adelaide",
    "Canberra",
    "Gold Coast",
    "Newcastle",
]
CITIES_AU_SECONDARY = [
    "Hobart",
    "Darwin",
    "Cairns",
    "Wollongong",
    "Geelong",
    "Townsville",
    "Toowoomba",
    "Ballarat",
    "Launceston",
    "Sunshine Coast",
    "Fremantle",
    "Byron Bay",
]
# NZ hubs only — justified “around Australia”, do not dilute AU focus
CITIES_OCEANIA = [
    "Auckland",
    "Wellington",
    "Christchurch",
]
CITIES_LEGACY = [
    "Paris",
    "Lyon",
    "Marseille",
    "Bordeaux",
    "Toulouse",
    "Nantes",
    "Lille",
    "Nice",
    "Montpellier",
    "Strasbourg",
    "Bruxelles",
    "Genève",
    "Montréal",
    "Barcelona",
    "Lisboa",
    "Berlin",
    "Amsterdam",
    "Roma",
    "London",
    "New York",
]
CITIES = CITIES_AU_MAJOR + CITIES_AU_SECONDARY + CITIES_OCEANIA + CITIES_LEGACY

AU_CITIES = set(CITIES_AU_MAJOR + CITIES_AU_SECONDARY)
OCEANIA_CITIES = set(CITIES_OCEANIA)

# Cities where "urban beach / waterfront" phrasing is plausible
BEACH_OK = {
    # AU / Oceania coastal & waterfront
    "Sydney",
    "Melbourne",
    "Brisbane",
    "Perth",
    "Adelaide",
    "Gold Coast",
    "Newcastle",
    "Hobart",
    "Darwin",
    "Cairns",
    "Wollongong",
    "Geelong",
    "Townsville",
    "Sunshine Coast",
    "Fremantle",
    "Byron Bay",
    "Auckland",
    "Wellington",
    "Christchurch",
    # Legacy
    "Marseille",
    "Nice",
    "Barcelona",
    "Lisboa",
    "Amsterdam",
    "New York",
    "Montréal",
    "Bordeaux",
    "Nantes",
}

SPOT_TYPES = [
    "cafe",
    "bar",
    "rooftop",
    "marche",
    "parc",
    "plage",
    "street-art",
    "musee-gratuit",
    "club",
    "afterwork",
    "food-hall",
    "auberge",
    "cowork",
    "vue-panoramique",
    "evenement-ephemere",
]

# persona / intention axes (locaux · voyageurs · rencontres + JTBD)
INTENTS = [
    "rencontre",
    "decouvrir-spot",
    "sortir-soir",
    "festival",
    "partager-adresse",
    "eviter-touristique",
    "last-minute",
    "carte-interactive",
    "locaux-voyageurs",
    "itineraire",
]

PERSONAS = [
    "local",
    "voyageur",
    "solo",
    "nomade",
    "expat",
    "amis",
    "couple",
    "organisateur",
]

MODIFIERS = [
    "gratuit",
    "cache",
    "late-night",
    "dimanche",
    "pluie",
    "solo-friendly",
    "dog-friendly",
    "lgbtq",
    "sans-alcool",
    "budget",
]

LOCALES = ("fr", "en", "es", "it", "de")

SPOT_LABEL = {
    "fr": {
        "cafe": "cafés",
        "bar": "bars",
        "rooftop": "rooftops",
        "marche": "marchés",
        "parc": "parcs",
        "plage": "plages urbaines",
        "street-art": "spots street art",
        "musee-gratuit": "musées gratuits",
        "club": "clubs",
        "afterwork": "afterworks",
        "food-hall": "food halls",
        "auberge": "auberges",
        "cowork": "coworkings",
        "vue-panoramique": "vues panoramiques",
        "evenement-ephemere": "événements éphémères",
    },
    "en": {
        "cafe": "cafés",
        "bar": "bars",
        "rooftop": "rooftops",
        "marche": "markets",
        "parc": "parks",
        "plage": "urban beaches",
        "street-art": "street art spots",
        "musee-gratuit": "free museums",
        "club": "clubs",
        "afterwork": "afterworks",
        "food-hall": "food halls",
        "auberge": "hostels",
        "cowork": "coworking spaces",
        "vue-panoramique": "panoramic viewpoints",
        "evenement-ephemere": "pop-up events",
    },
    "es": {
        "cafe": "cafés",
        "bar": "bares",
        "rooftop": "rooftops",
        "marche": "mercados",
        "parc": "parques",
        "plage": "playas urbanas",
        "street-art": "spots de street art",
        "musee-gratuit": "museos gratis",
        "club": "clubs",
        "afterwork": "afterworks",
        "food-hall": "food halls",
        "auberge": "albergues",
        "cowork": "coworkings",
        "vue-panoramique": "miradores",
        "evenement-ephemere": "eventos efímeros",
    },
    "it": {
        "cafe": "caffè",
        "bar": "bar",
        "rooftop": "rooftop",
        "marche": "mercati",
        "parc": "parchi",
        "plage": "spiagge urbane",
        "street-art": "spot di street art",
        "musee-gratuit": "musei gratuiti",
        "club": "club",
        "afterwork": "afterwork",
        "food-hall": "food hall",
        "auberge": "ostelli",
        "cowork": "coworking",
        "vue-panoramique": "belvedere",
        "evenement-ephemere": "eventi pop-up",
    },
    "de": {
        "cafe": "Cafés",
        "bar": "Bars",
        "rooftop": "Rooftops",
        "marche": "Märkte",
        "parc": "Parks",
        "plage": "Stadtstrände",
        "street-art": "Street-Art-Spots",
        "musee-gratuit": "kostenlose Museen",
        "club": "Clubs",
        "afterwork": "Afterworks",
        "food-hall": "Food Halls",
        "auberge": "Hostels",
        "cowork": "Coworking-Spaces",
        "vue-panoramique": "Aussichtspunkte",
        "evenement-ephemere": "Pop-up-Events",
    },
}

MOD_LABEL = {
    "fr": {
        "gratuit": "gratuits",
        "cache": "cachés",
        "late-night": "late-night",
        "dimanche": "le dimanche",
        "pluie": "par temps de pluie",
        "solo-friendly": "solo-friendly",
        "dog-friendly": "dog-friendly",
        "lgbtq": "LGBTQ+ friendly",
        "sans-alcool": "sans alcool",
        "budget": "petit budget",
    },
    "en": {
        "gratuit": "free",
        "cache": "hidden",
        "late-night": "late-night",
        "dimanche": "on Sunday",
        "pluie": "on a rainy day",
        "solo-friendly": "solo-friendly",
        "dog-friendly": "dog-friendly",
        "lgbtq": "LGBTQ+ friendly",
        "sans-alcool": "alcohol-free",
        "budget": "budget-friendly",
    },
    "es": {
        "gratuit": "gratis",
        "cache": "escondidos",
        "late-night": "nocturnos",
        "dimanche": "el domingo",
        "pluie": "con lluvia",
        "solo-friendly": "para ir solo",
        "dog-friendly": "pet-friendly",
        "lgbtq": "LGBTQ+ friendly",
        "sans-alcool": "sin alcohol",
        "budget": "baratos",
    },
    "it": {
        "gratuit": "gratuiti",
        "cache": "nascosti",
        "late-night": "notturni",
        "dimanche": "di domenica",
        "pluie": "con la pioggia",
        "solo-friendly": "adatti da soli",
        "dog-friendly": "pet-friendly",
        "lgbtq": "LGBTQ+ friendly",
        "sans-alcool": "senza alcol",
        "budget": "low cost",
    },
    "de": {
        "gratuit": "kostenlose",
        "cache": "versteckte",
        "late-night": "Late-Night",
        "dimanche": "am Sonntag",
        "pluie": "bei Regen",
        "solo-friendly": "solo-freundlich",
        "dog-friendly": "hundefreundlich",
        "lgbtq": "LGBTQ+ friendly",
        "sans-alcool": "alkoholfrei",
        "budget": "günstig",
    },
}

CITY_PREP = {
    "fr": "à",
    "en": "in",
    "es": "en",
    "it": "a",
    "de": "in",
}


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def normalize_phrase(phrase: str) -> str:
    s = strip_accents(phrase.lower().strip())
    s = re.sub(r"[^a-z0-9\s\-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def slug_city(city: str) -> str:
    return normalize_phrase(city).replace(" ", "-")


def spot_ok(spot: str, city: str) -> bool:
    if spot == "plage" and city not in BEACH_OK:
        return False
    return True


def priority_for(
    intent: str,
    persona: str,
    is_faq: bool,
    is_brand: bool,
    city: str | None = None,
) -> int:
    base = 3
    if intent in ("rencontre", "locaux-voyageurs", "decouvrir-spot"):
        base = 5
    elif intent in ("carte-interactive", "sortir-soir", "eviter-touristique"):
        base = 4
    if persona in ("local", "voyageur", "solo"):
        base = min(5, base + 1)
    if is_faq:
        base = min(5, base + 1)
    if is_brand:
        base = max(2, base - 1)
    # Australia-first: boost AU majors, mild boost secondary / NZ hubs
    if city in CITIES_AU_MAJOR:
        base = min(5, base + 1)
    elif city in CITIES_AU_SECONDARY or city in OCEANIA_CITIES:
        base = min(5, base)
    return base


def cluster_id(locale: str, intent: str, persona: str) -> str:
    return f"{persona}-{intent}-{locale}"


def make_entry(
    *,
    id_: str,
    phrase: str,
    locale: str,
    city: str | None,
    intent: str,
    persona: str,
    spot_type: str | None,
    cluster: str,
    priority: int,
    status: str = "active",
) -> dict:
    return {
        "id": id_,
        "phrase": phrase,
        "locale": locale,
        "city": city,
        "intent": intent,
        "persona": persona,
        "spotType": spot_type,
        "clusterId": cluster,
        "priority": priority,
        "usedCount": 0,
        "lastUsed": None,
        "status": status,
    }


def patterns_for_locale(locale: str) -> list[dict]:
    """Return pattern factories keyed by kind for a locale."""
    prep = CITY_PREP[locale]
    spots = SPOT_LABEL[locale]
    mods = MOD_LABEL[locale]

    if locale == "fr":
        return [
            {
                "kind": "meet-travelers",
                "intent": "rencontre",
                "persona": "local",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"rencontrer des voyageurs {prep} {city}",
            },
            {
                "kind": "meet-locals",
                "intent": "rencontre",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"rencontrer des locaux {prep} {city}",
            },
            {
                "kind": "meet-solo",
                "intent": "rencontre",
                "persona": "solo",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"rencontrer des voyageurs solo {prep} {city}",
            },
            {
                "kind": "faq-meet",
                "intent": "rencontre",
                "persona": "voyageur",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"comment rencontrer des gens {prep} {city}",
            },
            {
                "kind": "faq-meet-local",
                "intent": "rencontre",
                "persona": "local",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"comment rencontrer des voyageurs {prep} {city}",
            },
            {
                "kind": "spots-local",
                "intent": "decouvrir-spot",
                "persona": "voyageur",
                "spot": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"spots {spots[spot]} locaux {prep} {city}",
            },
            {
                "kind": "spots-hidden",
                "intent": "eviter-touristique",
                "persona": "voyageur",
                "spot": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"{spots[spot]} cachés {prep} {city}",
            },
            {
                "kind": "cafe-meet",
                "intent": "rencontre",
                "persona": "voyageur",
                "spot": "cafe",
                "faq": False,
                "fn": lambda city, **_: f"cafés pour rencontrer des locaux {prep} {city}",
            },
            {
                "kind": "tonight-solo",
                "intent": "sortir-soir",
                "persona": "solo",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"que faire ce soir {prep} {city} solo",
            },
            {
                "kind": "faq-tonight",
                "intent": "sortir-soir",
                "persona": "local",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"que faire ce soir {prep} {city}",
            },
            {
                "kind": "festival-week",
                "intent": "festival",
                "persona": "local",
                "spot": "evenement-ephemere",
                "faq": False,
                "fn": lambda city, **_: f"festivals et événements {prep} {city} cette semaine",
            },
            {
                "kind": "map-activities",
                "intent": "carte-interactive",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"carte interactive activités {prep} {city}",
            },
            {
                "kind": "locals-travelers",
                "intent": "locaux-voyageurs",
                "persona": "local",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"locaux et voyageurs {prep} {city}",
            },
            {
                "kind": "nightlife",
                "intent": "sortir-soir",
                "persona": "amis",
                "spot": "bar",
                "faq": False,
                "fn": lambda city, **_: f"nightlife et sorties {prep} {city}",
            },
            {
                "kind": "afterwork",
                "intent": "sortir-soir",
                "persona": "local",
                "spot": "afterwork",
                "faq": False,
                "fn": lambda city, **_: f"afterwork et rencontres {prep} {city}",
            },
            {
                "kind": "walking-tour",
                "intent": "itineraire",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"itinéraire communauté authenticité {prep} {city}",
            },
            {
                "kind": "last-minute",
                "intent": "last-minute",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"activité last-minute {prep} {city}",
            },
            {
                "kind": "share-spot",
                "intent": "partager-adresse",
                "persona": "local",
                "spot": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"partager une adresse {spots[spot]} {prep} {city}",
            },
            {
                "kind": "mod-spots",
                "intent": "decouvrir-spot",
                "persona": "voyageur",
                "spot": True,
                "mod": True,
                "faq": False,
                "fn": lambda city, spot, mod, **_: f"{spots[spot]} {mods[mod]} {prep} {city}",
            },
            {
                "kind": "faq-where-spot",
                "intent": "decouvrir-spot",
                "persona": "voyageur",
                "spot": True,
                "faq": True,
                "fn": lambda city, spot, **_: f"où trouver des {spots[spot]} {prep} {city}",
            },
            {
                "kind": "nomad-cowork",
                "intent": "decouvrir-spot",
                "persona": "nomade",
                "spot": "cowork",
                "faq": False,
                "fn": lambda city, **_: f"coworking pour nomades digitaux {prep} {city}",
            },
            {
                "kind": "expat-meet",
                "intent": "rencontre",
                "persona": "expat",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"rencontrer d'autres expats {prep} {city}",
            },
            {
                "kind": "couple-citybreak",
                "intent": "decouvrir-spot",
                "persona": "couple",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"spots authentiques city-break en couple {prep} {city}",
            },
            {
                "kind": "organizer",
                "intent": "partager-adresse",
                "persona": "organisateur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"organiser une sortie communauté {prep} {city}",
            },
            {
                "kind": "bored-local",
                "intent": "sortir-soir",
                "persona": "local",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"je m'ennuie {prep} {city} que faire ce soir",
            },
            {
                "kind": "brand-city",
                "intent": "carte-interactive",
                "persona": "voyageur",
                "spot": None,
                "brand": True,
                "faq": False,
                "fn": lambda city, **_: f"MapTrotter {city}",
            },
            {
                "kind": "brand-spot",
                "intent": "decouvrir-spot",
                "persona": "local",
                "spot": True,
                "brand": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"MapTrotter {spots[spot]} {city}",
            },
        ]

    if locale == "en":
        return [
            {
                "kind": "meet-travelers",
                "intent": "rencontre",
                "persona": "local",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"meet travelers {prep} {city}",
            },
            {
                "kind": "meet-locals",
                "intent": "rencontre",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"meet locals {prep} {city}",
            },
            {
                "kind": "meet-solo",
                "intent": "rencontre",
                "persona": "solo",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"meet solo travelers {prep} {city}",
            },
            {
                "kind": "faq-meet",
                "intent": "rencontre",
                "persona": "voyageur",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"how to meet people {prep} {city}",
            },
            {
                "kind": "faq-meet-local",
                "intent": "rencontre",
                "persona": "local",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"how to meet travelers {prep} {city}",
            },
            {
                "kind": "spots-local",
                "intent": "decouvrir-spot",
                "persona": "voyageur",
                "spot": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"best local {spots[spot]} {prep} {city}",
            },
            {
                "kind": "spots-hidden",
                "intent": "eviter-touristique",
                "persona": "voyageur",
                "spot": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"hidden {spots[spot]} {prep} {city}",
            },
            {
                "kind": "cafe-meet",
                "intent": "rencontre",
                "persona": "voyageur",
                "spot": "cafe",
                "faq": False,
                "fn": lambda city, **_: f"cafés to meet locals {prep} {city}",
            },
            {
                "kind": "tonight-solo",
                "intent": "sortir-soir",
                "persona": "solo",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"what to do tonight {prep} {city} solo",
            },
            {
                "kind": "faq-tonight",
                "intent": "sortir-soir",
                "persona": "local",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"what to do tonight {prep} {city}",
            },
            {
                "kind": "festival-week",
                "intent": "festival",
                "persona": "local",
                "spot": "evenement-ephemere",
                "faq": False,
                "fn": lambda city, **_: f"festivals and events {prep} {city} this week",
            },
            {
                "kind": "map-activities",
                "intent": "carte-interactive",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"interactive map activities {prep} {city}",
            },
            {
                "kind": "locals-travelers",
                "intent": "locaux-voyageurs",
                "persona": "local",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"locals and travelers {prep} {city}",
            },
            {
                "kind": "nightlife",
                "intent": "sortir-soir",
                "persona": "amis",
                "spot": "bar",
                "faq": False,
                "fn": lambda city, **_: f"nightlife and hangouts {prep} {city}",
            },
            {
                "kind": "afterwork",
                "intent": "sortir-soir",
                "persona": "local",
                "spot": "afterwork",
                "faq": False,
                "fn": lambda city, **_: f"afterwork meetups {prep} {city}",
            },
            {
                "kind": "walking-tour",
                "intent": "itineraire",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"community walking tour {prep} {city}",
            },
            {
                "kind": "last-minute",
                "intent": "last-minute",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"last-minute activities {prep} {city}",
            },
            {
                "kind": "share-spot",
                "intent": "partager-adresse",
                "persona": "local",
                "spot": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"share a local {spots[spot][:-1] if spots[spot].endswith('s') else spots[spot]} tip {prep} {city}",
            },
            {
                "kind": "mod-spots",
                "intent": "decouvrir-spot",
                "persona": "voyageur",
                "spot": True,
                "mod": True,
                "faq": False,
                "fn": lambda city, spot, mod, **_: f"{mods[mod]} {spots[spot]} {prep} {city}",
            },
            {
                "kind": "faq-where-spot",
                "intent": "decouvrir-spot",
                "persona": "voyageur",
                "spot": True,
                "faq": True,
                "fn": lambda city, spot, **_: f"where to find {spots[spot]} {prep} {city}",
            },
            {
                "kind": "nomad-cowork",
                "intent": "decouvrir-spot",
                "persona": "nomade",
                "spot": "cowork",
                "faq": False,
                "fn": lambda city, **_: f"coworking for digital nomads {prep} {city}",
            },
            {
                "kind": "expat-meet",
                "intent": "rencontre",
                "persona": "expat",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"meet other expats {prep} {city}",
            },
            {
                "kind": "couple-citybreak",
                "intent": "decouvrir-spot",
                "persona": "couple",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"authentic city-break spots for couples {prep} {city}",
            },
            {
                "kind": "organizer",
                "intent": "partager-adresse",
                "persona": "organisateur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"organize a community hangout {prep} {city}",
            },
            {
                "kind": "bored-local",
                "intent": "sortir-soir",
                "persona": "local",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"bored {prep} {city} what to do tonight",
            },
            {
                "kind": "brand-city",
                "intent": "carte-interactive",
                "persona": "voyageur",
                "spot": None,
                "brand": True,
                "faq": False,
                "fn": lambda city, **_: f"MapTrotter {city}",
            },
            {
                "kind": "brand-spot",
                "intent": "decouvrir-spot",
                "persona": "local",
                "spot": True,
                "brand": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"MapTrotter {spots[spot]} {city}",
            },
            {
                "kind": "meet-maptrotter",
                "intent": "rencontre",
                "persona": "voyageur",
                "spot": None,
                "brand": True,
                "faq": False,
                "fn": lambda city, **_: f"meet locals tonight {city} MapTrotter",
            },
        ]

    if locale == "es":
        return [
        {
            "kind": "meet-travelers",
            "intent": "rencontre",
            "persona": "local",
            "spot": None,
            "faq": False,
            "fn": lambda city, **_: f"conocer viajeros {prep} {city}",
        },
        {
            "kind": "meet-locals",
            "intent": "rencontre",
            "persona": "voyageur",
            "spot": None,
            "faq": False,
            "fn": lambda city, **_: f"conocer locales {prep} {city}",
        },
        {
            "kind": "meet-solo",
            "intent": "rencontre",
            "persona": "solo",
            "spot": None,
            "faq": False,
            "fn": lambda city, **_: f"conocer mochileros {prep} {city}",
        },
        {
            "kind": "faq-meet",
            "intent": "rencontre",
            "persona": "voyageur",
            "spot": None,
            "faq": True,
            "fn": lambda city, **_: f"cómo conocer gente {prep} {city}",
        },
        {
            "kind": "faq-meet-local",
            "intent": "rencontre",
            "persona": "local",
            "spot": None,
            "faq": True,
            "fn": lambda city, **_: f"cómo conocer viajeros {prep} {city}",
        },
        {
            "kind": "spots-local",
            "intent": "decouvrir-spot",
            "persona": "voyageur",
            "spot": True,
            "faq": False,
            "fn": lambda city, spot, **_: f"{spots[spot]} locales {prep} {city}",
        },
        {
            "kind": "spots-hidden",
            "intent": "eviter-touristique",
            "persona": "voyageur",
            "spot": True,
            "faq": False,
            "fn": lambda city, spot, **_: f"{spots[spot]} escondidos {prep} {city}",
        },
        {
            "kind": "cafe-meet",
            "intent": "rencontre",
            "persona": "voyageur",
            "spot": "cafe",
            "faq": False,
            "fn": lambda city, **_: f"cafés para conocer gente {prep} {city}",
        },
        {
            "kind": "tonight-solo",
            "intent": "sortir-soir",
            "persona": "solo",
            "spot": None,
            "faq": False,
            "fn": lambda city, **_: f"qué hacer esta noche {prep} {city} solo",
        },
        {
            "kind": "faq-tonight",
            "intent": "sortir-soir",
            "persona": "local",
            "spot": None,
            "faq": True,
            "fn": lambda city, **_: f"qué hacer esta noche {prep} {city}",
        },
        {
            "kind": "festival-week",
            "intent": "festival",
            "persona": "local",
            "spot": "evenement-ephemere",
            "faq": False,
            "fn": lambda city, **_: f"festivales y eventos {prep} {city} esta semana",
        },
        {
            "kind": "map-activities",
            "intent": "carte-interactive",
            "persona": "voyageur",
            "spot": None,
            "faq": False,
            "fn": lambda city, **_: f"mapa interactivo actividades {prep} {city}",
        },
        {
            "kind": "locals-travelers",
            "intent": "locaux-voyageurs",
            "persona": "local",
            "spot": None,
            "faq": False,
            "fn": lambda city, **_: f"locales y viajeros {prep} {city}",
        },
        {
            "kind": "nightlife",
            "intent": "sortir-soir",
            "persona": "amis",
            "spot": "bar",
            "faq": False,
            "fn": lambda city, **_: f"vida nocturna y planes {prep} {city}",
        },
        {
            "kind": "afterwork",
            "intent": "sortir-soir",
            "persona": "local",
            "spot": "afterwork",
            "faq": False,
            "fn": lambda city, **_: f"afterwork para conocer gente {prep} {city}",
        },
        {
            "kind": "walking-tour",
            "intent": "itineraire",
            "persona": "voyageur",
            "spot": None,
            "faq": False,
            "fn": lambda city, **_: f"ruta a pie comunidad {prep} {city}",
        },
        {
            "kind": "last-minute",
            "intent": "last-minute",
            "persona": "voyageur",
            "spot": None,
            "faq": False,
            "fn": lambda city, **_: f"planes de última hora {prep} {city}",
        },
        {
            "kind": "share-spot",
            "intent": "partager-adresse",
            "persona": "local",
            "spot": True,
            "faq": False,
            "fn": lambda city, spot, **_: f"compartir un {spots[spot].rstrip('s')} local {prep} {city}",
        },
        {
            "kind": "mod-spots",
            "intent": "decouvrir-spot",
            "persona": "voyageur",
            "spot": True,
            "mod": True,
            "faq": False,
            "fn": lambda city, spot, mod, **_: f"{spots[spot]} {mods[mod]} {prep} {city}",
        },
        {
            "kind": "faq-where-spot",
            "intent": "decouvrir-spot",
            "persona": "voyageur",
            "spot": True,
            "faq": True,
            "fn": lambda city, spot, **_: f"dónde encontrar {spots[spot]} {prep} {city}",
        },
        {
            "kind": "nomad-cowork",
            "intent": "decouvrir-spot",
            "persona": "nomade",
            "spot": "cowork",
            "faq": False,
            "fn": lambda city, **_: f"coworking para nómadas digitales {prep} {city}",
        },
        {
            "kind": "expat-meet",
            "intent": "rencontre",
            "persona": "expat",
            "spot": None,
            "faq": False,
            "fn": lambda city, **_: f"conocer otros expatriados {prep} {city}",
        },
        {
            "kind": "couple-citybreak",
            "intent": "decouvrir-spot",
            "persona": "couple",
            "spot": None,
            "faq": False,
            "fn": lambda city, **_: f"spots auténticos en pareja {prep} {city}",
        },
        {
            "kind": "organizer",
            "intent": "partager-adresse",
            "persona": "organisateur",
            "spot": None,
            "faq": False,
            "fn": lambda city, **_: f"organizar quedada comunidad {prep} {city}",
        },
        {
            "kind": "bored-local",
            "intent": "sortir-soir",
            "persona": "local",
            "spot": None,
            "faq": True,
            "fn": lambda city, **_: f"me aburro {prep} {city} qué hacer esta noche",
        },
        {
            "kind": "brand-city",
            "intent": "carte-interactive",
            "persona": "voyageur",
            "spot": None,
            "brand": True,
            "faq": False,
            "fn": lambda city, **_: f"MapTrotter {city}",
        },
        {
            "kind": "brand-spot",
            "intent": "decouvrir-spot",
            "persona": "local",
            "spot": True,
            "brand": True,
            "faq": False,
            "fn": lambda city, spot, **_: f"MapTrotter {spots[spot]} {city}",
        },
        {
            "kind": "mercado-meet",
            "intent": "rencontre",
            "persona": "voyageur",
            "spot": "marche",
            "faq": False,
            "fn": lambda city, **_: f"mercados para conocer gente {prep} {city}",
        },
        ]

    if locale == "it":
        return [
            {
                "kind": "meet-travelers",
                "intent": "rencontre",
                "persona": "local",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"incontrare viaggiatori {prep} {city}",
            },
            {
                "kind": "meet-locals",
                "intent": "rencontre",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"incontrare locali {prep} {city}",
            },
            {
                "kind": "meet-solo",
                "intent": "rencontre",
                "persona": "solo",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"incontrare viaggiatori solo {prep} {city}",
            },
            {
                "kind": "faq-meet",
                "intent": "rencontre",
                "persona": "voyageur",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"come conoscere gente {prep} {city}",
            },
            {
                "kind": "faq-meet-local",
                "intent": "rencontre",
                "persona": "local",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"come incontrare viaggiatori {prep} {city}",
            },
            {
                "kind": "spots-local",
                "intent": "decouvrir-spot",
                "persona": "voyageur",
                "spot": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"{spots[spot]} locali {prep} {city}",
            },
            {
                "kind": "spots-hidden",
                "intent": "eviter-touristique",
                "persona": "voyageur",
                "spot": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"{spots[spot]} nascosti {prep} {city}",
            },
            {
                "kind": "cafe-meet",
                "intent": "rencontre",
                "persona": "voyageur",
                "spot": "cafe",
                "faq": False,
                "fn": lambda city, **_: f"caffè per conoscere locali {prep} {city}",
            },
            {
                "kind": "tonight-solo",
                "intent": "sortir-soir",
                "persona": "solo",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"cosa fare stasera {prep} {city} da soli",
            },
            {
                "kind": "faq-tonight",
                "intent": "sortir-soir",
                "persona": "local",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"cosa fare stasera {prep} {city}",
            },
            {
                "kind": "festival-week",
                "intent": "festival",
                "persona": "local",
                "spot": "evenement-ephemere",
                "faq": False,
                "fn": lambda city, **_: f"festival ed eventi {prep} {city} questa settimana",
            },
            {
                "kind": "map-activities",
                "intent": "carte-interactive",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"mappa interattiva attività {prep} {city}",
            },
            {
                "kind": "locals-travelers",
                "intent": "locaux-voyageurs",
                "persona": "local",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"locali e viaggiatori {prep} {city}",
            },
            {
                "kind": "nightlife",
                "intent": "sortir-soir",
                "persona": "amis",
                "spot": "bar",
                "faq": False,
                "fn": lambda city, **_: f"vita notturna e uscite {prep} {city}",
            },
            {
                "kind": "afterwork",
                "intent": "sortir-soir",
                "persona": "local",
                "spot": "afterwork",
                "faq": False,
                "fn": lambda city, **_: f"afterwork per incontri {prep} {city}",
            },
            {
                "kind": "walking-tour",
                "intent": "itineraire",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"itinerario a piedi comunità {prep} {city}",
            },
            {
                "kind": "last-minute",
                "intent": "last-minute",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"attività last-minute {prep} {city}",
            },
            {
                "kind": "share-spot",
                "intent": "partager-adresse",
                "persona": "local",
                "spot": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"condividere un indirizzo {spots[spot]} {prep} {city}",
            },
            {
                "kind": "mod-spots",
                "intent": "decouvrir-spot",
                "persona": "voyageur",
                "spot": True,
                "mod": True,
                "faq": False,
                "fn": lambda city, spot, mod, **_: f"{spots[spot]} {mods[mod]} {prep} {city}",
            },
            {
                "kind": "faq-where-spot",
                "intent": "decouvrir-spot",
                "persona": "voyageur",
                "spot": True,
                "faq": True,
                "fn": lambda city, spot, **_: f"dove trovare {spots[spot]} {prep} {city}",
            },
            {
                "kind": "nomad-cowork",
                "intent": "decouvrir-spot",
                "persona": "nomade",
                "spot": "cowork",
                "faq": False,
                "fn": lambda city, **_: f"coworking per nomadi digitali {prep} {city}",
            },
            {
                "kind": "expat-meet",
                "intent": "rencontre",
                "persona": "expat",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"incontrare altri expat {prep} {city}",
            },
            {
                "kind": "couple-citybreak",
                "intent": "decouvrir-spot",
                "persona": "couple",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"spot autentici in coppia {prep} {city}",
            },
            {
                "kind": "organizer",
                "intent": "partager-adresse",
                "persona": "organisateur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"organizzare un'uscita community {prep} {city}",
            },
            {
                "kind": "bored-local",
                "intent": "sortir-soir",
                "persona": "local",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"mi annoio {prep} {city} cosa fare stasera",
            },
            {
                "kind": "brand-city",
                "intent": "carte-interactive",
                "persona": "voyageur",
                "spot": None,
                "brand": True,
                "faq": False,
                "fn": lambda city, **_: f"MapTrotter {city}",
            },
            {
                "kind": "brand-spot",
                "intent": "decouvrir-spot",
                "persona": "local",
                "spot": True,
                "brand": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"MapTrotter {spots[spot]} {city}",
            },
        ]

    if locale == "de":
        return [
            {
                "kind": "meet-travelers",
                "intent": "rencontre",
                "persona": "local",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"Reisende treffen {prep} {city}",
            },
            {
                "kind": "meet-locals",
                "intent": "rencontre",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"Locals treffen {prep} {city}",
            },
            {
                "kind": "meet-solo",
                "intent": "rencontre",
                "persona": "solo",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"Solo-Reisende treffen {prep} {city}",
            },
            {
                "kind": "faq-meet",
                "intent": "rencontre",
                "persona": "voyageur",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"wie man Leute kennenlernt {prep} {city}",
            },
            {
                "kind": "faq-meet-local",
                "intent": "rencontre",
                "persona": "local",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"wie man Reisende trifft {prep} {city}",
            },
            {
                "kind": "spots-local",
                "intent": "decouvrir-spot",
                "persona": "voyageur",
                "spot": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"lokale {spots[spot]} {prep} {city}",
            },
            {
                "kind": "spots-hidden",
                "intent": "eviter-touristique",
                "persona": "voyageur",
                "spot": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"versteckte {spots[spot]} {prep} {city}",
            },
            {
                "kind": "cafe-meet",
                "intent": "rencontre",
                "persona": "voyageur",
                "spot": "cafe",
                "faq": False,
                "fn": lambda city, **_: f"Cafés um Locals zu treffen {prep} {city}",
            },
            {
                "kind": "tonight-solo",
                "intent": "sortir-soir",
                "persona": "solo",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"was tun heute Abend {prep} {city} solo",
            },
            {
                "kind": "faq-tonight",
                "intent": "sortir-soir",
                "persona": "local",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"was tun heute Abend {prep} {city}",
            },
            {
                "kind": "festival-week",
                "intent": "festival",
                "persona": "local",
                "spot": "evenement-ephemere",
                "faq": False,
                "fn": lambda city, **_: f"Festivals und Events {prep} {city} diese Woche",
            },
            {
                "kind": "map-activities",
                "intent": "carte-interactive",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"interaktive Karte Aktivitäten {prep} {city}",
            },
            {
                "kind": "locals-travelers",
                "intent": "locaux-voyageurs",
                "persona": "local",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"Locals und Reisende {prep} {city}",
            },
            {
                "kind": "nightlife",
                "intent": "sortir-soir",
                "persona": "amis",
                "spot": "bar",
                "faq": False,
                "fn": lambda city, **_: f"Nachtleben und Ausgehen {prep} {city}",
            },
            {
                "kind": "afterwork",
                "intent": "sortir-soir",
                "persona": "local",
                "spot": "afterwork",
                "faq": False,
                "fn": lambda city, **_: f"Afterwork zum Kennenlernen {prep} {city}",
            },
            {
                "kind": "walking-tour",
                "intent": "itineraire",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"Community-Spaziergang {prep} {city}",
            },
            {
                "kind": "last-minute",
                "intent": "last-minute",
                "persona": "voyageur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"Last-Minute-Aktivitäten {prep} {city}",
            },
            {
                "kind": "share-spot",
                "intent": "partager-adresse",
                "persona": "local",
                "spot": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"einen lokalen {spots[spot]}-Tipp teilen {prep} {city}",
            },
            {
                "kind": "mod-spots",
                "intent": "decouvrir-spot",
                "persona": "voyageur",
                "spot": True,
                "mod": True,
                "faq": False,
                "fn": lambda city, spot, mod, **_: f"{mods[mod]} {spots[spot]} {prep} {city}",
            },
            {
                "kind": "faq-where-spot",
                "intent": "decouvrir-spot",
                "persona": "voyageur",
                "spot": True,
                "faq": True,
                "fn": lambda city, spot, **_: f"wo findet man {spots[spot]} {prep} {city}",
            },
            {
                "kind": "nomad-cowork",
                "intent": "decouvrir-spot",
                "persona": "nomade",
                "spot": "cowork",
                "faq": False,
                "fn": lambda city, **_: f"Coworking für digitale Nomaden {prep} {city}",
            },
            {
                "kind": "expat-meet",
                "intent": "rencontre",
                "persona": "expat",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"andere Expats treffen {prep} {city}",
            },
            {
                "kind": "couple-citybreak",
                "intent": "decouvrir-spot",
                "persona": "couple",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"authentische Spots für Paare {prep} {city}",
            },
            {
                "kind": "organizer",
                "intent": "partager-adresse",
                "persona": "organisateur",
                "spot": None,
                "faq": False,
                "fn": lambda city, **_: f"Community-Treffen organisieren {prep} {city}",
            },
            {
                "kind": "bored-local",
                "intent": "sortir-soir",
                "persona": "local",
                "spot": None,
                "faq": True,
                "fn": lambda city, **_: f"langeweile {prep} {city} was tun heute Abend",
            },
            {
                "kind": "brand-city",
                "intent": "carte-interactive",
                "persona": "voyageur",
                "spot": None,
                "brand": True,
                "faq": False,
                "fn": lambda city, **_: f"MapTrotter {city}",
            },
            {
                "kind": "brand-spot",
                "intent": "decouvrir-spot",
                "persona": "local",
                "spot": True,
                "brand": True,
                "faq": False,
                "fn": lambda city, spot, **_: f"MapTrotter {spots[spot]} {city}",
            },
        ]

    raise ValueError(f"unsupported locale: {locale}")


# Spot subsets for patterns that need spots — keep matrix dense but readable
CORE_SPOTS = [
    "cafe",
    "bar",
    "rooftop",
    "marche",
    "parc",
    "street-art",
    "club",
    "food-hall",
    "auberge",
    "vue-panoramique",
    "plage",
    "musee-gratuit",
    "cowork",
    "afterwork",
    "evenement-ephemere",
]

# Modifiers × spots for a controlled expansion (not full cartesian)
MOD_SPOT_PAIRS = [
    ("cache", "bar"),
    ("cache", "cafe"),
    ("cache", "rooftop"),
    ("cache", "marche"),
    ("cache", "parc"),
    ("cache", "street-art"),
    ("gratuit", "parc"),
    ("gratuit", "musee-gratuit"),
    ("gratuit", "street-art"),
    ("gratuit", "vue-panoramique"),
    ("late-night", "bar"),
    ("late-night", "club"),
    ("late-night", "food-hall"),
    ("dimanche", "marche"),
    ("dimanche", "parc"),
    ("dimanche", "cafe"),
    ("pluie", "musee-gratuit"),
    ("pluie", "cafe"),
    ("pluie", "food-hall"),
    ("pluie", "cowork"),
    ("solo-friendly", "cafe"),
    ("solo-friendly", "bar"),
    ("solo-friendly", "auberge"),
    ("solo-friendly", "cowork"),
    ("dog-friendly", "parc"),
    ("dog-friendly", "cafe"),
    ("lgbtq", "bar"),
    ("lgbtq", "club"),
    ("lgbtq", "cafe"),
    ("sans-alcool", "cafe"),
    ("sans-alcool", "food-hall"),
    ("budget", "auberge"),
    ("budget", "street-art"),
    ("budget", "marche"),
    ("budget", "parc"),
]

# City priority tiers — Australia-first, then legacy anchors
TIER_A = set(CITIES_AU_MAJOR) | {
    "Auckland",
    "Paris",
    "Lyon",
    "Marseille",
    "Barcelona",
    "Berlin",
    "London",
    "Montréal",
    "Bruxelles",
    "Roma",
}
TIER_B = set(CITIES_AU_SECONDARY) | set(CITIES_OCEANIA) | {
    "Bordeaux",
    "Toulouse",
    "Nantes",
    "Nice",
    "Amsterdam",
    "Lisboa",
    "New York",
}
# Remaining legacy = tier C (lighter expansion)

# AU + Oceania always get base patterns in every locale
_AU_WAVE = AU_CITIES | OCEANIA_CITIES
_LEGACY_ES_HEAVY = {
    "Barcelona",
    "Paris",
    "Lisboa",
    "Montréal",
    "Berlin",
    "London",
    "Marseille",
    "Nice",
    "Bruxelles",
    "Amsterdam",
}
_LEGACY_IT_HEAVY = {"Roma", "Paris", "Berlin", "London", "Barcelona", "Amsterdam", "Nice"}
_LEGACY_DE_HEAVY = {"Berlin", "Paris", "London", "Amsterdam", "Bruxelles", "Genève", "Roma"}

# Locale expansion — EN heaviest on AU; FR/ES/IT/DE cover AU majors + language anchors
LOCALE_POLICY = {
    "fr": {
        "cities": CITIES,
        "heavy_cities": _AU_WAVE | TIER_A | TIER_B,
        "mod_cities": set(CITIES_AU_MAJOR) | TIER_A | TIER_B,
        "spot_cities": _AU_WAVE | set(CITIES_LEGACY),
        "skip_heavy_kinds_tier_c": False,
    },
    "en": {
        # EN = primary for Australia wave
        "cities": CITIES,
        "heavy_cities": _AU_WAVE | TIER_A | TIER_B,
        "mod_cities": _AU_WAVE | TIER_A | TIER_B,
        "spot_cities": _AU_WAVE
        | TIER_A
        | TIER_B
        | {"Lille", "Montpellier", "Strasbourg", "Genève"},
        "skip_heavy_kinds_tier_c": True,
    },
    "es": {
        "cities": CITIES,
        "heavy_cities": set(CITIES_AU_MAJOR) | {"Auckland"} | _LEGACY_ES_HEAVY,
        "mod_cities": set(CITIES_AU_MAJOR) | {
            "Barcelona",
            "Paris",
            "Lisboa",
            "Montréal",
            "Berlin",
            "London",
            "Marseille",
            "Nice",
        },
        "spot_cities": set(CITIES_AU_MAJOR)
        | set(CITIES_AU_SECONDARY)
        | {"Auckland", "Wellington"}
        | {
            "Barcelona",
            "Paris",
            "Lyon",
            "Marseille",
            "Nice",
            "Lisboa",
            "Montréal",
            "Berlin",
            "Amsterdam",
            "London",
            "New York",
            "Bruxelles",
            "Bordeaux",
            "Toulouse",
            "Roma",
        },
        "skip_heavy_kinds_tier_c": True,
    },
    "it": {
        "cities": CITIES,
        "heavy_cities": set(CITIES_AU_MAJOR) | {"Auckland"} | _LEGACY_IT_HEAVY,
        "mod_cities": set(CITIES_AU_MAJOR) | _LEGACY_IT_HEAVY,
        "spot_cities": set(CITIES_AU_MAJOR)
        | set(CITIES_AU_SECONDARY)
        | {"Auckland", "Wellington"}
        | _LEGACY_IT_HEAVY
        | {"Lyon", "Marseille", "Bruxelles", "New York", "Lisboa"},
        "skip_heavy_kinds_tier_c": True,
    },
    "de": {
        "cities": CITIES,
        "heavy_cities": set(CITIES_AU_MAJOR) | {"Auckland"} | _LEGACY_DE_HEAVY,
        "mod_cities": set(CITIES_AU_MAJOR) | _LEGACY_DE_HEAVY,
        "spot_cities": set(CITIES_AU_MAJOR)
        | set(CITIES_AU_SECONDARY)
        | {"Auckland", "Wellington", "Christchurch"}
        | _LEGACY_DE_HEAVY
        | {"Lyon", "Marseille", "Nice", "Barcelona", "New York", "Lisboa"},
        "skip_heavy_kinds_tier_c": True,
    },
}


def build() -> dict:
    keywords: list[dict] = []
    seen: set[str] = set()
    counters: dict[str, int] = {}

    def add(entry: dict) -> bool:
        key = f"{entry['locale']}|{normalize_phrase(entry['phrase'])}"
        if key in seen:
            return False
        seen.add(key)
        keywords.append(entry)
        return True

    for locale in LOCALES:
        policy = LOCALE_POLICY[locale]
        patterns = patterns_for_locale(locale)
        for city in policy["cities"]:
            city_slug = slug_city(city)
            for pat in patterns:
                is_faq = bool(pat.get("faq"))
                is_brand = bool(pat.get("brand"))
                intent = pat["intent"]
                persona = pat["persona"]
                spot_spec = pat.get("spot")
                needs_mod = bool(pat.get("mod"))
                kind = pat["kind"]

                # Base meet/FAQ/brand-city patterns: all policy cities
                # Heavy spot expansions: gated by policy
                heavy = kind in (
                    "spots-local",
                    "spots-hidden",
                    "share-spot",
                    "mod-spots",
                    "faq-where-spot",
                    "brand-spot",
                )

                def emit(spot: str | None = None, mod: str | None = None) -> None:
                    if spot and not spot_ok(spot, city):
                        return
                    if heavy and city not in policy["heavy_cities"] and kind != "brand-spot":
                        if city not in policy["spot_cities"]:
                            return
                    if kind in ("mod-spots",) and city not in policy["mod_cities"]:
                        return
                    if kind == "brand-spot" and city not in policy["heavy_cities"]:
                        return
                    if kind == "share-spot" and city not in policy["spot_cities"]:
                        return
                    if (
                        policy["skip_heavy_kinds_tier_c"]
                        and kind == "mod-spots"
                        and city not in TIER_A
                        and MOD_SPOT_PAIRS.index((mod, spot)) % 2 == 1
                    ):
                        return
                    kwargs = {"city": city}
                    if spot is not None:
                        kwargs["spot"] = spot
                    if mod is not None:
                        kwargs["mod"] = mod
                    phrase = pat["fn"](**kwargs)
                    base_id = f"{locale}-{city_slug}-{intent}-{kind}"
                    if spot:
                        base_id += f"-{spot}"
                    if mod:
                        base_id += f"-{mod}"
                    n = counters.get(base_id, 0) + 1
                    counters[base_id] = n
                    eid = f"{base_id}-{n:02d}"
                    entry = make_entry(
                        id_=eid,
                        phrase=phrase,
                        locale=locale,
                        city=city,
                        intent=intent,
                        persona=persona,
                        spot_type=spot,
                        cluster=cluster_id(locale, intent, persona),
                        priority=priority_for(
                            intent, persona, is_faq, is_brand, city=city
                        ),
                    )
                    add(entry)

                if needs_mod:
                    if city not in policy["mod_cities"]:
                        continue
                    for mod, spot in MOD_SPOT_PAIRS:
                        emit(spot=spot, mod=mod)
                elif spot_spec is True:
                    if city not in policy["spot_cities"] and heavy:
                        continue
                    for spot in CORE_SPOTS:
                        if (
                            locale != "fr"
                            and city not in policy["heavy_cities"]
                            and spot
                            in (
                                "evenement-ephemere",
                                "afterwork",
                                "musee-gratuit",
                                "plage",
                            )
                        ):
                            continue
                        emit(spot=spot)
                elif isinstance(spot_spec, str):
                    emit(spot=spot_spec)
                else:
                    emit()

    # Generic brand + spotType without city (helps brand cluster)
    for locale in LOCALES:
        labels = SPOT_LABEL[locale]
        for spot in ("cafe", "bar", "rooftop", "marche", "parc", "street-art", "cowork"):
            phrase = f"MapTrotter {labels[spot]}"
            add(
                make_entry(
                    id_=f"{locale}-brand-spot-{spot}-01",
                    phrase=phrase,
                    locale=locale,
                    city=None,
                    intent="decouvrir-spot",
                    persona="local",
                    spot_type=spot,
                    cluster=cluster_id(locale, "decouvrir-spot", "local"),
                    priority=3,
                )
            )

    # Community / vibes brand anchors (no city)
    anchors = {
        "fr": [
            ("carte interactive MapTrotter communauté", "carte-interactive", "voyageur"),
            ("spots locaux authentiques MapTrotter", "decouvrir-spot", "local"),
            ("rencontres voyageurs sur MapTrotter", "rencontre", "voyageur"),
            ("vibes locales carte MapTrotter", "carte-interactive", "local"),
        ],
        "en": [
            ("MapTrotter interactive map community", "carte-interactive", "voyageur"),
            ("authentic local spots MapTrotter", "decouvrir-spot", "local"),
            ("meet travelers on MapTrotter", "rencontre", "voyageur"),
            ("local vibes MapTrotter map", "carte-interactive", "local"),
        ],
        "es": [
            ("mapa interactivo MapTrotter comunidad", "carte-interactive", "voyageur"),
            ("spots locales auténticos MapTrotter", "decouvrir-spot", "local"),
            ("conocer viajeros en MapTrotter", "rencontre", "voyageur"),
            ("vibes locales mapa MapTrotter", "carte-interactive", "local"),
        ],
        "it": [
            ("mappa interattiva MapTrotter community", "carte-interactive", "voyageur"),
            ("spot locali autentici MapTrotter", "decouvrir-spot", "local"),
            ("incontrare viaggiatori su MapTrotter", "rencontre", "voyageur"),
            ("vibes locali mappa MapTrotter", "carte-interactive", "local"),
        ],
        "de": [
            ("interaktive MapTrotter Karte Community", "carte-interactive", "voyageur"),
            ("authentische lokale Spots MapTrotter", "decouvrir-spot", "local"),
            ("Reisende treffen auf MapTrotter", "rencontre", "voyageur"),
            ("lokale Vibes MapTrotter Karte", "carte-interactive", "local"),
        ],
    }
    for locale, rows in anchors.items():
        for i, (phrase, intent, persona) in enumerate(rows, 1):
            add(
                make_entry(
                    id_=f"{locale}-brand-anchor-{i:02d}",
                    phrase=phrase,
                    locale=locale,
                    city=None,
                    intent=intent,
                    persona=persona,
                    spot_type=None,
                    cluster=cluster_id(locale, intent, persona),
                    priority=4,
                )
            )

    return {
        "version": 1,
        "updated": "2026-10-15",
        "meta": {
            "product": "MapTrotter",
            "axes": {
                "personas": PERSONAS,
                "intents": INTENTS,
                "spotTypes": SPOT_TYPES,
                "modifiers": MODIFIERS,
                "cities": CITIES,
                "locales": list(LOCALES),
                "rollout": {
                    "au_major": CITIES_AU_MAJOR,
                    "au_secondary": CITIES_AU_SECONDARY,
                    "oceania": CITIES_OCEANIA,
                    "legacy": CITIES_LEGACY,
                },
            },
            "notes": (
                "Generated by scripts/build-dictionary.py for SEO/AIO blog topic rotation. "
                "Australia-first city wave; locales FR/EN/ES/IT/DE. "
                "Absurd geo×spot combos (e.g. plage × Canberra inland-only) excluded where listed. "
                "Phrases are localized intent translations, not word-for-word spam."
            ),
        },
        "keywords": keywords,
    }


def stats(doc: dict) -> None:
    kws = doc["keywords"]
    by_locale: dict[str, int] = {}
    faq = brand = 0
    for k in kws:
        by_locale[k["locale"]] = by_locale.get(k["locale"], 0) + 1
        p = k["phrase"].lower()
        if p.startswith(
            (
                "comment ",
                "cómo ",
                "how to ",
                "que faire",
                "qué hacer",
                "what to do",
                "où ",
                "dónde ",
                "where ",
                "je m'ennuie",
                "me aburro",
                "bored ",
                "come ",
                "cosa fare",
                "dove ",
                "mi annoio",
                "wie man ",
                "was tun ",
                "wo findet ",
                "langeweile ",
            )
        ):
            faq += 1
        if "maptrotter" in p:
            brand += 1
    n = len(kws)
    print(f"Total entries: {n}")
    for loc, c in sorted(by_locale.items()):
        pct = 100 * c / n if n else 0
        print(f"  {loc}: {c} ({pct:.1f}%)")
    print(f"FAQ-style (~): {faq} ({100*faq/n:.1f}%)")
    print(f"Brand mentions: {brand} ({100*brand/n:.1f}%)")
    cities = sorted({k["city"] for k in kws if k["city"]})
    print(f"Cities covered: {len(cities)}")


def main() -> None:
    doc = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stats(doc)
    if len(doc["keywords"]) < 500:
        raise SystemExit(f"ERROR: only {len(doc['keywords'])} entries (need ≥500)")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
