"""Google Flights tramite la libreria fast-flights (scraping).

Copre le compagnie che Ryanair/Wizz non coprono (easyJet, Volotea, Vueling,
ITA...). Google non permette "ovunque", quindi cerca su una lista di
destinazioni da config.yaml, per i prossimi N weekend ven→dom, solo diretti.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date
from urllib.parse import quote

import fx
from dates import upcoming_fri_sun
from models import Offer

log = logging.getLogger(__name__)

_PRICE_RE = re.compile(r"([€$£])?\s*([\d.,]+)\s*([€$£])?")


def parse_price(text: str) -> float | None:
    """'€58' / '$1,234' / '58 €' -> importo in EUR."""
    m = _PRICE_RE.search(text or "")
    if not m:
        return None
    symbol = m.group(1) or m.group(3) or "€"
    amount = float(m.group(2).replace(",", ""))
    return fx.to_eur(amount, fx.SYMBOLS.get(symbol, "EUR"))


def search_link(origin: str, dest: str, out_d: date, in_d: date) -> str:
    q = f"Flights from {origin} to {dest} on {out_d.isoformat()} through {in_d.isoformat()} nonstop"
    return f"https://www.google.com/travel/flights?q={quote(q)}&curr=EUR&hl=it"


def fetch(cfg: dict) -> list[Offer]:
    from fast_flights import FlightData, Passengers, create_filter, get_flights_from_filter

    gcfg = cfg["sources"]["google_flights"]
    origin = cfg["origin"]
    offers: list[Offer] = []
    errors = 0
    total = 0
    for dest in gcfg["destinations"]:
        for out_d, in_d in upcoming_fri_sun(gcfg.get("weekends", 8)):
            total += 1
            try:
                flt = create_filter(
                    flight_data=[
                        FlightData(date=out_d.isoformat(), from_airport=origin, to_airport=dest),
                        FlightData(date=in_d.isoformat(), from_airport=dest, to_airport=origin),
                    ],
                    trip="round-trip",
                    seat="economy",
                    passengers=Passengers(adults=1),
                    max_stops=0,
                )
                result = get_flights_from_filter(flt, currency="EUR", mode="common")
            except Exception as e:  # noqa: BLE001
                errors += 1
                log.debug("Google Flights %s %s: %s", dest, out_d, e)
                time.sleep(gcfg.get("sleep_seconds", 3))
                continue
            best = None
            for f in result.flights:
                price = parse_price(f.price)
                if f.stops == 0 and price and (best is None or price < best[0]):
                    best = (price, f.name)
            if best:
                offers.append(
                    Offer(
                        source="google_flights",
                        airline=best[1] or "Google Flights",
                        origin=origin,
                        dest=dest,
                        dest_city=dest,
                        out_date=out_d,
                        in_date=in_d,
                        price_pp=round(best[0], 2),
                        link=search_link(origin, dest, out_d, in_d),
                    )
                )
            time.sleep(gcfg.get("sleep_seconds", 3))
    if total and errors == total:
        raise RuntimeError(f"Google Flights: tutte le {total} ricerche fallite")
    log.info("Google Flights: %d ricerche, %d errori", total, errors)
    return offers
