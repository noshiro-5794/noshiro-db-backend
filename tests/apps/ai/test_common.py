from decimal import Decimal

import pytest

from apps.ai.exceptions import InvalidAIProposal
from apps.ai.services.common import (
    ai_input_hash,
    optional_non_negative_decimal,
    optional_non_negative_int,
    validate_matching_output,
)


class TestValidateMatchingOutput:
    def test_valid_bind_decision(self) -> None:
        output = validate_matching_output(
            {"decision": "bind", "confidence": "0.95", "reason": "Match found."}
        )
        assert output["decision"] == "bind"
        assert output["confidence"] == "0.95"
        assert output["reason"] == "Match found."

    def test_valid_reject_decision(self) -> None:
        output = validate_matching_output(
            {"decision": "reject", "confidence": "0.8", "reason": "Different entities."}
        )
        assert output["decision"] == "reject"

    def test_valid_abstain_decision(self) -> None:
        output = validate_matching_output(
            {
                "decision": "abstain",
                "confidence": "0.5",
                "reason": "Not enough evidence.",
            }
        )
        assert output["decision"] == "abstain"

    def test_invalid_decision_raises(self) -> None:
        with pytest.raises(InvalidAIProposal, match="decision must be"):
            validate_matching_output(
                {"decision": "maybe", "confidence": "0.5", "reason": "test"}
            )

    def test_empty_reason_raises(self) -> None:
        with pytest.raises(InvalidAIProposal, match="reason must be"):
            validate_matching_output(
                {"decision": "bind", "confidence": "0.5", "reason": "  "}
            )

    def test_boolean_confidence_raises(self) -> None:
        with pytest.raises(InvalidAIProposal, match="confidence must be"):
            validate_matching_output(
                {"decision": "bind", "confidence": True, "reason": "test"}
            )

    def test_non_numeric_confidence_raises(self) -> None:
        with pytest.raises(InvalidAIProposal, match="confidence must be"):
            validate_matching_output(
                {"decision": "bind", "confidence": "high", "reason": "test"}
            )

    def test_negative_confidence_raises(self) -> None:
        with pytest.raises(InvalidAIProposal, match="confidence must be"):
            validate_matching_output(
                {"decision": "bind", "confidence": "-0.1", "reason": "test"}
            )

    def test_confidence_above_one_raises(self) -> None:
        with pytest.raises(InvalidAIProposal, match="confidence must be"):
            validate_matching_output(
                {"decision": "bind", "confidence": "1.5", "reason": "test"}
            )

    def test_reason_truncated_to_2000_chars(self) -> None:
        output = validate_matching_output(
            {"decision": "bind", "confidence": "0.5", "reason": "x" * 3000}
        )
        assert len(output["reason"]) == 2000


class TestOptionalNonNegativeInt:
    def test_none_returns_none(self) -> None:
        assert optional_non_negative_int(None) is None

    def test_boolean_returns_none(self) -> None:
        assert optional_non_negative_int(True) is None
        assert optional_non_negative_int(False) is None

    def test_valid_string_returns_int(self) -> None:
        assert optional_non_negative_int("5") == 5

    def test_negative_returns_none(self) -> None:
        assert optional_non_negative_int("-1") is None

    def test_invalid_string_returns_none(self) -> None:
        assert optional_non_negative_int("abc") is None


class TestOptionalNonNegativeDecimal:
    def test_none_returns_none(self) -> None:
        assert optional_non_negative_decimal(None) is None

    def test_boolean_returns_none(self) -> None:
        assert optional_non_negative_decimal(True) is None

    def test_valid_string_returns_decimal(self) -> None:
        result = optional_non_negative_decimal("0.001")
        assert result == Decimal("0.001")

    def test_negative_returns_none(self) -> None:
        assert optional_non_negative_decimal("-0.01") is None

    def test_invalid_string_returns_none(self) -> None:
        assert optional_non_negative_decimal("abc") is None


class TestAiInputHash:
    def test_produces_stable_hash(self) -> None:
        h1 = ai_input_hash({"a": 1, "b": 2})
        h2 = ai_input_hash({"b": 2, "a": 1})
        assert h1 == h2
        assert len(h1) == 64

    def test_different_payloads_produce_different_hashes(self) -> None:
        h1 = ai_input_hash({"a": 1})
        h2 = ai_input_hash({"a": 2})
        assert h1 != h2
