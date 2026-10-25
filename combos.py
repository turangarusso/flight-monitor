"""Combina voli di andata e ritorno rispettando le regole sugli orari."""

from __future__ import annotations

from datetime import date, time

from dates import DAY_CODES, is_weekend_trip
from models import Leg

_CODES = {v: k for k, v in DAY_CODES.items()}


def _hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def valid_trip(out: Leg, inn: Leg, cfg: dict) -> bool:
    """Weekend valido: date giuste, ore minime sul posto, fasce orarie."""
    if not is_weekend_trip(out.dep.date(), inn.dep.date(), cfg):
        return False
    rules = cfg.get("time_rules") or {}
    hours = (inn.dep - out.arr).total_seconds() / 3600
    if hours < rules.get("min_hours_at_destination", 0):
        return False
    arrive_by = (rules.get("outbound_arrive_by") or {}).get(_CODES[out.dep.weekday()])
    if arrive_by and (out.arr.date() > out.dep.date() or out.arr.time() > _hhmm(arrive_by)):
        return False
    depart_after = (rules.get("inbound_depart_after") or {}).get(_CODES[inn.dep.weekday()])
    if depart_after and inn.dep.time() < _hhmm(depart_after):
        return False
    return True


def best_combos(outs: list[Leg], ins: list[Leg], cfg: dict) -> list[tuple[Leg, Leg]]:
    """Per ogni coppia di date (andata, ritorno) la combinazione valida più economica."""
    best: dict[tuple[date, date], tuple[Leg, Leg]] = {}
    for o in outs:
        for i in ins:
            if not valid_trip(o, i, cfg):
                continue
            k = (o.dep.date(), i.dep.date())
            if k not in best or o.price + i.price < best[k][0].price + best[k][1].price:
                best[k] = (o, i)
    return list(best.values())
