"""Aeroporti italiani, per separare le offerte nazionali da quelle estere."""

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
