"""Messaggi Telegram."""

from __future__ import annotations

import html
import os

import requests

from airports import country_label, is_domestic
from alerts import Alert
from dates import fmt_it
from models import Offer

MAX_LEN = 3900  # limite Telegram 4096 caratteri


def _times(o) -> str:
    if not (o.out_dep and o.out_arr and o.in_dep):
        return f"{fmt_it(o.out_date)} → {fmt_it(o.in_date)}"
    return (
        f"{fmt_it(o.out_date)} {o.out_dep:%H:%M}→{o.out_arr:%H:%M} · "
        f"ritorno {fmt_it(o.in_date)} {o.in_dep:%H:%M} · {o.hours_at_dest:.0f} h sul posto"
    )


def _short(o, cfg: dict, best: Offer) -> str:
    """Riga compatta per le altre date della stessa città."""
    if o.out_dep and o.out_arr and o.in_dep:
        when = f"{fmt_it(o.out_date)} {o.out_dep:%H:%M}→{o.out_arr:%H:%M} · {fmt_it(o.in_date)} {o.in_dep:%H:%M}"
    else:
        when = f"{fmt_it(o.out_date)} → {fmt_it(o.in_date)}"
    airline = f" ({html.escape(o.airline)})" if o.airline != best.airline else ""
    return f'   • {when} · <b>{o.price_pp:.0f} €</b>{airline} · <a href="{html.escape(o.link)}">Prenota</a>'


def _line(a: Alert, others: list[Alert], cfg: dict) -> str:
    o = a.offer
    adults = cfg["adults"]
    tag = {"new": "🆕", "drop": f"🔻 -{a.drop:.0f} €", "record": "🏆 minimo storico",
           "digest": ""}[a.reason]
    if a.reason == "record" and a.drop:
        tag += f" (-{a.drop:.0f} €)"
    tier = "🔥" if o.price_pp <= cfg["thresholds"]["super"] else "👍"
    country = country_label(o.country_code)
    lines = [
        f"{tier} <b>{html.escape(o.dest_city)}</b>{' ' + country if country else ''} ({html.escape(o.airline)})",
        f"   {_times(o)}",
        f"   <b>{o.price_pp:.0f} €</b> a testa ({o.price_pp * adults:.0f} € in {adults}) · "
        + (f"{tag} · " if tag else "")
        + f'<a href="{html.escape(o.link)}">Prenota</a>',
    ]
    limit = (cfg.get("digest") or {}).get("max_other_dates", 4)
    if others:
        lines.append("   Altre date:")
        lines += [_short(x.offer, cfg, o) for x in others[:limit]]
        if len(others) > limit:
            lines.append(f"   …e altre {len(others) - limit} date: /voli {html.escape(o.dest_city)}")
    return "\n".join(lines)


def _best_per_dest(alerts: list[Alert]) -> list[tuple[Alert, list[Alert]]]:
    """Una voce per destinazione: l'offerta più economica + le altre date, per prezzo."""
    groups: dict[str, list[Alert]] = {}
    for a in alerts:
        groups.setdefault(a.offer.dest, []).append(a)
    rows = []
    for g in groups.values():
        g.sort(key=lambda a: (a.offer.price_pp, a.offer.out_date))
        rows.append((g[0], g[1:]))
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


def build_digest(offers: list[Offer], cfg: dict) -> list[str]:
    """Riepilogo del mattino: le migliori offerte valide, anche se già notificate."""
    dcfg = cfg.get("digest") or {}
    items = [Alert(o, "digest") for o in offers]
    sections = [
        ("☀️ <b>Riepilogo del mattino: estero</b>",
         [a for a in items if not is_domestic(a.offer.dest)], dcfg.get("max_abroad", 12)),
        ("🇮🇹 <b>Riepilogo del mattino: Italia</b>",
         [a for a in items if is_domestic(a.offer.dest)], dcfg.get("max_italy", 6)),
    ]
    out = []
    for title, group, limit in sections:
        rows = _best_per_dest(group)
        if not rows:
            continue
        lines = [title]
        for a, others in rows[:limit]:
            lines += ["", _line(a, others, cfg)]
        if len(rows) > limit:
            lines += ["", f"…e altre {len(rows) - limit} destinazioni"]
        out += _split(lines)
    return out or [f"☀️ Nessuna offerta weekend sotto i {cfg['thresholds']['good']} € oggi."]


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
