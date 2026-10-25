"""Ryanair: API pubblica non ufficiale "farfnd" (pagina Tariffe più basse).

Una chiamata restituisce la tariffa A/R più bassa verso ogni destinazione
nella finestra di date indicata, quindi copre "ovunque".
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta

from dates import DAY_NAMES_EN, search_range, weekdays, windows
from http_utils import make_session, request_json
from models import Offer

API = "https://services-api.ryanair.com/farfnd/v4/roundTripFares"


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


def _to_date(s: str) -> date:
    return datetime.fromisoformat(s[:19]).date()


def parse(data: dict, cfg: dict) -> list[Offer]:
    offers = []
    for fare in data.get("fares") or []:
        out, inn = fare.get("outbound") or {}, fare.get("inbound") or {}
        try:
            arr = out["arrivalAirport"]
            out_d = _to_date(out["departureDate"])
            in_d = _to_date(inn["departureDate"])
            summary = (fare.get("summary") or {}).get("price") or {}
            price = summary.get("value")
            if price is None:
                price = out["price"]["value"] + inn["price"]["value"]
        except (KeyError, TypeError):
            continue
        offers.append(
            Offer(
                source="ryanair",
                airline="Ryanair",
                origin=out.get("departureAirport", {}).get("iataCode", cfg["origin"]),
                dest=arr["iataCode"],
                dest_city=(arr.get("city") or {}).get("name") or arr.get("name") or arr["iataCode"],
                out_date=out_d,
                in_date=in_d,
                price_pp=float(price),
                link=booking_link(cfg["origin"], arr["iataCode"], out_d, in_d, cfg["adults"]),
            )
        )
    return offers


def fetch(cfg: dict) -> list[Offer]:
    s = make_session()
    start, end = search_range(cfg)
    offers: list[Offer] = []
    # Finestre di 2 settimane: l'API dà 1 tariffa per destinazione per finestra,
    # finestre più piccole = più weekend diversi per la stessa destinazione.
    for w_start, w_end in windows(start, end, days=14):
        params = {
            "departureAirportIataCode": cfg["origin"],
            "outboundDepartureDateFrom": w_start.isoformat(),
            "outboundDepartureDateTo": w_end.isoformat(),
            "inboundDepartureDateFrom": w_start.isoformat(),
            "inboundDepartureDateTo": (w_end + timedelta(days=cfg["max_nights"])).isoformat(),
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
        offers += parse(request_json(s, "GET", API, params=params), cfg)
        time.sleep(1)
    return offers
