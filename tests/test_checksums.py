"""IBAN, BIC and RF checks against published reference values, not values copied from the code."""

import pytest

from sepapay.iban import bic_problem, iban_problem, normalize_iban
from sepapay.reference import normalize_reference, rf_problem


class TestIban:
    @pytest.mark.parametrize(
        "iban",
        [
            "GB82 WEST 1234 5698 7654 32",  # the ISO 13616 / ECBS worked example
            "DE89 3704 0044 0532 0130 00",  # the example in most German bank documentation
        ],
    )
    def test_accepts_published_examples(self, iban: str) -> None:
        assert iban_problem(normalize_iban(iban)) is None

    def test_catches_a_single_mistyped_digit(self) -> None:
        assert "check digits" in (iban_problem("DE89370400440532013001") or "")

    def test_catches_two_swapped_adjacent_digits(self) -> None:
        assert "check digits" in (iban_problem("DE89370400440532010300") or "")

    def test_rejects_the_wrong_length_for_the_country(self) -> None:
        assert iban_problem("DE8937040044053201300") == "DE IBANs are 22 characters, this one is 21"

    def test_rejects_a_country_outside_sepa(self) -> None:
        # A valid Brazilian IBAN checksum-wise is still not payable by SCT.
        assert iban_problem("BR1500000000000010932840814P2") == "BR is not a SEPA country"

    def test_rejects_something_that_is_not_an_iban(self) -> None:
        assert "not an IBAN" in (iban_problem("12345") or "")

    def test_normalizes_spaces_and_case(self) -> None:
        assert normalize_iban(" gb82 west 1234 5698 7654 32 ") == "GB82WEST12345698765432"


class TestBic:
    @pytest.mark.parametrize("bic", ["DEUTDEFF", "DEUTDEFF500", "COBADEFFXXX"])
    def test_accepts_8_and_11_character_bics(self, bic: str) -> None:
        assert bic_problem(bic) is None

    @pytest.mark.parametrize("bic", ["DEUTDEF", "DEUTDEFF50", "D3UTDEFF", "DEUT1EFF"])
    def test_rejects_malformed_bics(self, bic: str) -> None:
        assert bic_problem(bic) is not None


class TestCreditorReference:
    def test_accepts_the_iso_11649_example(self) -> None:
        assert rf_problem(normalize_reference("RF18 5390 0754 7034")) is None

    def test_catches_a_mistyped_reference(self) -> None:
        assert "check digits" in (rf_problem("RF18539007547035") or "")

    def test_rejects_a_reference_over_25_characters(self) -> None:
        assert rf_problem("RF18" + "1" * 22) is not None
