"""
tests/test_tools.py
===================
Unit tests for all three tools.  Run with:  python -m pytest tests/ -v
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import calculate, search_flights, search_hotels


# ═══════════════════════════════════════════════════════════════════
# calculate
# ═══════════════════════════════════════════════════════════════════

class TestCalculate:
    def test_simple_addition(self):
        r = calculate("1 + 1")
        assert r["ok"] is True
        assert r["result"] == 2.0

    def test_mixed_operators(self):
        r = calculate("89 + 68 * 2")
        assert r["ok"] is True
        assert r["result"] == pytest.approx(89 + 68 * 2)

    def test_parentheses(self):
        r = calculate("(89 + 68) * 2")
        assert r["ok"] is True
        assert r["result"] == pytest.approx((89 + 68) * 2)

    def test_floating_point(self):
        r = calculate("1.5 * 4")
        assert r["ok"] is True
        assert r["result"] == pytest.approx(6.0)

    def test_division(self):
        r = calculate("100 / 4")
        assert r["ok"] is True
        assert r["result"] == 25.0

    def test_division_by_zero(self):
        r = calculate("10 / 0")
        assert r["ok"] is False
        assert "zero" in r["error"].lower()

    def test_empty_expression(self):
        r = calculate("")
        assert r["ok"] is False

    def test_injection_attempt_semicolon(self):
        r = calculate("1 + 1; import os; os.system('rm -rf /')")
        assert r["ok"] is False
        assert "disallowed" in r["error"].lower()

    def test_injection_attempt_letters(self):
        r = calculate("__import__('os').system('ls')")
        assert r["ok"] is False

    def test_non_string_input(self):
        r = calculate(42)
        assert r["ok"] is False

    def test_too_long_expression(self):
        r = calculate("1 + " * 60 + "1")
        assert r["ok"] is False
        assert "long" in r["error"].lower()

    def test_negative_unary(self):
        r = calculate("-5 + 10")
        assert r["ok"] is True
        assert r["result"] == 5.0


# ═══════════════════════════════════════════════════════════════════
# search_flights
# ═══════════════════════════════════════════════════════════════════

class TestSearchFlights:
    def test_basic_search_lhr_to_opo(self):
        r = search_flights("LHR", "OPO")
        assert r["ok"] is True
        assert len(r["flights"]) > 0
        # sorted ascending by price
        prices = [f["price_eur"] for f in r["flights"]]
        assert prices == sorted(prices)

    def test_price_cap_filters(self):
        r = search_flights("LHR", "OPO", max_price=100)
        assert r["ok"] is True
        for f in r["flights"]:
            assert f["price_eur"] <= 100

    def test_price_cap_too_low(self):
        r = search_flights("LHR", "OPO", max_price=1)
        assert r["ok"] is True
        assert r["flights"] == []

    def test_invalid_origin_format(self):
        r = search_flights("LHRX", "OPO")
        assert r["ok"] is False
        assert "origin" in r["error"].lower()

    def test_invalid_origin_unknown(self):
        r = search_flights("JFK", "OPO")
        assert r["ok"] is False

    def test_same_origin_destination(self):
        r = search_flights("OPO", "OPO")
        assert r["ok"] is False

    def test_non_string_origin(self):
        r = search_flights(123, "OPO")
        assert r["ok"] is False

    def test_negative_max_price(self):
        r = search_flights("LHR", "OPO", max_price=-50)
        assert r["ok"] is False

    def test_stn_to_opo(self):
        r = search_flights("STN", "OPO")
        assert r["ok"] is True
        assert len(r["flights"]) >= 1


# ═══════════════════════════════════════════════════════════════════
# search_hotels
# ═══════════════════════════════════════════════════════════════════

class TestSearchHotels:
    def test_basic_search(self):
        r = search_hotels(nights=2)
        assert r["ok"] is True
        assert len(r["hotels"]) > 0

    def test_total_eur_computed_correctly(self):
        r = search_hotels(nights=2)
        for h in r["hotels"]:
            assert h["total_eur"] == pytest.approx(h["price_per_night_eur"] * 2)

    def test_price_cap(self):
        r = search_hotels(nights=2, max_price_per_night=100)
        assert r["ok"] is True
        for h in r["hotels"]:
            assert h["price_per_night_eur"] <= 100

    def test_min_stars_filter(self):
        r = search_hotels(nights=2, min_stars=4)
        assert r["ok"] is True
        for h in r["hotels"]:
            assert h["stars"] >= 4

    def test_combined_filters(self):
        r = search_hotels(nights=2, max_price_per_night=120, min_stars=3)
        assert r["ok"] is True
        for h in r["hotels"]:
            assert h["price_per_night_eur"] <= 120
            assert h["stars"] >= 3

    def test_invalid_nights_zero(self):
        r = search_hotels(nights=0)
        assert r["ok"] is False

    def test_invalid_nights_too_many(self):
        r = search_hotels(nights=31)
        assert r["ok"] is False

    def test_invalid_min_stars(self):
        r = search_hotels(nights=2, min_stars=6)
        assert r["ok"] is False

    def test_non_integer_nights(self):
        r = search_hotels(nights="two")
        assert r["ok"] is False

    def test_sorted_by_price(self):
        r = search_hotels(nights=2)
        prices = [h["price_per_night_eur"] for h in r["hotels"]]
        assert prices == sorted(prices)
