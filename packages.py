"""Pacchetti volo + alloggio per le migliori offerte di volo all'estero."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from airports import is_domestic
from models import Offer
from sources.hotels import BudgetExceeded, HotelSearch, Stay

log = logging.getLogger("sources.packages")  # avvisi salvati in last_errors.txt


@dataclass
class Package:
    offer: Offer
    hotel: Stay | None
    apartment: Stay | None

    @property
    def stay(self) -> Stay | None:
        """L'alloggio più economico tra hotel e appartamento."""
        options = [s for s in (self.hotel, self.apartment) if s]
        return min(options, key=lambda s: s.total_eur) if options else None

    def total(self, adults: int) -> float | None:
        return self.offer.price_pp * adults + self.stay.total_eur if self.stay else None


def candidates(offers: list[Offer], cfg: dict, history: dict[str, str] | None = None,
               today: date | None = None) -> list[Offer]:
    """Offerte all'estero (una per destinazione) per cui cercare l'alloggio.

    1 posto fisso per il volo più economico, gli altri a rotazione tra le
    destinazioni successive: prima quelle mai proposte o proposte da più tempo,
    così anche città come Barcellona arrivano prima o poi nel riepilogo.
    """
    hcfg = cfg.get("hotels") or {}
    history = history or {}
    first_day = (today or date.today()) + timedelta(days=hcfg.get("min_days_ahead", 7))
    best: dict[str, Offer] = {}
    for o in sorted(offers, key=lambda o: o.price_pp):
        if is_domestic(o.dest) or o.out_date < first_day or o.dest in best:
            continue
        best[o.dest] = o
    pool = list(best.values())[: hcfg.get("rotation_pool", 10)]
    fixed = hcfg.get("fixed_cheapest", 1)
    rotating = hcfg.get("rotating", max(hcfg.get("top_flights", 3) - fixed, 0))
    rest = sorted(enumerate(pool[fixed:]), key=lambda x: (history.get(x[1].dest, ""), x[0]))
    return pool[:fixed] + [o for _, o in rest[:rotating]]


def build(offers: list[Offer], cfg: dict, search: HotelSearch,
          today: date | None = None) -> tuple[list[Package], list[str]]:
    """Restituisce (pacchetti, note da mostrare)."""
    if not search.enabled:
        return [], []
    today = today or date.today()
    history = search.state.setdefault("package_history", {})
    chosen = candidates(offers, cfg, history, today)
    left = search.searches_left()
    if left is not None and left < 2 * len(chosen):
        return [], [f"Ricerche hotel quasi finite sul piano SerpApi ({left} rimaste): pacchetti sospesi."]
    packages, notes = [], []
    for o in chosen:
        try:
            hotel = search.best(o.dest_city, o.out_date, o.in_date, "hotel")
            apartment = search.best(o.dest_city, o.out_date, o.in_date, "apartment")
        except BudgetExceeded as e:
            notes.append(f"Ricerche hotel sospese fino al mese prossimo ({e}).")
            break
        except Exception as e:  # noqa: BLE001 - gli hotel non devono bloccare i voli
            log.warning("Hotel %s: %s", o.dest_city, e)
            continue
        history[o.dest] = today.isoformat()
        if hotel or apartment:
            packages.append(Package(o, hotel, apartment))
    search.save()
    return packages, notes
