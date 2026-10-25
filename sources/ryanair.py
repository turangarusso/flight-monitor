"""Ryanair.

1. Scoperta: API "farfnd" (pagina Tariffe più basse), una chiamata per
   weekend restituisce la tariffa A/R più bassa verso ogni destinazione.
2. Dettaglio: per ogni destinazione + weekend sotto soglia, l'API di
   disponibilità restituisce tutti i voli con orari e posti per 2 persone,
   così si trova il volo più economico con orari utilizzabili.
   Se la disponibilità è bloccata si usano gli orari della tariffa trovata.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta

from combos import best_combos
from dates import DAY_NAMES_EN, fridays, search_range, weekdays
from http_utils import make_session, request_json
from models import Leg, Offer

log = logging.getLogger(__name__)

FARES_API = "https://services-api.ryanair.com/farfnd/v4/roundTripFares"
AVAIL_API = "https://www.ryanair.com/api/booking/v4/it-it/availability"


def booking_link(origin: str, dest: str, out_d: date, in_d: date, adults: int) -> str:
    return (
        "https://www.ryanair.com/it/it/trip/flights/select"
        f"?adults={adults}&teens=0&children=0&infants=0"
        f"&dateOut={out_d.isoformat()}&dateIn={in_d.isoformat()}"
        "&isConnectedFlight=false&isReturn=true&discount=0"
        f"&originIata={origin}&destinationIata={dest}"
        f"&tpAdults={adults}&tpTeens=0&tpChildren=0&tpInfants=0"
        f"&tpStartDate={out_d.isoformat()}&tpEndDate={in_d.isoformat()}"
        f"&tpOriginIata={origin}&tpDestinationIata={dest}"
    )


def _day_names(codes: list[str]) -> str:
    return ",".join(DAY_NAMES_EN[d] for d in sorted(weekdays(codes)))


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s[:19])


def parse_fares(data: dict) -> list[dict]:
    """Tariffe farfnd -> dict con destinazione, città e le due tratte."""
    found = []
    for fare in data.get("fares") or []:
        out, inn = fare.get("outbound") or {}, fare.get("inbound") or {}
        try:
            arr = out["arrivalAirport"]
            out_leg = Leg(_dt(out["departureDate"]), _dt(out["arrivalDate"]), float(out["price"]["value"]))
            in_leg = Leg(_dt(inn["departureDate"]), _dt(inn["arrivalDate"]), float(inn["price"]["value"]))
        except (KeyError, TypeError, ValueError):
            continue
        found.append({
            "dest": arr["iataCode"],
            "city": (arr.get("city") or {}).get("name") or arr.get("name") or arr["iataCode"],
            "out": out_leg,
            "in": in_leg,
        })
    return found


def parse_availability(data: dict, min_seats: int) -> tuple[list[Leg], list[Leg]]:
    """Risposta availability -> (voli di andata, voli di ritorno)."""
    trips = []
    for trip in (data.get("trips") or [])[:2]:
        legs = []
        for day in trip.get("dates") or []:
            for f in day.get("flights") or []:
                fares = (f.get("regularFare") or {}).get("fares") or []
                left = f.get("faresLeft", -1)
                if not fares or not f.get("time") or (0 <= left < min_seats):
                    continue
                legs.append(Leg(_dt(f["time"][0]), _dt(f["time"][1]), float(fares[0]["amount"]), "Ryanair"))
        trips.append(legs)
    while len(trips) < 2:
        trips.append([])
    return trips[0], trips[1]


def to_offers(dest: str, city: str, combos, cfg: dict) -> list[Offer]:
    return [
        Offer(
            source="ryanair",
            airline="Ryanair",
            origin=cfg["origin"],
            dest=dest,
            dest_city=city,
            out_date=o.dep.date(),
            in_date=i.dep.date(),
            price_pp=round(o.price + i.price, 2),
            link=booking_link(cfg["origin"], dest, o.dep.date(), i.dep.date(), cfg["adults"]),
            out_dep=o.dep, out_arr=o.arr, in_dep=i.dep, in_arr=i.arr,
        )
        for o, i in combos
    ]


def _availability(s, cfg: dict, dest: str, fri: date):
    params = {
        "ADT": cfg["adults"], "TEEN": 0, "CHD": 0, "INF": 0,
        "Origin": cfg["origin"], "Destination": dest,
        "DateOut": fri.isoformat(), "DateIn": (fri + timedelta(days=2)).isoformat(),
        "FlexDaysBeforeOut": 0, "FlexDaysOut": 1, "FlexDaysBeforeIn": 0, "FlexDaysIn": 1,
        "RoundTrip": "true", "IncludeConnectingFlights": "false", "Disc": 0,
        "promoCode": "", "ToUs": "AGREED",
    }
    return request_json(s, "GET", AVAIL_API, retries=2, params=params)


def fetch(cfg: dict) -> list[Offer]:
    s = make_session()
    start, end = search_range(cfg)
    offers: list[Offer] = []
    avail_ok = True
    try:
        s.get("https://www.ryanair.com/it/it", timeout=30)  # cookie di sessione
    except Exception:  # noqa: BLE001
        pass
    for fri in fridays(start, end):
        params = {
            "departureAirportIataCode": cfg["origin"],
            "outboundDepartureDateFrom": fri.isoformat(),
            "outboundDepartureDateTo": (fri + timedelta(days=1)).isoformat(),
            "inboundDepartureDateFrom": (fri + timedelta(days=2)).isoformat(),
            "inboundDepartureDateTo": (fri + timedelta(days=3)).isoformat(),
            "outboundDepartureDaysOfWeek": _day_names(cfg["outbound_days"]),
            "inboundDepartureDaysOfWeek": _day_names(cfg["inbound_days"]),
            "durationFrom": cfg["min_nights"],
            "durationTo": cfg["max_nights"],
            "adultPaxCount": 1,
            "market": "it-it",
            "currency": "EUR",
            "searchMode": "ALL",
            "priceValueTo": cfg["thresholds"]["good"],
        }
        for fare in parse_fares(request_json(s, "GET", FARES_API, params=params)):
            combos = None
            if avail_ok:
                try:
                    outs, ins = parse_availability(_availability(s, cfg, fare["dest"], fri), cfg["adults"])
                    combos = best_combos(outs, ins, cfg)
                except Exception as e:  # noqa: BLE001
                    log.warning("Ryanair availability non disponibile (%s): uso solo le tariffe minime", e)
                    avail_ok = False
                time.sleep(1)
            if combos is None:
                combos = best_combos([fare["out"]], [fare["in"]], cfg)
            offers += to_offers(fare["dest"], fare["city"], combos, cfg)
        time.sleep(1)
    return offers
