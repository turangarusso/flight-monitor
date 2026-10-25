"""Wizz Air: API non ufficiale be.wizzair.com.

1. legge la versione corrente dell'API da wizzair.com/buildnumber
2. scarica la mappa rotte e trova le destinazioni servite da NAP
3. per ogni destinazione chiede il calendario prezzi (andata e ritorno)
4. combina andate ven/sab con ritorni dom/lun

Se le richieste dirette vengono bloccate (403/429), riprova da un browser
headless (Playwright) che esegue le stesse chiamate con i cookie del sito.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timedelta

import fx
from dates import is_weekend_trip, search_range, windows
from http_utils import HttpError, make_session, request_json
from models import Offer

log = logging.getLogger(__name__)

SITE = "https://wizzair.com"


class RequestsClient:
    def __init__(self):
        self.s = make_session()
        self.s.headers.update({"Origin": SITE, "Referer": SITE + "/it-it"})

    def text(self, url: str) -> str:
        r = self.s.get(url, timeout=30)
        if r.status_code >= 400:
            raise HttpError(r.status_code, url)
        return r.text

    def json(self, method: str, url: str, body: dict | None = None):
        return request_json(self.s, method, url, json=body)

    def close(self):
        self.s.close()


class BrowserClient:
    """Esegue fetch() dentro una pagina wizzair.com reale."""

    def __init__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._page = self._browser.new_page(locale="it-IT")
        self._page.goto(SITE + "/it-it", wait_until="domcontentloaded", timeout=60000)
        self._page.wait_for_timeout(5000)

    def _fetch(self, method: str, url: str, body: dict | None):
        res = self._page.evaluate(
            """async ([url, method, body]) => {
                const r = await fetch(url, {
                    method,
                    credentials: 'include',
                    headers: body ? {'content-type': 'application/json'} : {},
                    body: body || undefined,
                });
                return {status: r.status, text: await r.text()};
            }""",
            [url, method, json.dumps(body) if body else None],
        )
        if res["status"] >= 400:
            raise HttpError(res["status"], url)
        return res["text"]

    def text(self, url: str) -> str:
        return self._fetch("GET", url, None)

    def json(self, method: str, url: str, body: dict | None = None):
        return json.loads(self._fetch(method, url, body))

    def close(self):
        self._browser.close()
        self._pw.stop()


def api_base(client) -> str:
    text = client.text(SITE + "/buildnumber")
    m = re.search(r"https://be\.wizzair\.com/[\d.]+", text)
    if not m:
        raise RuntimeError(f"Versione API Wizz non trovata in: {text[:200]!r}")
    return m.group(0)


def destinations(route_map: dict, origin: str) -> dict[str, str]:
    """IATA -> nome città delle destinazioni dirette da `origin`."""
    names = {c["iata"]: c.get("shortName") or c["iata"] for c in route_map.get("cities", [])}
    for city in route_map.get("cities", []):
        if city.get("iata") == origin:
            return {c["iata"]: names.get(c["iata"], c["iata"]) for c in city.get("connections", [])}
    return {}


def _daily_prices(flights: list[dict]) -> dict[date, float]:
    """Prezzo minimo per giorno, convertito in EUR."""
    out: dict[date, float] = {}
    for f in flights or []:
        price = f.get("price") or {}
        amount = price.get("amount") or 0
        if amount <= 0 or f.get("priceType") == "soldOut":
            continue
        eur = fx.to_eur(float(amount), price.get("currencyCode", "EUR"))
        if eur is None:
            continue
        d = datetime.fromisoformat(f["departureDate"][:19]).date()
        out[d] = min(eur, out.get(d, eur))
    return out


def combine(dest: str, city: str, timetable: dict, cfg: dict) -> list[Offer]:
    outs = _daily_prices(timetable.get("outboundFlights"))
    rets = _daily_prices(timetable.get("returnFlights"))
    offers = []
    for out_d, p_out in outs.items():
        for in_d, p_in in rets.items():
            if is_weekend_trip(out_d, in_d, cfg):
                offers.append(
                    Offer(
                        source="wizzair",
                        airline="Wizz Air",
                        origin=cfg["origin"],
                        dest=dest,
                        dest_city=city,
                        out_date=out_d,
                        in_date=in_d,
                        price_pp=round(p_out + p_in, 2),
                        link=(
                            f"{SITE}/it-it/booking/select-flight/{cfg['origin']}/{dest}/"
                            f"{out_d.isoformat()}/{in_d.isoformat()}/{cfg['adults']}/0/0/null"
                        ),
                    )
                )
    return offers


def _run(client, cfg: dict) -> list[Offer]:
    base = api_base(client)
    route_map = client.json("GET", f"{base}/Api/asset/map?languageCode=it-it")
    dests = destinations(route_map, cfg["origin"])
    log.info("Wizz Air: %d destinazioni da %s", len(dests), cfg["origin"])
    start, end = search_range(cfg)
    sleep = cfg["sources"]["wizzair"].get("sleep_seconds", 1.5)
    offers: list[Offer] = []
    for dest, city in dests.items():
        for w_start, w_end in windows(start, end, days=30):
            body = {
                "flightList": [
                    {"departureStation": cfg["origin"], "arrivalStation": dest,
                     "from": w_start.isoformat(), "to": w_end.isoformat()},
                    {"departureStation": dest, "arrivalStation": cfg["origin"],
                     "from": w_start.isoformat(),
                     "to": (w_end + timedelta(days=cfg["max_nights"])).isoformat()},
                ],
                "priceType": "regular",
                "adultCount": 1,
                "childCount": 0,
                "infantCount": 0,
            }
            try:
                tt = client.json("POST", f"{base}/Api/search/timetable", body)
            except HttpError as e:
                if e.status in (403, 429):
                    raise
                log.warning("Wizz %s: %s", dest, e)
                continue
            offers += combine(dest, city, tt, cfg)
            time.sleep(sleep)
    return offers


def fetch(cfg: dict) -> list[Offer]:
    client = RequestsClient()
    try:
        return _run(client, cfg)
    except HttpError as e:
        if e.status not in (403, 429) or not cfg["sources"]["wizzair"].get("playwright_fallback"):
            raise
        log.warning("Wizz Air ha bloccato le richieste dirette (%s), uso il browser", e)
    finally:
        client.close()
    browser = BrowserClient()
    try:
        return _run(browser, cfg)
    finally:
        browser.close()
