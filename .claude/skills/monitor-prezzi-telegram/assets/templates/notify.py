"""Invio messaggi Telegram (HTML), spezzati sotto il limite di 4096 caratteri."""

from __future__ import annotations

import html
import os

import requests

MAX_LEN = 3900


def split(lines: list[str]) -> list[str]:
    messages, cur = [], ""
    for line in lines:
        if len(cur) + len(line) + 1 > MAX_LEN:
            messages.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        messages.append(cur)
    return messages


def line(item) -> str:
    # {{ADATTA}}: una riga per elemento, con link e contesto utile
    return f'• <b>{html.escape(item.name)}</b> · {item.price:.0f} € · <a href="{html.escape(item.link)}">Apri</a>'


def build_messages(items, title: str, warnings: list[str]) -> list[str]:
    if not items and not warnings:
        return []
    lines = [f"<b>{html.escape(title)}</b>", ""] + [line(i) for i in items]
    lines += [""] + [f"⚠️ {html.escape(w)}" for w in warnings] if warnings else []
    return split(lines)


def send(messages: list[str]) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    for text in messages:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=30,
        )
        r.raise_for_status()
