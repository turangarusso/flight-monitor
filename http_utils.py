"""Sessione HTTP condivisa con header da browser e retry."""

from __future__ import annotations

import time

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)


class HttpError(Exception):
    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status} su {url}")
        self.status = status


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
        }
    )
    return s


def request_json(s: requests.Session, method: str, url: str, retries: int = 3, **kwargs):
    """Richiesta con backoff esponenziale su errori di rete e 429/5xx."""
    kwargs.setdefault("timeout", 30)
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = s.request(method, url, **kwargs)
            if r.status_code == 429 or r.status_code >= 500:
                last = HttpError(r.status_code, url)
            elif r.status_code >= 400:
                raise HttpError(r.status_code, url)
            else:
                return r.json()
        except requests.RequestException as e:
            last = e
        time.sleep(2 ** (attempt + 1))
    assert last is not None
    raise last
