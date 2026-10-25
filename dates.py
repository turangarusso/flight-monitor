"""Utility per finestre di date e weekend."""

from __future__ import annotations

from datetime import date, timedelta

DAY_CODES = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}
DAY_NAMES_EN = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
DAY_NAMES_IT = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def weekdays(codes: list[str]) -> set[int]:
    return {DAY_CODES[c.upper()[:3]] for c in codes}


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    # giorno limitato all'ultimo giorno del mese
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise ValueError(d)


def windows(start: date, end: date, days: int = 30) -> list[tuple[date, date]]:
    """Spezza [start, end] in finestre consecutive di `days` giorni."""
    out = []
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=days - 1), end)
        out.append((cur, stop))
        cur = stop + timedelta(days=1)
    return out


def is_weekend_trip(out_d: date, in_d: date, cfg: dict) -> bool:
    nights = (in_d - out_d).days
    return (
        out_d.weekday() in weekdays(cfg["outbound_days"])
        and in_d.weekday() in weekdays(cfg["inbound_days"])
        and cfg["min_nights"] <= nights <= cfg["max_nights"]
    )


def search_range(cfg: dict, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    return today + timedelta(days=1), add_months(today, cfg["months_ahead"])


def fridays(start: date, end: date) -> list[date]:
    """Tutti i venerdì tra start ed end (i weekend da controllare)."""
    first = start + timedelta(days=(4 - start.weekday()) % 7)
    out = []
    while first <= end:
        out.append(first)
        first += timedelta(weeks=1)
    return out


def upcoming_fri_sun(n: int, today: date | None = None) -> list[tuple[date, date]]:
    """I prossimi `n` weekend come coppie (venerdì, domenica)."""
    today = today or date.today()
    days_to_fri = (4 - today.weekday()) % 7 or 7
    first = today + timedelta(days=days_to_fri)
    return [(first + timedelta(weeks=i), first + timedelta(weeks=i, days=2)) for i in range(n)]


def fmt_it(d: date) -> str:
    return f"{DAY_NAMES_IT[d.weekday()]} {d.day:02d}/{d.month:02d}"
