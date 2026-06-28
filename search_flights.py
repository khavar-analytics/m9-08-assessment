"""
Tool: search_flights

Searches mock flight data for routes matching the given criteria.
Returns a list of available flights sorted by price ascending.

Safety: All inputs are validated before the data file is touched.
"""

import json
import re
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data" / "flights.json"

# Whitelist of valid IATA airport codes present in our dataset
VALID_AIRPORTS = {"LHR", "STN", "LGW", "OPO"}
IATA_PATTERN = re.compile(r"^[A-Z]{3}$")


def _validate_airport(code: str, field: str) -> str:
    """
    Validate that `code` is a well-formed IATA code and is one we know about.
    Raises ValueError on bad input — callers must not bypass this.
    """
    if not isinstance(code, str):
        raise ValueError(f"{field} must be a string, got {type(code).__name__}")
    code = code.strip().upper()
    if not IATA_PATTERN.match(code):
        raise ValueError(
            f"{field} '{code}' is not a valid IATA airport code (expected 3 uppercase letters)"
        )
    if code not in VALID_AIRPORTS:
        raise ValueError(
            f"{field} '{code}' is not in the list of supported airports: {sorted(VALID_AIRPORTS)}"
        )
    return code


def _validate_max_price(max_price) -> float | None:
    """Allow None (no price cap) or a positive number."""
    if max_price is None:
        return None
    try:
        val = float(max_price)
    except (TypeError, ValueError):
        raise ValueError(f"max_price must be a number, got {max_price!r}")
    if val <= 0:
        raise ValueError(f"max_price must be positive, got {val}")
    return val


def search_flights(origin: str, destination: str, max_price: float | None = None) -> dict:
    """
    Search for one-way flights from *origin* to *destination*.

    Parameters
    ----------
    origin      : IATA code of the departure airport (e.g. "LHR")
    destination : IATA code of the arrival airport   (e.g. "OPO")
    max_price   : optional upper bound on price in EUR

    Returns
    -------
    dict with keys:
        "ok"      : bool
        "flights" : list[dict]  – sorted by price ascending (empty on no match)
        "error"   : str | None
    """
    # ── Input validation (safety mitigation) ────────────────────────────────
    try:
        origin = _validate_airport(origin, "origin")
        destination = _validate_airport(destination, "destination")
        max_price = _validate_max_price(max_price)
    except ValueError as exc:
        return {"ok": False, "flights": [], "error": str(exc)}

    if origin == destination:
        return {"ok": False, "flights": [], "error": "origin and destination must differ"}

    # ── Load data ────────────────────────────────────────────────────────────
    try:
        raw = json.loads(DATA_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "flights": [], "error": f"data load error: {exc}"}

    # ── Filter ───────────────────────────────────────────────────────────────
    results = [
        f for f in raw.get("routes", [])
        if f.get("origin") == origin
        and f.get("destination") == destination
        and (max_price is None or f.get("price_eur", 0) <= max_price)
    ]

    results.sort(key=lambda f: f.get("price_eur", 0))
    return {"ok": True, "flights": results, "error": None}