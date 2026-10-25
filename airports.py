"""Aeroporti italiani (offerte nazionali vs estere) e nomi dei paesi."""

from __future__ import annotations


ITALIAN_AIRPORTS = {
    # Nord
    "TRN", "CUF", "MXP", "LIN", "BGY", "VBS", "VRN", "VCE", "TSF", "TRS", "BZO", "GOA", "BLQ", "PMF", "RMI", "FRL",
    # Centro
    "PSA", "FLR", "SAY", "PEG", "AOI", "FCO", "CIA", "PSR",
    # Sud
    "NAP", "QSR", "BRI", "BDS", "FOG", "TAR", "SUF", "CRV", "REG",
    # Isole
    "CTA", "CIY", "PMO", "TPS", "LMP", "PNL", "CAG", "OLB", "AHO", "TTB",
}


def is_domestic(iata: str) -> bool:
    return iata.upper() in ITALIAN_AIRPORTS


# Nomi italiani dei paesi (ISO 3166-1 alpha-2)
COUNTRY_IT = {
    "IT": "Italia", "FR": "Francia", "ES": "Spagna", "PT": "Portogallo", "GB": "Regno Unito",
    "IE": "Irlanda", "DE": "Germania", "AT": "Austria", "CH": "Svizzera", "BE": "Belgio",
    "NL": "Paesi Bassi", "LU": "Lussemburgo", "DK": "Danimarca", "SE": "Svezia", "NO": "Norvegia",
    "FI": "Finlandia", "IS": "Islanda", "PL": "Polonia", "CZ": "Repubblica Ceca", "SK": "Slovacchia",
    "HU": "Ungheria", "SI": "Slovenia", "HR": "Croazia", "BA": "Bosnia ed Erzegovina",
    "RS": "Serbia", "ME": "Montenegro", "AL": "Albania", "MK": "Macedonia del Nord",
    "XK": "Kosovo", "GR": "Grecia", "CY": "Cipro", "MT": "Malta", "BG": "Bulgaria",
    "RO": "Romania", "MD": "Moldavia", "UA": "Ucraina", "LT": "Lituania", "LV": "Lettonia",
    "EE": "Estonia", "TR": "Turchia", "GE": "Georgia", "AM": "Armenia", "AZ": "Azerbaigian",
    "IL": "Israele", "JO": "Giordania", "EG": "Egitto", "MA": "Marocco", "TN": "Tunisia",
    "DZ": "Algeria", "AE": "Emirati Arabi Uniti", "SA": "Arabia Saudita", "KZ": "Kazakistan",
    "UZ": "Uzbekistan", "MV": "Maldive",
}


def flag(code: str | None) -> str:
    """'FR' -> 🇫🇷"""
    if not code or len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code.upper())


def country_label(code: str | None) -> str:
    """'FR' -> '🇫🇷 Francia' (solo bandiera se il nome non è noto)."""
    if not code:
        return ""
    name = COUNTRY_IT.get(code.upper())
    return f"{flag(code)} {name}" if name else flag(code)
