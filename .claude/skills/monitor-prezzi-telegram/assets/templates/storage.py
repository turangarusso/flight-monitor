"""Dati in data/ (committati dal workflow): stato anti-spam, latest.json per il bot, errori."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).parent / "data"
STATE = DATA / "state.json"
LATEST = DATA / "latest.json"
ERRORS = DATA / "last_errors.txt"


def load_state() -> dict:
    state = json.loads(STATE.read_text("utf-8")) if STATE.exists() else {}
    state.setdefault("notified", {})   # chiave elemento -> ultimo prezzo notificato
    state.setdefault("failures", {})   # fonte -> run falliti consecutivi
    return state


def save_state(state: dict) -> None:
    DATA.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n", "utf-8")


def to_notify(items, state: dict, min_drop: float) -> list:
    """Anti-spam: solo elementi nuovi o scesi di almeno min_drop."""
    out = []
    for i in items:
        last = state["notified"].get(i.key)
        if last is None or i.price <= last - min_drop:
            out.append(i)
            state["notified"][i.key] = i.price
    return out


def write_latest(rows: list[dict], refreshed: set[str]) -> None:
    """Elementi validi per il bot; le fonti non aggiornate in questo run mantengono i dati precedenti."""
    old = json.loads(LATEST.read_text("utf-8")).get("items", []) if LATEST.exists() else []
    keep = [r for r in old if r.get("source") not in refreshed]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    DATA.mkdir(exist_ok=True)
    LATEST.write_text(json.dumps({"updated": now, "items": rows + keep}, ensure_ascii=False, indent=1) + "\n", "utf-8")


def write_errors(errors: dict[str, str]) -> None:
    """Errori e avvisi del run: Claude li legge dal repo (i log di Actions spesso non sono accessibili)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = "".join(f"[{k}]\n{v}\n\n" for k, v in errors.items()) or "Nessun errore\n"
    DATA.mkdir(exist_ok=True)
    ERRORS.write_text(f"Run del {now}\n\n{body}", "utf-8")
