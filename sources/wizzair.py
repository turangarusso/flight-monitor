"""Wizz Air: API non ufficiale be.wizzair.com.

1. legge la versione corrente dell'API da wizzair.com/buildnumber
2. scarica la mappa rotte e trova le destinazioni servite da NAP
3. per ogni destinazione chiede il calendario prezzi (andata e ritorno)
   e trova i weekend con prezzo minimo sotto soglia
4. per quei weekend chiede tutti i voli con orari (search/search) e
   sceglie la combinazione più economica con orari utilizzabili

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
from combos import best_combos
from dates import is_weekend_trip, search_range, windows
from http_utils import HttpError, make_session, request_json
from models import Leg, Offer

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


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s[:19])


def _eur(price: dict | None) -> float | None:
    if not price or not price.get("amount") or price["amount"] <= 0:
        return None
    return fx.to_eur(float(price["amount"]), price.get("currencyCode", "EUR"))


def timetable_legs(flights: list[dict], est_hours: float) -> list[Leg]:
    """Calendario -> un volo per giorno al prezzo minimo.

    Il calendario non dà l'orario di arrivo: lo stima con la durata media.
    """
    legs = []
    for f in flights or []:
        eur = _eur(f.get("price"))
        if eur is None or f.get("priceType") == "soldOut":
            continue
        times = f.get("departureDates") or [f["departureDate"]]
        for t in times:
            dep = _dt(t)
            legs.append(Leg(dep, dep + timedelta(hours=est_hours), eur, "Wizz Air"))
    return legs


def search_legs(flights: list[dict]) -> list[Leg]:
    """Risposta search/search -> tutti i voli con la tariffa base più bassa (no WDC)."""
    legs = []
    for f in flights or []:
        prices = []
        for fare in f.get("fares") or []:
            if fare.get("wdc") or (fare.get("bundle") or "basic").lower() != "basic":
                continue
            eur = _eur(fare.get("discountedPrice")) or _eur(fare.get("basePrice"))
            if eur is not None:
                prices.append(eur)
        if prices and f.get("departureDateTime") and f.get("arrivalDateTime"):
            legs.append(Leg(_dt(f["departureDateTime"]), _dt(f["arrivalDateTime"]), min(prices), "Wizz Air"))
    return legs


def candidate_weekends(timetable: dict, cfg: dict) -> list[date]:
    """Venerdì dei weekend in cui il prezzo minimo A/R è sotto soglia (orari esclusi)."""
    outs = timetable_legs(timetable.get("outboundFlights"), 0)
    ins = timetable_legs(timetable.get("returnFlights"), 0)
    good = cfg["thresholds"]["good"]
    out = set()
    for o in outs:
        for i in ins:
            if o.price + i.price <= good and is_weekend_trip(o.dep.date(), i.dep.date(), cfg):
                out.add(o.dep.date() - timedelta(days=(o.dep.weekday() - 4) % 7))
    return sorted(out)


def to_offers(dest: str, city: str, combos, cfg: dict) -> list[Offer]:
    return [
        Offer(
            source="wizzair",
            airline="Wizz Air",
            origin=cfg["origin"],
            dest=dest,
            dest_city=city,
            out_date=o.dep.date(),
            in_date=i.dep.date(),
            price_pp=round(o.price + i.price, 2),
            link=(
                f"{SITE}/it-it/booking/select-flight/{cfg['origin']}/{dest}/"
                f"{o.dep.date().isoformat()}/{i.dep.date().isoformat()}/{cfg['adults']}/0/0/null"
            ),
            out_dep=o.dep, out_arr=o.arr, in_dep=i.dep, in_arr=i.arr,
        )
        for o, i in combos
    ]


def _search(client, base: str, cfg: dict, dest: str, out_d: date, in_d: date):
    body = {
        "isFlightChange": False,
        "flightList": [
            {"departureStation": cfg["origin"], "arrivalStation": dest, "departureDate": out_d.isoformat()},
            {"departureStation": dest, "arrivalStation": cfg["origin"], "departureDate": in_d.isoformat()},
        ],
        "adultCount": cfg["adults"],
        "childCount": 0,
        "infantCount": 0,
        "wdc": False,
    }
    return client.json("POST", f"{base}/Api/search/search", body)


def _run(client, cfg: dict) -> list[Offer]:
    wcfg = cfg["sources"]["wizzair"]
    base = api_base(client)
    route_map = client.json("GET", f"{base}/Api/asset/map?languageCode=it-it")
    dests = destinations(route_map, cfg["origin"])
    log.info("Wizz Air: %d destinazioni da %s", len(dests), cfg["origin"])
    start, end = search_range(cfg)
    sleep = wcfg.get("sleep_seconds", 1.5)
    search_ok = True
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
            time.sleep(sleep)
            for fri in candidate_weekends(tt, cfg):
                combos = None
                if search_ok:
                    try:
                        outs, ins = [], []
                        # (ven, dom) e (sab, lun) coprono tutti e 4 i giorni del weekend
                        for d_out, d_in in ((fri, fri + timedelta(days=2)),
                                            (fri + timedelta(days=1), fri + timedelta(days=3))):
                            res = _search(client, base, cfg, dest, d_out, d_in)
                            outs += search_legs(res.get("outboundFlights"))
                            ins += search_legs(res.get("returnFlights"))
                            time.sleep(sleep)
                        combos = best_combos(outs, ins, cfg)
                    except Exception as e:  # noqa: BLE001
                        log.warning("Wizz search non disponibile (%s): uso il calendario", e)
                        search_ok = False
                if combos is None:
                    est = wcfg.get("estimated_flight_hours", 3)
                    combos = best_combos(
                        timetable_legs(tt.get("outboundFlights"), est),
                        timetable_legs(tt.get("returnFlights"), est),
                        cfg,
                    )
                    combos = [c for c in combos if fri <= c[0].dep.date() <= fri + timedelta(days=1)]
                offers += to_offers(dest, city, combos, cfg)
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
