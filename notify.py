"""Messaggi Telegram."""

from __future__ import annotations

import html
import os

import requests

from airports import is_domestic
from alerts import Alert
from dates import fmt_it

MAX_LEN = 3900  # limite Telegram 4096 caratteri


def _times(o) -> str:
    if not (o.out_dep and o.out_arr and o.in_dep):
        return f"{fmt_it(o.out_date)} → {fmt_it(o.in_date)}"
    return (
        f"{fmt_it(o.out_date)} {o.out_dep:%H:%M}→{o.out_arr:%H:%M} · "
        f"ritorno {fmt_it(o.in_date)} {o.in_dep:%H:%M} · {o.hours_at_dest:.0f} h sul posto"
    )


def _line(a: Alert, others: int, cfg: dict) -> str:
    o = a.offer
    adults = cfg["adults"]
    tag = {"new": "🆕", "drop": f"🔻 -{a.drop:.0f} €", "record": "🏆 minimo storico"}[a.reason]
    if a.reason == "record" and a.drop:
        tag += f" (-{a.drop:.0f} €)"
    tier = "🔥" if o.price_pp <= cfg["thresholds"]["super"] else "👍"
    more = f" · +{others} altre date" if others else ""
    return (
        f"{tier} <b>{html.escape(o.dest_city)}</b> ({html.escape(o.airline)})\n"
        f"   {_times(o)}\n"
        f"   <b>{o.price_pp:.0f} €</b> a testa ({o.price_pp * adults:.0f} € in {adults}) · {tag}{more} · "
        f'<a href="{html.escape(o.link)}">Prenota</a>'
    )


def _best_per_dest(alerts: list[Alert]) -> list[tuple[Alert, int]]:
    """Una riga per destinazione: l'offerta più economica + quante altre date."""
    groups: dict[str, list[Alert]] = {}
    for a in alerts:
        groups.setdefault(a.offer.dest, []).append(a)
    rows = [(min(g, key=lambda a: a.offer.price_pp), len(g) - 1) for g in groups.values()]
    return sorted(rows, key=lambda r: r[0].offer.price_pp)


def _split(lines: list[str]) -> list[str]:
    messages, cur = [], ""
    for line in lines:
        if len(cur) + len(line) + 1 > MAX_LEN:
            messages.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        messages.append(cur)
    return messages


def build_messages(alerts: list[Alert], cfg: dict, warnings: list[str]) -> list[str]:
    """Primo messaggio: estero (+ avvisi). Secondo messaggio: Italia."""
    abroad = [a for a in alerts if not is_domestic(a.offer.dest)]
    italy = [a for a in alerts if is_domestic(a.offer.dest)]
    out = []

    lines = [f"🌍 <b>Weekend all'estero da {cfg['origin']}</b>"] if abroad else []
    for a, others in _best_per_dest(abroad):
        lines += ["", _line(a, others, cfg)]
    if warnings:
        lines += [""] + [f"⚠️ {html.escape(w)}" for w in warnings]
    out += _split(lines)

    if italy:
        lines = [f"🇮🇹 <b>Weekend in Italia da {cfg['origin']}</b>"]
        for a, others in _best_per_dest(italy):
            lines += ["", _line(a, others, cfg)]
        out += _split(lines)
    return out


def send(messages: list[str]) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    for text in messages:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=30,
        )
        r.raise_for_status()
