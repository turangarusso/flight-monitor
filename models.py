"""Formato comune delle offerte restituite da tutte le fonti."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date


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

    @property
    def key(self) -> str:
        return f"{self.airline}|{self.dest}|{self.out_date.isoformat()}|{self.in_date.isoformat()}"

    @property
    def nights(self) -> int:
        return (self.in_date - self.out_date).days

    def as_row(self) -> dict:
        row = asdict(self)
        row["out_date"] = self.out_date.isoformat()
        row["in_date"] = self.in_date.isoformat()
        row["price_pp"] = round(self.price_pp, 2)
        return row
