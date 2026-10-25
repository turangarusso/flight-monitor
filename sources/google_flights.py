"""Google Flights tramite la libreria fast-flights (scraping).

Copre le compagnie che Ryanair/Wizz non coprono (easyJet, Volotea, Vueling,
ITA...). Google non permette "ovunque", quindi cerca su una lista di
destinazioni da config.yaml, per i prossimi N weekend.

Fa ricerche di sola andata (ven/sab all'andata, dom/lun al ritorno): ognuna
restituisce tutti i voli diretti con orari, così si può scegliere la
combinazione con orari utilizzabili. Per le low cost il prezzo A/R è la
somma delle due tratte.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
from urllib.parse import quote

import fx
from combos import best_combos
from dates import upcoming_fri_sun
from models import Leg, Offer

log = logging.getLogger(__name__)

_PRICE_RE = re.compile(r"([€$£])?\s*([\d.,]+)\s*([€$£])?")
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([AP]M)?", re.I)


def parse_price(text: str) -> float | None:
    """'€58' / '$1,234' / '58 €' -> importo in EUR."""
    m = _PRICE_RE.search(text or "")
    if not m:
        return None
    symbol = m.group(1) or m.group(3) or "€"
    amount = float(m.group(2).replace(",", ""))
    return fx.to_eur(amount, fx.SYMBOLS.get(symbol, "EUR"))


def parse_time(text: str, day: date) -> datetime | None:
    """'8:05 PM on Sat, Jan 16' -> datetime nel giorno `day`."""
    m = _TIME_RE.search(text or "")
    if not m:
        return None
    h, mi, ampm = int(m.group(1)), int(m.group(2)), (m.group(3) or "").upper()
    if ampm == "PM" and h != 12:
        h += 12
    elif ampm == "AM" and h == 12:
        h = 0
    return datetime(day.year, day.month, day.day, h, mi)


def to_legs(flights, day: date) -> list[Leg]:
    legs = []
    for f in flights:
        price = parse_price(f.price)
        dep = parse_time(f.departure, day)
        arr = parse_time(f.arrival, day)
        if f.stops != 0 or not price or not dep or not arr:
            continue
        ahead = re.search(r"\+(\d)", f.arrival_time_ahead or "")
        if ahead:
            arr += timedelta(days=int(ahead.group(1)))
        elif arr < dep:
            arr += timedelta(days=1)
        legs.append(Leg(dep, arr, price, f.name or ""))
    return legs


def destinations(raw) -> dict[str, tuple[str, str]]:
    """Config -> IATA: (città, paese). Accetta lista, 'IATA: nome' o 'IATA: {city, country}'."""
    if isinstance(raw, list):
        return {d: (d, "") for d in raw}
    out = {}
    for iata, v in raw.items():
        if isinstance(v, dict):
            out[iata] = (v.get("city") or iata, (v.get("country") or "").upper())
        else:
            out[iata] = (v or iata, "")
    return out


def search_link(origin: str, dest: str, out_d: date, in_d: date) -> str:
    q = f"Flights from {origin} to {dest} on {out_d.isoformat()} through {in_d.isoformat()} nonstop"
    return f"https://www.google.com/travel/flights?q={quote(q)}&curr=EUR&hl=it"


def _airline(o: Leg, i: Leg) -> str:
    if o.airline == i.airline:
        return o.airline or "Google Flights"
    return f"{o.airline} + {i.airline}"


def fetch(cfg: dict) -> list[Offer]:
    from fast_flights import FlightData, Passengers, create_filter, get_flights_from_filter

    gcfg = cfg["sources"]["google_flights"]
    origin = cfg["origin"]
    sleep = gcfg.get("sleep_seconds", 2)
    offers: list[Offer] = []
    stats = {"total": 0, "errors": 0}
    first_error: list[str] = []

    def one_way(frm: str, to: str, day: date) -> list[Leg]:
        stats["total"] += 1
        try:
            flt = create_filter(
                flight_data=[FlightData(date=day.isoformat(), from_airport=frm, to_airport=to)],
                trip="one-way",
                seat="economy",
                passengers=Passengers(adults=1),
                max_stops=0,
            )
            return to_legs(get_flights_from_filter(flt, currency="EUR", mode="common").flights, day)
        except RuntimeError as e:
            if "No flights found" in str(e):
                return []
            raise_or_count(e)
        except Exception as e:  # noqa: BLE001
            raise_or_count(e)
        finally:
            time.sleep(sleep)
        return []

    def raise_or_count(e: Exception):
        stats["errors"] += 1
        if not first_error:
            first_error.append(f"{type(e).__name__}: {str(e)[:300]}")
        log.debug("Google Flights: %s", e)

    for dest, (city, country) in destinations(gcfg["destinations"]).items():
        for fri, sun in upcoming_fri_sun(gcfg.get("weekends", 6)):
            sat, mon = fri + timedelta(days=1), sun + timedelta(days=1)
            outs = one_way(origin, dest, fri) + one_way(origin, dest, sat)
            if not outs:
                continue  # niente andata, inutile cercare il ritorno
            ins = one_way(dest, origin, sun) + one_way(dest, origin, mon)
            for o, i in best_combos(outs, ins, cfg):
                offers.append(
                    Offer(
                        source="google_flights",
                        airline=_airline(o, i),
                        origin=origin,
                        dest=dest,
                        dest_city=city,
                        out_date=o.dep.date(),
                        in_date=i.dep.date(),
                        price_pp=round(o.price + i.price, 2),
                        link=search_link(origin, dest, o.dep.date(), i.dep.date()),
                        out_dep=o.dep, out_arr=o.arr, in_dep=i.dep, in_arr=i.arr,
                        country_code=country,
                    )
                )
    if stats["total"] and stats["errors"] == stats["total"]:
        raise RuntimeError(f"Google Flights: tutte le {stats['total']} ricerche fallite. Primo errore: {first_error[0]}")
    log.info("Google Flights: %d ricerche, %d errori", stats["total"], stats["errors"])
    return offers
