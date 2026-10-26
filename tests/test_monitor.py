import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

import fx
import monitor
import notify
import packages
import storage
from airports import country_label
from alerts import filter_offers, select_alerts
from dates import is_weekend_trip, upcoming_fri_sun, windows
from combos import best_combos, valid_trip
from models import Leg, Offer
from sources import google_flights, ryanair, wizzair
from sources import hotels as hotel_src

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def cfg():
    return monitor.load_config()


@pytest.fixture(autouse=True)
def no_network_fx(monkeypatch):
    monkeypatch.setattr(fx, "_cache", {"HUF": 0.0025, "USD": 0.9})


def offer(price, dest="BCN", out=date(2026, 11, 13), inn=date(2026, 11, 15), airline="Ryanair"):
    return Offer("ryanair", airline, "NAP", dest, dest, out, inn, price, "https://x")


def empty_state():
    return {"offers": {}, "dest_min": {}, "failures": {}}


def test_windows_cover_range():
    w = windows(date(2026, 1, 1), date(2026, 3, 1), days=30)
    assert w[0][0] == date(2026, 1, 1) and w[-1][1] == date(2026, 3, 1)
    assert all((b - a).days < 30 for a, b in w)


def test_weekend_rules(cfg):
    assert is_weekend_trip(date(2026, 11, 13), date(2026, 11, 15), cfg)      # ven→dom
    assert is_weekend_trip(date(2026, 11, 14), date(2026, 11, 16), cfg)      # sab→lun
    assert not is_weekend_trip(date(2026, 11, 18), date(2026, 11, 22), cfg)  # mer→dom
    assert not is_weekend_trip(date(2026, 11, 13), date(2026, 11, 23), cfg)  # troppo lungo


def test_upcoming_fri_sun():
    weekends = upcoming_fri_sun(3, today=date(2026, 10, 25))  # domenica
    assert weekends[0] == (date(2026, 10, 30), date(2026, 11, 1))
    assert len(weekends) == 3


def L(dep, arr, price):
    return Leg(datetime.fromisoformat(dep), datetime.fromisoformat(arr), price)


def test_screenshot_case_rejected(cfg):
    # sab 20:05 -> 22:00, ritorno dom 06:00: solo 8 ore a Londra
    assert not valid_trip(L("2027-01-16T20:05", "2027-01-16T22:00", 25),
                          L("2027-01-17T06:00", "2027-01-17T09:40", 30), cfg)


def test_good_times_accepted(cfg):
    out = L("2027-01-16T08:30", "2027-01-16T10:25", 20)
    assert valid_trip(out, L("2027-01-17T19:40", "2027-01-17T23:20", 19), cfg)        # 33 h
    assert not valid_trip(out, L("2027-01-17T13:00", "2027-01-17T15:00", 19), cfg)   # ritorno troppo presto
    late = L("2027-01-16T13:00", "2027-01-16T15:00", 20)                              # sab atterra dopo le 14
    assert not valid_trip(late, L("2027-01-18T07:00", "2027-01-18T09:00", 19), cfg)
    fri_night = L("2027-01-15T21:00", "2027-01-15T23:00", 20)
    assert valid_trip(fri_night, L("2027-01-17T19:00", "2027-01-17T21:00", 19), cfg)
    after_midnight = L("2027-01-15T23:00", "2027-01-16T01:00", 20)
    assert not valid_trip(after_midnight, L("2027-01-17T19:00", "2027-01-17T21:00", 19), cfg)


def test_best_combo_skips_cheap_bad_flight(cfg):
    outs = [L("2027-01-16T20:05", "2027-01-16T22:00", 9), L("2027-01-16T07:00", "2027-01-16T09:00", 30)]
    ins = [L("2027-01-17T06:00", "2027-01-17T08:00", 5), L("2027-01-17T19:00", "2027-01-17T21:00", 20)]
    (o, i), = best_combos(outs, ins, cfg)
    assert (o.price, i.price) == (30, 20)


def test_ryanair_fares_fallback_filters_times(cfg):
    fares = ryanair.parse_fares(json.loads((FIX / "ryanair_sample.json").read_text()))
    assert [f["dest"] for f in fares] == ["LTN", "BCN"]  # la tariffa malformata viene ignorata
    valid = {f["dest"]: best_combos([f["out"]], [f["in"]], cfg) for f in fares}
    assert valid["LTN"] == []          # il caso dello screenshot
    assert len(valid["BCN"]) == 1      # ven 18:30 -> dom 21:10


def test_ryanair_availability_picks_good_flights(cfg):
    data = json.loads((FIX / "ryanair_availability_sample.json").read_text())
    outs, ins = ryanair.parse_availability(data, min_seats=2)
    assert len(outs) == 2 and len(ins) == 2   # esclusi: 1 solo posto, esaurito
    offers = ryanair.to_offers("LTN", "Londra", best_combos(outs, ins, cfg), cfg)
    (o,) = offers
    assert o.price_pp == pytest.approx(59.99)
    assert (o.out_dep.hour, o.in_dep.hour) == (7, 19)
    assert "adults=2" in o.link and "destinationIata=LTN" in o.link


def test_wizz_search_legs(cfg):
    data = json.loads((FIX / "wizz_search_sample.json").read_text())
    outs = wizzair.search_legs(data["outboundFlights"])
    ins = wizzair.search_legs(data["returnFlights"])
    assert outs[0].price == pytest.approx(29.99)   # non usa la tariffa WDC né i bundle
    assert ins[0].price == pytest.approx(20)       # 8000 HUF
    (o,) = wizzair.to_offers("BUD", "Budapest", best_combos(outs, ins, cfg), cfg)
    assert o.price_pp == pytest.approx(49.99) and o.hours_at_dest == 31


def test_wizz_timetable_candidates_and_fallback(cfg):
    tt = json.loads((FIX / "wizz_timetable_sample.json").read_text())
    assert wizzair.candidate_weekends(tt, cfg) == [date(2026, 11, 13)]
    combos = best_combos(wizzair.timetable_legs(tt["outboundFlights"], 3),
                         wizzair.timetable_legs(tt["returnFlights"], 3), cfg)
    # ven 19:00 (+3h) -> dom 18:00 = 44 h ok; sab 08:00 -> lun 07:00 ok; sab -> dom 18:00 = 31 h ok
    assert {(o.dep.day, i.dep.day) for o, i in combos} == {(13, 15), (14, 15), (14, 16), (13, 16)}


def test_wizz_destinations_and_version():
    route_map = {"cities": [
        {"iata": "NAP", "shortName": "Napoli", "connections": [{"iata": "BUD"}, {"iata": "TIA"}, {"iata": "VCX"}]},
        {"iata": "BUD", "shortName": "Budapest", "countryCode": "hu", "connections": []},
        {"iata": "VCE", "shortName": "Venezia", "connections": []},
        {"iata": "VCX", "shortName": "Venezia (tutti gli aeroporti)", "connections": []},
    ]}
    assert wizzair.destinations(route_map, "NAP") == {"BUD": ("Budapest", "HU"), "TIA": ("TIA", "")}

    class Fake:
        def text(self, url):
            return "SSR https://be.wizzair.com/27.3.0 "

    assert wizzair.api_base(Fake()) == "https://be.wizzair.com/27.3.0"

    class NotFound:
        def text(self, url):
            raise wizzair.HttpError(404, url)

    with pytest.raises(wizzair.VersionNotFound) as e:   # 403 -> passa al browser
        wizzair.api_base(NotFound())
    assert e.value.status == 403


def test_google_price_parse():
    assert google_flights.parse_price("€58") == 58
    assert google_flights.parse_price("$100") == pytest.approx(90)
    assert google_flights.parse_price("1,234 €") == 1234
    assert google_flights.parse_price("") is None


def test_google_times():
    day = date(2027, 1, 16)
    assert google_flights.parse_time("8:05 PM on Sat, Jan 16", day) == datetime(2027, 1, 16, 20, 5)
    assert google_flights.parse_time("12:10 AM on Sun, Jan 17", day) == datetime(2027, 1, 16, 0, 10)

    class F:
        def __init__(self, dep, arr, ahead="", stops=0):
            self.price, self.departure, self.arrival = "€20", dep, arr
            self.arrival_time_ahead, self.stops, self.name = ahead, stops, "easyJet"

    legs = google_flights.to_legs([F("11:30 PM", "1:20 AM", "+1"), F("9:00 AM", "11:00 AM", stops=1)], day)
    assert len(legs) == 1 and legs[0].arr == datetime(2027, 1, 17, 1, 20)


def test_filter_dedup_and_threshold(cfg):
    offers = [offer(30), offer(28), offer(70, dest="LGW"),
              offer(20, out=date(2026, 11, 18), inn=date(2026, 11, 20))]
    kept = filter_offers(offers, cfg)
    assert [o.price_pp for o in kept] == [28]


def test_alerts_no_spam(cfg):
    state = empty_state()
    assert [a.reason for a in select_alerts([offer(30)], state, cfg)] == ["new"]
    assert select_alerts([offer(30)], state, cfg) == []         # stesso prezzo: niente
    assert select_alerts([offer(32)], state, cfg) == []         # aumento: niente
    a = select_alerts([offer(26)], state, cfg)                  # -4 €: notifica
    assert a[0].drop == 4 and a[0].reason == "record"
    other_weekend = offer(40, out=date(2026, 11, 20), inn=date(2026, 11, 22))
    assert [a.reason for a in select_alerts([other_weekend], state, cfg)] == ["new"]


def test_messages_split_italy_and_group(cfg):
    state = empty_state()
    alerts = select_alerts([
        offer(25), offer(35, out=date(2026, 11, 20), inn=date(2026, 11, 22)),
        offer(55, dest="STN"), offer(20, dest="CTA"),
    ], state, cfg)
    msgs = notify.build_messages(alerts, cfg, ["Wizz Air non funziona"])
    assert len(msgs) == 2
    abroad, italy = msgs
    assert "estero" in abroad and "CTA" not in abroad and "⚠️ Wizz Air" in abroad
    assert "Italia" in italy and "CTA" in italy and "BCN" not in italy
    assert abroad.index("BCN") < abroad.index("STN")            # ordinate per prezzo
    assert "Altre date:" in abroad and abroad.count("<b>BCN</b>") == 1 and "ven 20/11" in abroad
    assert "50 € in 2" in abroad and "🔥" in abroad and "👍" in abroad
    assert notify.build_messages([], cfg, []) == []


def test_message_shows_times(cfg):
    o = offer(30, out=date(2027, 1, 16), inn=date(2027, 1, 17))
    o.out_dep, o.out_arr = datetime(2027, 1, 16, 8, 30), datetime(2027, 1, 16, 10, 25)
    o.in_dep = datetime(2027, 1, 17, 19, 40)
    (msg,) = notify.build_messages(select_alerts([o], empty_state(), cfg), cfg, [])
    assert "sab 16/01 08:30→10:25" in msg and "dom 17/01 19:40" in msg and "33 h sul posto" in msg


def test_digest_includes_already_notified(cfg):
    state = empty_state()
    offers = [offer(25), offer(56, dest="TLS"), offer(20, dest="CTA")]
    select_alerts(offers, state, cfg)
    snapshot = json.dumps(state, sort_keys=True)
    assert select_alerts(offers, state, cfg) == []          # niente nuovi avvisi...
    msgs = notify.build_digest(offers, cfg)                 # ...ma il riepilogo le mostra
    assert len(msgs) == 2 and "TLS" in msgs[0] and "CTA" in msgs[1] and "CTA" not in msgs[0]
    assert "🆕" not in "".join(msgs)
    assert json.dumps(state, sort_keys=True) == snapshot


def test_digest_limits_and_empty(cfg):
    many = [offer(20 + i, dest=f"X{i:02d}") for i in range(15)]
    (msg,) = notify.build_digest(many, cfg)
    assert msg.count("Prenota") == 12 and "altre 3 destinazioni" in msg
    assert "Nessuna offerta" in notify.build_digest([], cfg)[0]


def test_country_from_sources(cfg):
    fares = ryanair.parse_fares(json.loads((FIX / "ryanair_sample.json").read_text()))
    assert [f["country"] for f in fares] == ["GB", "ES"]
    assert google_flights.destinations(cfg["sources"]["google_flights"]["destinations"])["NTE"] == ("Nantes", "FR")
    assert google_flights.destinations(["LGW"]) == {"LGW": ("LGW", "")}
    assert country_label("fr") == "🇫🇷 Francia" and country_label("ZZ") == "🇿🇿" and country_label("") == ""


def test_message_country_and_other_dates(cfg):
    weekends = [date(2027, 1, 8) + timedelta(weeks=i) for i in range(6)]
    offers = [offer(50 + i, dest="TLS", out=d, inn=d + timedelta(days=2)) for i, d in enumerate(weekends)]
    for o in offers:
        o.dest_city, o.country_code = "Tolosa", "FR"
    (msg,) = notify.build_digest(offers, cfg)
    assert "<b>Tolosa</b> 🇫🇷 Francia (Ryanair)" in msg
    assert msg.count("   • ") == 4                       # 4 altre date mostrate
    assert "…e altre 1 date: /voli Tolosa" in msg
    assert msg.count("Prenota") == 5


def test_latest_json_keeps_other_sources(tmp_path):
    path = tmp_path / "latest.json"
    old_google = offer(40, dest="LGW", out=date(2027, 1, 8), inn=date(2027, 1, 10))
    old_google.source = "google_flights"
    past = offer(30, dest="BCN", out=date(2026, 1, 1), inn=date(2026, 1, 3))
    past.source = "google_flights"
    storage.write_latest([old_google, past, offer(99)], {"ryanair", "google_flights"}, path=path)
    new = offer(25, dest="TLS", out=date(2027, 1, 22), inn=date(2027, 1, 24))
    new.country_code = "FR"
    storage.write_latest([new], {"ryanair"}, path=path, today=date(2026, 10, 25))
    data = json.loads(path.read_text())
    assert data["adults"] == 2
    assert [(r["source"], r["dest"]) for r in data["offers"]] == [("ryanair", "TLS"), ("google_flights", "LGW")]
    assert data["offers"][0]["country_name"] == "Francia" and data["offers"][0]["flag"] == "🇫🇷"


def test_prices_csv_migration(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text("checked_at,source\nold,row\n")
    storage.append_prices([offer(30)], path)
    assert (tmp_path / "prices_v1.csv").exists()
    assert path.read_text().splitlines()[0] == ",".join(storage.FIELDS)


def test_state_prunes_past(tmp_path):
    st = empty_state()
    st["offers"] = {"Ryanair|BCN|2026-01-01|2026-01-03": 20, "Ryanair|BCN|2027-01-01|2027-01-03": 20}
    path = tmp_path / "s.json"
    storage.save_state(st, path, today=date(2026, 10, 25))
    assert list(storage.load_state(path)["offers"]) == ["Ryanair|BCN|2027-01-01|2027-01-03"]


def test_main_isolates_failing_source(cfg, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(storage, "STATE", tmp_path / "a.json")
    monkeypatch.setattr(ryanair, "fetch", lambda c: [offer(25)])
    monkeypatch.setattr(wizzair, "fetch", lambda c: (_ for _ in ()).throw(RuntimeError("bloccato")))
    assert monitor.main(["--sources", "ryanair,wizzair", "--dry-run"]) == 0
    assert "BCN" in capsys.readouterr().out  # Ryanair notificata nonostante Wizz rotto


# --- Pacchetti volo + alloggio ---

def test_hotel_quality_filters(cfg):
    hotels = json.loads((FIX / "serpapi_hotels_sample.json").read_text())["properties"]
    best = hotel_src.pick_best(hotels, "hotel", "Tolosa", 2, cfg["hotels"])
    assert (best.name, best.stars, best.total_eur) == ("Hotel Ibis Styles", 3, 150)
    rentals = json.loads((FIX / "serpapi_rentals_sample.json").read_text())["properties"]
    apt = hotel_src.pick_best(rentals, "apartment", "Tolosa", 2, cfg["hotels"])
    assert (apt.name, apt.rating, apt.total_eur) == ("Capitole Loft", 4.8, 142)


class FakeResp:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def test_hotel_search_cache_and_budget(cfg, monkeypatch, tmp_path):
    calls = []
    data = json.loads((FIX / "serpapi_hotels_sample.json").read_text())
    monkeypatch.setattr(hotel_src.requests, "get", lambda url, params, timeout: calls.append(params) or FakeResp(data))
    state = empty_state()
    cache = tmp_path / "cache.json"
    s = hotel_src.HotelSearch(cfg, state, api_key="k", cache_path=cache, today=date(2026, 10, 26))
    d1, d2 = date(2027, 1, 23), date(2027, 1, 25)
    assert s.best("Tolosa", d1, d2, "hotel").name == "Hotel Ibis Styles"
    assert s.best("Tolosa", d1, d2, "hotel").name == "Hotel Ibis Styles"   # dalla cache
    assert len(calls) == 1 and calls[0]["hotel_class"] == "3,4,5" and calls[0]["adults"] == 2
    assert state["hotel_searches"] == {"2026-10": 1}
    s.save()
    s2 = hotel_src.HotelSearch(cfg, state, api_key="k", cache_path=cache, today=date(2026, 10, 27))
    s2.best("Tolosa", d1, d2, "hotel")
    assert len(calls) == 1                                                 # cache ancora valida
    state["hotel_searches"]["2026-10"] = cfg["hotels"]["monthly_budget"]
    with pytest.raises(hotel_src.BudgetExceeded):
        s2.best("Praga", d1, d2, "hotel")


def test_packages_build_and_message(cfg, monkeypatch, tmp_path):
    hotels = json.loads((FIX / "serpapi_hotels_sample.json").read_text())
    rentals = json.loads((FIX / "serpapi_rentals_sample.json").read_text())
    monkeypatch.setattr(hotel_src.requests, "get",
                        lambda url, params, timeout: FakeResp(rentals if params.get("vacation_rentals") else hotels))
    tls = offer(56.27, dest="TLS", out=date(2027, 1, 23), inn=date(2027, 1, 25))
    tls.dest_city, tls.country_code = "Tolosa", "FR"
    tls.out_dep, tls.out_arr, tls.in_dep = datetime(2027, 1, 23, 10), datetime(2027, 1, 23, 12, 5), datetime(2027, 1, 25, 20, 55)
    soon = offer(20, dest="BCN", out=date(2026, 10, 30), inn=date(2026, 11, 1))   # troppo vicino
    italy = offer(15, dest="CTA", out=date(2027, 1, 8), inn=date(2027, 1, 10))    # Italia: escluso
    state = empty_state()
    search = hotel_src.HotelSearch(cfg, state, api_key="k", cache_path=tmp_path / "c.json", today=date(2026, 10, 26))
    pkgs, notes = packages.build([soon, italy, tls], cfg, search, today=date(2026, 10, 26))
    assert [p.offer.dest for p in pkgs] == ["TLS"] and notes == []
    p = pkgs[0]
    assert p.stay.name == "Capitole Loft" and p.total(2) == pytest.approx(254.54)
    (msg,) = notify.build_packages(pkgs, cfg, notes)
    assert "<b>Tolosa</b> 🇫🇷 Francia · sab 23/01 → lun 25/01 (2 notti)" in msg
    assert "🏨 Hotel Ibis Styles ★★★ · 4,2/5 (800 recensioni) · <b>150 €</b>" in msg
    assert "🏠 Appartamento Capitole Loft · 4,8/5 (63 recensioni) · <b>142 €</b>" in msg
    assert "Totale da <b>255 €</b> in 2 (127 € a testa)" in msg


def test_packages_disabled_without_key(cfg, tmp_path):
    search = hotel_src.HotelSearch(cfg, empty_state(), api_key="", cache_path=tmp_path / "c.json")
    assert packages.build([offer(30, dest="TLS", out=date(2027, 1, 23), inn=date(2027, 1, 25))], cfg, search) == ([], [])
    assert notify.build_packages([], cfg, []) == []
