"""Conversione valute verso EUR (tassi BCE via frankfurter.app, gratuito)."""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

# Usati solo se l'API dei cambi non risponde
FALLBACK_RATES = {
    "EUR": 1.0, "USD": 0.92, "GBP": 1.18, "CHF": 1.06, "HUF": 0.0025,
    "PLN": 0.23, "RON": 0.20, "BGN": 0.51, "CZK": 0.040, "ALL": 0.010,
    "MKD": 0.016, "RSD": 0.0085, "GEL": 0.34, "MDL": 0.052, "BAM": 0.51,
    "NOK": 0.085, "SEK": 0.088, "DKK": 0.134, "TRY": 0.027,
}

SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}

_cache: dict[str, float] = {}


def to_eur(amount: float, currency: str) -> float | None:
    currency = currency.upper()
    if currency == "EUR":
        return amount
    if currency not in _cache:
        try:
            r = requests.get(
                "https://api.frankfurter.app/latest",
                params={"from": currency, "to": "EUR"},
                timeout=15,
            )
            r.raise_for_status()
            _cache[currency] = float(r.json()["rates"]["EUR"])
        except Exception as e:  # noqa: BLE001
            rate = FALLBACK_RATES.get(currency)
            if rate is None:
                log.warning("Valuta %s sconosciuta (%s)", currency, e)
                return None
            _cache[currency] = rate
    return amount * _cache[currency]
