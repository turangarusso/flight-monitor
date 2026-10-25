import json
from datetime import date, datetime
from pathlib import Path

import pytest

import fx
import monitor
import notify
import storage
from alerts import filter_offers, select_alerts
from dates import is_weekend_trip, upcoming_fri_sun, windows
from combos import best_combos, valid_trip
from models import Leg, Offer
from sources import google_flights, ryanair, wizzair

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
        {"iata": "BUD", "shortName": "Budapest", "connections": []},
        {"iata": "VCE", "shortName": "Venezia", "connections": []},
        {"iata": "VCX", "shortName": "Venezia (tutti gli aeroporti)", "connections": []},
    ]}
    assert wizzair.destinations(route_map, "NAP") == {"BUD": "Budapest", "TIA": "TIA"}

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
    assert "+1 altre date" in abroad and abroad.count("BCN") == 1
    assert "50 € in 2" in abroad and "🔥" in abroad and "👍" in abroad
    assert notify.build_messages([], cfg, []) == []


def test_message_shows_times(cfg):
    o = offer(30, out=date(2027, 1, 16), inn=date(2027, 1, 17))
    o.out_dep, o.out_arr = datetime(2027, 1, 16, 8, 30), datetime(2027, 1, 16, 10, 25)
    o.in_dep = datetime(2027, 1, 17, 19, 40)
    (msg,) = notify.build_messages(select_alerts([o], empty_state(), cfg), cfg, [])
    assert "sab 16/01 08:30→10:25" in msg and "dom 17/01 19:40" in msg and "33 h sul posto" in msg


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
