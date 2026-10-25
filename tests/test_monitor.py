import json
from datetime import date
from pathlib import Path

import pytest

import fx
import monitor
import notify
import storage
from alerts import filter_offers, select_alerts
from dates import is_weekend_trip, upcoming_fri_sun, windows
from models import Offer
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


def test_ryanair_parse(cfg):
    offers = ryanair.parse(json.loads((FIX / "ryanair_sample.json").read_text()), cfg)
    assert len(offers) == 2  # la tariffa malformata viene ignorata
    bcn = offers[0]
    assert (bcn.dest, bcn.dest_city, bcn.price_pp) == ("BCN", "Barcellona", 29.99)
    assert bcn.out_date == date(2026, 11, 13) and bcn.in_date == date(2026, 11, 15)
    assert "adults=2" in bcn.link and "destinationIata=BCN" in bcn.link


def test_wizz_combine_converts_currency(cfg):
    tt = json.loads((FIX / "wizz_timetable_sample.json").read_text())
    offers = {(o.out_date, o.in_date): o.price_pp for o in wizzair.combine("BUD", "Budapest", tt, cfg)}
    # ven 13 + dom 15 (8000 HUF = 20 €), sab 14 + lun 16 (12000 HUF = 30 €), ...
    assert offers[(date(2026, 11, 13), date(2026, 11, 15))] == pytest.approx(39.99)
    assert offers[(date(2026, 11, 14), date(2026, 11, 16))] == pytest.approx(39.99)
    assert offers[(date(2026, 11, 14), date(2026, 11, 15))] == pytest.approx(29.99)
    # mercoledì 18 e voli soldOut esclusi
    assert all(d.weekday() in (4, 5) for d, _ in offers)


def test_wizz_destinations_and_version():
    route_map = {"cities": [
        {"iata": "NAP", "shortName": "Napoli", "connections": [{"iata": "BUD"}, {"iata": "TIA"}]},
        {"iata": "BUD", "shortName": "Budapest", "connections": []},
    ]}
    assert wizzair.destinations(route_map, "NAP") == {"BUD": "Budapest", "TIA": "TIA"}

    class Fake:
        def text(self, url):
            return "SSR https://be.wizzair.com/27.3.0 "

    assert wizzair.api_base(Fake()) == "https://be.wizzair.com/27.3.0"


def test_google_price_parse():
    assert google_flights.parse_price("€58") == 58
    assert google_flights.parse_price("$100") == pytest.approx(90)
    assert google_flights.parse_price("1,234 €") == 1234
    assert google_flights.parse_price("") is None


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


def test_message_sections(cfg):
    state = empty_state()
    alerts = select_alerts([offer(25), offer(55, dest="STN")], state, cfg)
    msgs = notify.build_messages(alerts, cfg, ["Wizz Air non funziona"])
    text = "".join(msgs)
    assert text.index("Super offerte") < text.index("25 €") < text.index("Buone offerte") < text.index("55 €")
    assert "50 € in 2" in text and "⚠️ Wizz Air" in text
    assert notify.build_messages([], cfg, []) == []


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
