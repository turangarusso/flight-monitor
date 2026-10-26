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


def candidates(offers: list[Offer], cfg: dict, today: date | None = None) -> list[Offer]:
    """Le migliori offerte all'estero, una per destinazione, con almeno N giorni di anticipo."""
    hcfg = cfg.get("hotels") or {}
    first_day = (today or date.today()) + timedelta(days=hcfg.get("min_days_ahead", 7))
    best: dict[str, Offer] = {}
    for o in sorted(offers, key=lambda o: o.price_pp):
        if is_domestic(o.dest) or o.out_date < first_day or o.dest in best:
            continue
        best[o.dest] = o
    return list(best.values())[: hcfg.get("top_flights", 3)]


def build(offers: list[Offer], cfg: dict, search: HotelSearch,
          today: date | None = None) -> tuple[list[Package], list[str]]:
    """Restituisce (pacchetti, note da mostrare)."""
    if not search.enabled:
        return [], []
    packages, notes = [], []
    for o in candidates(offers, cfg, today):
        try:
            hotel = search.best(o.dest_city, o.out_date, o.in_date, "hotel")
            apartment = search.best(o.dest_city, o.out_date, o.in_date, "apartment")
        except BudgetExceeded as e:
            notes.append(f"Ricerche hotel sospese fino al mese prossimo ({e}).")
            break
        except Exception as e:  # noqa: BLE001 - gli hotel non devono bloccare i voli
            log.warning("Hotel %s: %s", o.dest_city, e)
            continue
        if hotel or apartment:
            packages.append(Package(o, hotel, apartment))
    search.save()
    return packages, notes
