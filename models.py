"""Formato comune delle offerte restituite da tutte le fonti."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime


@dataclass
class Leg:
    """Un singolo volo (andata o ritorno), orari locali."""
    dep: datetime
    arr: datetime
    price: float         # a persona, in EUR
    airline: str = ""


@dataclass
class Offer:
    source: str          # ryanair | wizzair | google_flights
    airline: str         # nome compagnia mostrato nel messaggio
    origin: str          # IATA partenza
    dest: str            # IATA arrivo
    dest_city: str       # nome città
    out_date: date       # data volo di andata
    in_date: date        # data volo di ritorno
    price_pp: float      # prezzo A/R a persona, in EUR
    link: str            # link di prenotazione / ricerca
    out_dep: datetime | None = None
    out_arr: datetime | None = None
    in_dep: datetime | None = None
    in_arr: datetime | None = None
    country_code: str = ""   # ISO2 del paese di destinazione, es. "FR"

    @property
    def key(self) -> str:
        return f"{self.airline}|{self.dest}|{self.out_date.isoformat()}|{self.in_date.isoformat()}"

    @property
    def nights(self) -> int:
        return (self.in_date - self.out_date).days

    @property
    def hours_at_dest(self) -> float | None:
        if self.out_arr and self.in_dep:
            return (self.in_dep - self.out_arr).total_seconds() / 3600
        return None

    def as_row(self) -> dict:
        row = asdict(self)
        for k, v in row.items():
            if isinstance(v, (date, datetime)):
                row[k] = v.isoformat()
            elif v is None:
                row[k] = ""
        row["price_pp"] = round(self.price_pp, 2)
        return row
