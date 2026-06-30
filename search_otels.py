"""
Tool: search_hotels

Searches mock hotel data for accommodation in Porto that meets criteria.

Safety: All arguments are validated before any data access.
"""

import json
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data" / "hotels.json"

VALID_STARS = {1, 2, 3, 4, 5}


def _validate_nights(nights) -> int:
    try:
        val = int(nights)
    except (TypeError, ValueError):
        raise ValueError(f"nights must be an integer, got {nights!r}")
    if val < 1 or val > 30:
        raise ValueError(f"nights must be between 1 and 30, got {val}")
    return val


def _validate_max_price_per_night(price) -> float | None:
    if price is None:
        return None
    try:
        val = float(price)
    except (TypeError, ValueError):
        raise ValueError(f"max_price_per_night must be a number, got {price!r}")
    if val <= 0:
        raise ValueError(f"max_price_per_night must be positive, got {val}")
    return val


def _validate_min_stars(stars) -> int | None:
    if stars is None:
        return None
    try:
        val = int(stars)
    except (TypeError, ValueError):
        raise ValueError(f"min_stars must be an integer, got {stars!r}")
    if val not in VALID_STARS:
        raise ValueError(f"min_stars must be one of {sorted(VALID_STARS)}, got {val}")
    return val


def search_hotels(
    nights: int,
    max_price_per_night: float | None = None,
    min_stars: int | None = None,
) -> dict:
    """
    Search for hotels in Porto.

    Parameters
    ----------
    nights              : number of nights to stay
    max_price_per_night : optional cap on nightly rate in EUR
    min_stars           : optional minimum star rating (1–5)

    Returns
    -------
    dict with keys:
        "ok"     : bool
        "hotels" : list[dict]  – each hotel has a computed "total_eur" field
        "error"  : str | None
    """
    # ── Input validation ─────────────────────────────────────────────────────
    try:
        nights = _validate_nights(nights)
        max_price_per_night = _validate_max_price_per_night(max_price_per_night)
        min_stars = _validate_min_stars(min_stars)
    except ValueError as exc:
        return {"ok": False, "hotels": [], "error": str(exc)}

    # ── Load data ────────────────────────────────────────────────────────────
    try:
        raw = json.loads(DATA_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "hotels": [], "error": f"data load error: {exc}"}

    # ── Filter & annotate ────────────────────────────────────────────────────
    results = []
    for h in raw.get("hotels", []):
        pn = h.get("price_per_night_eur", 0)
        if max_price_per_night is not None and pn > max_price_per_night:
            continue
        if min_stars is not None and h.get("stars", 0) < min_stars:
            continue
        enriched = dict(h)
        enriched["nights"] = nights
        enriched["total_eur"] = round(pn * nights, 2)
        results.append(enriched)

    results.sort(key=lambda h: h["price_per_night_eur"])
    return {"ok": True, "hotels": results, "error": None}
