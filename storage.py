"""Storico prezzi (CSV) e stato degli avvisi (JSON) in data/."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path

from models import Offer

DATA = Path(__file__).parent / "data"
PRICES = DATA / "prices.csv"
STATE = DATA / "alerted.json"

FIELDS = ["checked_at", "source", "airline", "origin", "dest", "dest_city",
          "out_date", "in_date", "price_pp", "link"]


def append_prices(offers: list[Offer], path: Path | None = None) -> None:
    path = path or PRICES
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for o in offers:
            w.writerow({"checked_at": now, **o.as_row()})


def load_state(path: Path | None = None) -> dict:
    path = path or STATE
    state = json.loads(path.read_text("utf-8")) if path.exists() else {}
    state.setdefault("offers", {})     # chiave offerta -> ultimo prezzo notificato
    state.setdefault("dest_min", {})   # destinazione -> prezzo minimo mai visto
    state.setdefault("failures", {})   # fonte -> run falliti consecutivi
    return state


def save_state(state: dict, path: Path | None = None, today: date | None = None) -> None:
    path = path or STATE
    today = (today or date.today()).isoformat()
    # rimuove le offerte con partenza già passata
    state["offers"] = {k: v for k, v in state["offers"].items() if k.split("|")[2] >= today}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n", "utf-8")
