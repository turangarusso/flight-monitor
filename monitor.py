"""Monitor voli weekend low-cost: cerca, salva lo storico, avvisa su Telegram.

Uso:
    python monitor.py                       # tutte le fonti abilitate
    python monitor.py --sources ryanair,wizzair
    python monitor.py --dry-run             # stampa il messaggio, non invia e non salva
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
import traceback
from pathlib import Path

import yaml

import notify
import storage
from alerts import filter_offers, select_alerts

ROOT = Path(__file__).parent
NAMES = {"ryanair": "Ryanair", "wizzair": "Wizz Air", "google_flights": "Google Flights"}

log = logging.getLogger("monitor")


def load_config(path: Path = ROOT / "config.yaml") -> dict:
    return yaml.safe_load(path.read_text("utf-8"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sources", default="all", help="es. ryanair,wizzair (default: all)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--digest", action="store_true",
                   help="invia anche il riepilogo delle migliori offerte valide")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = load_config()
    enabled = [n for n, c in cfg["sources"].items() if c.get("enabled")]
    wanted = enabled if args.sources == "all" else [s.strip() for s in args.sources.split(",")]

    # salva anche gli avvisi non fatali delle fonti (es. fallback attivati) in last_errors.txt
    source_warnings: list[str] = []
    handler = logging.Handler(logging.WARNING)
    handler.emit = lambda r: source_warnings.append(f"{r.name}: {r.getMessage()}")
    logging.getLogger("sources").addHandler(handler)

    state = storage.load_state()
    offers, warnings, errors = [], [], {}
    refreshed: set[str] = set()
    for name in wanted:
        try:
            found = importlib.import_module(f"sources.{name}").fetch(cfg)
            log.info("%s: %d tariffe", name, len(found))
            offers += found
            state["failures"][name] = 0
            refreshed.add(name)
        except Exception as e:  # noqa: BLE001 - una fonte rotta non blocca le altre
            log.exception("%s fallita", name)
            errors[name] = traceback.format_exc(limit=4)
            fails = state["failures"].get(name, 0) + 1
            state["failures"][name] = fails
            if fails >= cfg["alerts"]["failure_alert_after"]:
                warnings.append(f"{NAMES.get(name, name)} non funziona da {fails} run: {e}")

    offers = filter_offers(offers, cfg)
    alerts = select_alerts(offers, state, cfg)
    log.info("%d offerte sotto soglia, %d da notificare", len(offers), len(alerts))

    # avvisa sugli errori solo la prima volta che si supera la soglia, o insieme a offerte
    first_warning = any(
        state["failures"][n] == cfg["alerts"]["failure_alert_after"] for n in wanted
    )
    messages = notify.build_messages(alerts, cfg, warnings if (alerts or first_warning) else [])
    if args.digest:
        messages += notify.build_digest(offers, cfg)

    if args.dry_run:
        print("\n---\n".join(messages) or "(nessun messaggio)")
        return 0

    storage.append_prices(offers)
    storage.write_latest(offers, refreshed, cfg["adults"])
    if source_warnings:
        errors["avvisi"] = "\n".join(dict.fromkeys(source_warnings))
    storage.write_errors(errors)
    if messages:
        notify.send(messages)
    storage.save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
