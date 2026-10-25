"""Decide quali offerte notificare (solo nuove o migliorate)."""

from __future__ import annotations

from dataclasses import dataclass

from dates import is_weekend_trip
from models import Offer


@dataclass
class Alert:
    offer: Offer
    reason: str              # new | drop | record
    drop: float = 0.0        # euro risparmiati rispetto all'ultima notifica


def filter_offers(offers: list[Offer], cfg: dict) -> list[Offer]:
    """Tiene solo weekend sotto soglia e, per ogni volo, il prezzo più basso."""
    best: dict[str, Offer] = {}
    for o in offers:
        if o.price_pp > cfg["thresholds"]["good"] or not is_weekend_trip(o.out_date, o.in_date, cfg):
            continue
        if o.key not in best or o.price_pp < best[o.key].price_pp:
            best[o.key] = o
    return sorted(best.values(), key=lambda o: (o.price_pp, o.out_date))


def select_alerts(offers: list[Offer], state: dict, cfg: dict) -> list[Alert]:
    """Confronta con lo stato e lo aggiorna; restituisce gli avvisi da inviare."""
    min_drop = cfg["alerts"]["min_drop_eur"]
    prev_min = dict(state["dest_min"])
    alerts = []
    for o in offers:
        last = state["offers"].get(o.key)
        record = o.dest in prev_min and o.price_pp < prev_min[o.dest] - 0.01
        alert = None
        if last is None:
            alert = Alert(o, "record" if record else "new")
        elif o.price_pp <= last - min_drop:
            alert = Alert(o, "record" if record else "drop", drop=round(last - o.price_pp, 2))
        elif record:
            alert = Alert(o, "record", drop=round(last - o.price_pp, 2))
        if alert:
            alerts.append(alert)
            state["offers"][o.key] = o.price_pp
        state["dest_min"][o.dest] = min(o.price_pp, state["dest_min"].get(o.dest, o.price_pp))
    return alerts
