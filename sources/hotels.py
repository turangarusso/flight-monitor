"""Alloggi tramite Google Hotels (SerpApi, piano gratuito).

Cerca hotel di almeno 3 stelle con buone recensioni e appartamenti interi,
scarta ostelli, camere private e bagni in comune, e restituisce la struttura
valida più economica. Le ricerche gratuite sono poche: c'è una cache su file
e un budget mensile salvato nello stato.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)

API = "https://serpapi.com/search.json"
ACCOUNT_API = "https://serpapi.com/account.json"  # gratuita: non consuma ricerche
CACHE = Path(__file__).parent.parent / "data" / "hotels_cache.json"

# parole che indicano strutture da evitare (nome, tipo, servizi, info)
BAD_WORDS = (
    "hostel", "ostello", "dorm", "shared bathroom", "shared bath", "bagno in comune",
    "bagno condiviso", "capsule", "private room", "camera privata", "room in ", "shared room",
)


@dataclass
class Stay:
    kind: str            # hotel | apartment
    name: str
    stars: int           # 0 per gli appartamenti
    rating: float        # voto ospiti su 5
    reviews: int
    total_eur: float     # prezzo totale del soggiorno per tutti gli ospiti
    link: str

    def as_dict(self) -> dict:
        return asdict(self)


class BudgetExceeded(Exception):
    pass


def _text(p: dict) -> str:
    parts = [p.get("name", ""), p.get("type", ""), p.get("description", "")]
    parts += p.get("amenities") or []
    parts += p.get("essential_info") or []
    return " ".join(str(x) for x in parts).lower()


def _total(p: dict, nights: int) -> float | None:
    total = (p.get("total_rate") or {}).get("extracted_lowest")
    if total:
        return float(total)
    nightly = (p.get("rate_per_night") or {}).get("extracted_lowest")
    return float(nightly) * nights if nightly else None


def _link(p: dict, city: str) -> str:
    if p.get("link"):
        return p["link"]
    return f"https://www.google.com/travel/search?q={quote(p.get('name', '') + ' ' + city)}&hl=it"


def acceptable(p: dict, kind: str, hcfg: dict) -> bool:
    """Filtri di qualità: niente catapecchie, niente bagni in comune."""
    text = _text(p)
    if any(w in text for w in BAD_WORDS):
        return False
    rating = p.get("overall_rating") or 0
    reviews = p.get("reviews") or 0
    loc = p.get("location_rating")
    if loc is not None and loc < hcfg.get("min_location_rating", 3.5):
        return False
    if kind == "hotel":
        stars = p.get("extracted_hotel_class") or 0
        return (stars >= hcfg.get("min_stars", 3)
                and rating >= hcfg.get("min_hotel_rating", 4.0)
                and reviews >= hcfg.get("min_hotel_reviews", 50))
    # appartamenti: deve essere l'alloggio intero, se Google lo specifica
    info = " ".join(p.get("essential_info") or []).lower()
    if info and "entire" not in info:
        return False
    return (rating >= hcfg.get("min_apartment_rating", 4.3)
            and reviews >= hcfg.get("min_apartment_reviews", 15))


def pick_best(properties: list[dict], kind: str, city: str, nights: int, hcfg: dict) -> Stay | None:
    best = None
    for p in properties or []:
        total = _total(p, nights)
        if not total or total > hcfg.get("max_total_eur", 250) or not acceptable(p, kind, hcfg):
            continue
        if best is None or total < best.total_eur:
            best = Stay(
                kind=kind,
                name=p.get("name", "?"),
                stars=int(p.get("extracted_hotel_class") or 0),
                rating=float(p.get("overall_rating") or 0),
                reviews=int(p.get("reviews") or 0),
                total_eur=round(total, 2),
                link=_link(p, city),
            )
    return best


class HotelSearch:
    """Ricerche SerpApi con cache su file e budget mensile."""

    def __init__(self, cfg: dict, state: dict, api_key: str | None = None,
                 cache_path: Path | None = None, today: date | None = None):
        self.cfg = cfg
        self.hcfg = cfg.get("hotels") or {}
        self.key = api_key if api_key is not None else os.environ.get("SERPAPI_KEY", "")
        self.cache_path = cache_path or CACHE
        self.today = today or date.today()
        self.month = self.today.strftime("%Y-%m")
        self.state = state
        self.counter = state.setdefault("hotel_searches", {})
        self.cache = self._load_cache()

    @property
    def enabled(self) -> bool:
        return bool(self.key) and self.hcfg.get("enabled", True)

    @property
    def used(self) -> int:
        return self.counter.get(self.month, 0)

    def searches_left(self) -> int | None:
        """Ricerche rimaste sul piano SerpApi (None se non si riesce a saperlo)."""
        try:
            r = requests.get(ACCOUNT_API, params={"api_key": self.key}, timeout=30)
            r.raise_for_status()
            left = r.json().get("total_searches_left")
            return int(left) if left is not None else None
        except Exception as e:  # noqa: BLE001
            log.info("SerpApi account: %s", e)
            return None

    def _load_cache(self) -> dict:
        if not self.cache_path.exists():
            return {}
        cache = json.loads(self.cache_path.read_text("utf-8"))
        limit = (self.today - timedelta(days=self.hcfg.get("cache_days", 3))).isoformat()
        return {k: v for k, v in cache.items() if v.get("searched", "") >= limit}

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1) + "\n", "utf-8")

    def best(self, city: str, check_in: date, check_out: date, kind: str) -> Stay | None:
        ck = f"{kind}|{city.lower()}|{check_in.isoformat()}|{check_out.isoformat()}"
        if ck in self.cache:
            hit = self.cache[ck]["stay"]
            return Stay(**hit) if hit else None
        if self.used >= self.hcfg.get("monthly_budget", 90):
            raise BudgetExceeded(f"budget mensile di {self.used} ricerche hotel esaurito")
        params = {
            "engine": "google_hotels",
            "q": city,
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "adults": self.cfg["adults"],
            "currency": "EUR",
            "gl": "it",
            "hl": "en",  # testi in inglese: filtri più affidabili
            "sort_by": 3,  # prezzo più basso
            "rating": 8,   # voto 4,0+
            "api_key": self.key,
        }
        if kind == "hotel":
            params["hotel_class"] = "3,4,5"
        else:
            params["vacation_rentals"] = "true"
        r = requests.get(API, params=params, timeout=60)
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(f"SerpApi: {data['error']}")
        self.counter[self.month] = self.used + 1
        nights = (check_out - check_in).days
        stay = pick_best(data.get("properties"), kind, city, nights, self.hcfg)
        self.cache[ck] = {
            "searched": self.today.isoformat(),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stay": stay.as_dict() if stay else None,
        }
        return stay
