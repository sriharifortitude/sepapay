"""The calendar, the character set, and amounts."""

import datetime as dt
from decimal import Decimal

import pytest

from sepapay.money import AmountError, format_amount, parse_amount
from sepapay.target2 import closed_because, easter_sunday, next_business_day
from sepapay.text import TextError, identifier, to_sepa


class TestTarget2:
    @pytest.mark.parametrize(
        ("year", "easter"),
        [(2000, dt.date(2000, 4, 23)), (2024, dt.date(2024, 3, 31)), (2025, dt.date(2025, 4, 20)),
         (2026, dt.date(2026, 4, 5)), (2027, dt.date(2027, 3, 28)), (2038, dt.date(2038, 4, 25))],
    )  # fmt: skip
    def test_easter_matches_the_published_dates(self, year: int, easter: dt.date) -> None:
        assert easter_sunday(year) == easter

    def test_good_friday_and_easter_monday_are_closed(self) -> None:
        assert closed_because(dt.date(2026, 4, 3)) == "Good Friday"
        assert closed_because(dt.date(2026, 4, 6)) == "Easter Monday"

    def test_fixed_holidays_and_weekends_are_closed(self) -> None:
        assert closed_because(dt.date(2026, 5, 1)) == "Labour Day"
        assert closed_because(dt.date(2025, 12, 26)) == "26 December"  # a Friday
        assert closed_because(dt.date(2026, 10, 3)) == "Saturday"

    def test_national_holidays_do_not_close_target2(self) -> None:
        # German Unity Day 2025 is a Friday: German banks' branches close, TARGET2 doesn't.
        assert closed_because(dt.date(2025, 10, 3)) is None

    def test_next_business_day_skips_christmas_and_the_weekend(self) -> None:
        # 2026: Fri 25 (Christmas), Sat 26, Sun 27 -> Mon 28
        assert next_business_day(dt.date(2026, 12, 25)) == dt.date(2026, 12, 28)


class TestText:
    def test_strips_accents_and_expands_letters_that_do_not_decompose(self) -> None:
        assert to_sepa("Müller & Söhne Straße", "name", 70) == "Muller + Sohne Strasse"
        assert to_sepa("Łódź Øresund Œuvre", "name", 70) == "Lodz Oresund OEuvre"

    def test_collapses_whitespace(self) -> None:
        assert to_sepa("  Acme \t Ltd  ", "name", 70) == "Acme Ltd"

    def test_refuses_what_it_cannot_convert_and_names_it(self) -> None:
        with pytest.raises(TextError, match="'株'"):
            to_sepa("株式会社", "name", 70)

    def test_refuses_a_value_too_long_after_conversion(self) -> None:
        # "ß" becomes two characters, so 70 of them is 140 after conversion.
        with pytest.raises(TextError, match="140 characters"):
            to_sepa("ß" * 70, "name", 70)

    @pytest.mark.parametrize("value", ["/INV-1", "INV-1/", "INV//1"])
    def test_identifier_slash_rules(self, value: str) -> None:
        with pytest.raises(TextError, match="'/'"):
            identifier(value, "end_to_end_id")

    def test_identifier_max_35(self) -> None:
        with pytest.raises(TextError, match="maximum is 35"):
            identifier("X" * 36, "end_to_end_id")


class TestMoney:
    @pytest.mark.parametrize(("raw", "expected"), [("10", "10.00"), ("10.5", "10.50"), ("0.01", "0.01")])
    def test_parses_plain_decimals(self, raw: str, expected: str) -> None:
        assert format_amount(parse_amount(raw)) == expected

    @pytest.mark.parametrize("raw", ["1,000.00", "1.000,00", "10.001", "-5.00", "1e3", "", "abc"])
    def test_refuses_ambiguous_or_invalid_amounts(self, raw: str) -> None:
        with pytest.raises(AmountError):
            parse_amount(raw)

    def test_refuses_zero_and_the_scheme_maximum_plus_a_cent(self) -> None:
        with pytest.raises(AmountError, match="smallest"):
            parse_amount("0.00")
        with pytest.raises(AmountError, match="maximum"):
            parse_amount("1000000000.00")
        assert parse_amount("999999999.99") == Decimal("999999999.99")
