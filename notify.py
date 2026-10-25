"""Messaggi Telegram."""

from __future__ import annotations

import html
import os

import requests

from alerts import Alert
from dates import fmt_it

MAX_LEN = 3900  # limite Telegram 4096 caratteri


def _line(a: Alert, adults: int) -> str:
    o = a.offer
    tag = {"new": "🆕", "drop": f"🔻 -{a.drop:.0f} €", "record": "🏆 minimo storico"}[a.reason]
    if a.reason == "record" and a.drop:
        tag += f" (-{a.drop:.0f} €)"
    return (
        f"✈️ <b>{html.escape(o.origin)} → {html.escape(o.dest_city)}</b> ({html.escape(o.airline)})\n"
        f"   {fmt_it(o.out_date)} → {fmt_it(o.in_date)} · <b>{o.price_pp:.0f} €</b> a testa "
        f"({o.price_pp * adults:.0f} € in {adults}) · {tag} · "
        f'<a href="{html.escape(o.link)}">Prenota</a>'
    )


def build_messages(alerts: list[Alert], cfg: dict, warnings: list[str]) -> list[str]:
    super_t = cfg["thresholds"]["super"]
    adults = cfg["adults"]
    sections = [
        (f"🔥 <b>Super offerte (≤ {super_t} €)</b>", [a for a in alerts if a.offer.price_pp <= super_t]),
        (f"👍 <b>Buone offerte ({super_t}–{cfg['thresholds']['good']} €)</b>",
         [a for a in alerts if a.offer.price_pp > super_t]),
    ]
    lines: list[str] = []
    for title, items in sections:
        if items:
            lines += ["", title] + [_line(a, adults) for a in items]
    lines += ["", *[f"⚠️ {html.escape(w)}" for w in warnings]] if warnings else []
    if not lines:
        return []
    lines = [f"🛫 <b>Voli weekend da {cfg['origin']}</b>"] + lines

    messages, cur = [], ""
    for line in lines:
        if len(cur) + len(line) + 1 > MAX_LEN:
            messages.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        messages.append(cur)
    return messages


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
