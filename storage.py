"""Storico prezzi (CSV) e stato degli avvisi (JSON) in data/."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path

from airports import COUNTRY_IT, flag
from models import Offer

DATA = Path(__file__).parent / "data"
PRICES = DATA / "prices.csv"
STATE = DATA / "alerted.json"

ERRORS = DATA / "last_errors.txt"
LATEST = DATA / "latest.json"

FIELDS = ["checked_at", "source", "airline", "origin", "dest", "dest_city",
          "out_date", "in_date", "price_pp", "link", "out_dep", "out_arr", "in_dep", "in_arr"]


def append_prices(offers: list[Offer], path: Path | None = None) -> None:
    path = path or PRICES
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with path.open(encoding="utf-8") as f:
            header = f.readline().strip().split(",")
        if header != FIELDS:
            # formato vecchio: lo archivia e ricomincia
            path.rename(path.with_name(path.stem + "_v1" + path.suffix))
    new = not path.exists()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for o in offers:
            w.writerow({"checked_at": now, **o.as_row()})


def write_latest(offers: list[Offer], refreshed: set[str], adults: int = 2,
                 path: Path | None = None, today: date | None = None,
                 stays: dict[str, dict] | None = None) -> None:
    """Offerte valide attuali, lette dal bot Telegram (/voli, /top, /paese).

    Le fonti non aggiornate in questo run (non eseguite o fallite) mantengono
    le offerte precedenti, tranne quelle con partenza già passata.
    """
    path = path or LATEST
    today_s = (today or date.today()).isoformat()
    old = json.loads(path.read_text("utf-8")).get("offers", []) if path.exists() else []
    keep = [r for r in old if r.get("source") not in refreshed and r.get("out_date", "") >= today_s]
    rows = []
    for o in offers:
        row = o.as_row()
        row["country_name"] = COUNTRY_IT.get(o.country_code, "")
        row["flag"] = flag(o.country_code)
        row.update((stays or {}).get(o.key, {}))  # hotel / appartamento del pacchetto
        rows.append(row)
    rows = sorted(rows + keep, key=lambda r: (r["price_pp"], r["out_date"]))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"updated": now, "adults": adults, "offers": rows}, ensure_ascii=False, indent=1) + "\n", "utf-8")


def write_errors(errors: dict[str, str], path: Path | None = None) -> None:
    """Ultimi errori per fonte, leggibili dal repo senza aprire i log di Actions."""
    path = path or ERRORS
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = "".join(f"[{name}]\n{err}\n\n" for name, err in errors.items()) or "Nessun errore\n"
    path.write_text(f"Run del {now}\n\n{body}", "utf-8")


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
