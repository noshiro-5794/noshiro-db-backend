from decimal import Decimal
from unittest.mock import Mock

import pytest
from django.conf import settings
from django.test import override_settings

from integrations.ai import AIProviderError, ai_gateway
from integrations.ai.gateway import (
    _MODEL_ROUTING,
    OpenAICompatibleGateway,
)


class TestResolveModel:
    def test_known_use_case_returns_correct_setting(self) -> None:
        for use_case, setting_key in _MODEL_ROUTING.items():
            model = ai_gateway.resolve_model(use_case)
            assert model == getattr(settings, setting_key)

    def test_unknown_use_case_falls_back_to_primary(self) -> None:
        model = ai_gateway.resolve_model("nonexistent")
        assert model == settings.AI_PRIMARY_MODEL

    @override_settings(AI_REASONING_MODEL="custom-reasoning")
    def test_matching_use_case_uses_reasoning_tier(self) -> None:
        assert ai_gateway.resolve_model("entity_matching") == "custom-reasoning"

    @override_settings(AI_FAST_MODEL="custom-fast")
    def test_completion_use_case_uses_fast_tier(self) -> None:
        assert ai_gateway.resolve_model("info_completion") == "custom-fast"


class TestConfidence:
    def test_high_confidence(self) -> None:
        c = OpenAICompatibleGateway._confidence({"confidence": "0.99"})
        assert c == Decimal("0.99")

    def test_low_confidence(self) -> None:
        c = OpenAICompatibleGateway._confidence({"confidence": "0.5"})
        assert c == Decimal("0.5")

    def test_missing_confidence_defaults_to_zero(self) -> None:
        c = OpenAICompatibleGateway._confidence({})
        assert c == Decimal("0")

    def test_non_numeric_confidence_defaults_to_zero(self) -> None:
        c = OpenAICompatibleGateway._confidence({"confidence": "high"})
        assert c == Decimal("0")

    def test_boolean_confidence_defaults_to_zero(self) -> None:
        c = OpenAICompatibleGateway._confidence({"confidence": True})
        assert c == Decimal("0")

    def test_none_confidence_defaults_to_zero(self) -> None:
        c = OpenAICompatibleGateway._confidence({"confidence": None})
        assert c == Decimal("0")


class TestCompleteJson:
    def test_raises_without_api_key(self) -> None:
        with (
            override_settings(AI_AGENT_API_KEY=None),
            pytest.raises(AIProviderError, match="not configured"),
        ):
            ai_gateway.complete_json(
                system_prompt="test",
                payload={"key": "value"},
            )

    def test_uses_model_from_use_case(self) -> None:
        fake_response = Mock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.return_value = {
            "choices": [{"message": {"content": '{"result": "ok"}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        fake_client = Mock()
        fake_client.post.return_value = fake_response

        gw = OpenAICompatibleGateway(client=fake_client)
        with override_settings(AI_AGENT_API_KEY="sk-test"):
            result, usage = gw.complete_json(
                system_prompt="test",
                payload={"key": "value"},
                use_case="field_normalization",
            )

        assert result == {"result": "ok"}
        assert usage["model"] == settings.AI_FAST_MODEL
        assert usage["input_tokens"] == 10
        assert usage["output_tokens"] == 5

    def test_classification_fallback_when_confidence_low(self) -> None:
        fake_response_low = Mock()
        fake_response_low.raise_for_status.return_value = None
        fake_response_low.json.return_value = {
            "choices": [{"message": {"content": '{"confidence": "0.5"}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        fake_response_high = Mock()
        fake_response_high.raise_for_status.return_value = None
        fake_response_high.json.return_value = {
            "choices": [{"message": {"content": '{"confidence": "0.95"}'}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
        }
        fake_client = Mock()
        fake_client.post.side_effect = [fake_response_low, fake_response_high]

        gw = OpenAICompatibleGateway(client=fake_client)
        with override_settings(AI_AGENT_API_KEY="sk-test"):
            result, usage = gw.complete_json(
                system_prompt="test",
                payload={"key": "value"},
                use_case="entity_classification",
            )

        assert result == {"confidence": "0.95"}
        assert usage["model"] == settings.AI_PRIMARY_MODEL
        assert fake_client.post.call_count == 2

    def test_no_fallback_when_confidence_high(self) -> None:
        fake_response = Mock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.return_value = {
            "choices": [{"message": {"content": '{"confidence": "0.95"}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        fake_client = Mock()
        fake_client.post.return_value = fake_response

        gw = OpenAICompatibleGateway(client=fake_client)
        with override_settings(AI_AGENT_API_KEY="sk-test"):
            result, usage = gw.complete_json(
                system_prompt="test",
                payload={"key": "value"},
                use_case="entity_classification",
            )

        assert result == {"confidence": "0.95"}
        assert usage["model"] == settings.AI_FAST_MODEL
        assert fake_client.post.call_count == 1

    def test_http_error_wraps_as_ai_provider_error(self) -> None:
        import httpx

        fake_client = Mock()
        fake_client.post.side_effect = httpx.HTTPError("connection refused")

        gw = OpenAICompatibleGateway(client=fake_client)
        with (
            override_settings(AI_AGENT_API_KEY="sk-test"),
            pytest.raises(AIProviderError, match="connection refused"),
        ):
            gw.complete_json(
                system_prompt="test",
                payload={"key": "value"},
            )

    def test_invalid_json_response_wraps_as_ai_provider_error(self) -> None:
        fake_response = Mock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.return_value = {
            "choices": [{"message": {"content": "not json"}}],
        }
        fake_client = Mock()
        fake_client.post.return_value = fake_response

        gw = OpenAICompatibleGateway(client=fake_client)
        with (
            override_settings(AI_AGENT_API_KEY="sk-test"),
            pytest.raises(AIProviderError),
        ):
            gw.complete_json(
                system_prompt="test",
                payload={"key": "value"},
            )

    def test_non_dict_json_output_wraps_as_ai_provider_error(self) -> None:
        fake_response = Mock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.return_value = {
            "choices": [{"message": {"content": "[1, 2, 3]"}}],
        }
        fake_client = Mock()
        fake_client.post.return_value = fake_response

        gw = OpenAICompatibleGateway(client=fake_client)
        with (
            override_settings(AI_AGENT_API_KEY="sk-test"),
            pytest.raises(AIProviderError, match="JSON output must be an object"),
        ):
            gw.complete_json(
                system_prompt="test",
                payload={"key": "value"},
            )


class TestGatewayProviderName:
    def test_provider_name_is_openai_compatible(self) -> None:
        assert ai_gateway.provider_name == "openai_compatible"


class TestGatewayClientProperty:
    def test_client_property_lazy_init(self) -> None:
        from unittest.mock import patch

        with patch("integrations.ai.gateway.httpx") as mock_httpx:
            mock_client = Mock()
            mock_httpx.Client.return_value = mock_client
            mock_httpx_client_kwargs = Mock(return_value={})

            with patch(
                "integrations.ai.gateway.httpx_client_kwargs",
                mock_httpx_client_kwargs,
            ):
                gw = OpenAICompatibleGateway()
                with override_settings(AI_AGENT_API_KEY="sk-test"):
                    _ = gw.client
                    mock_httpx.Client.assert_called_once()

    def test_client_property_returns_cached(self) -> None:
        fake_client = Mock()
        gw = OpenAICompatibleGateway(client=fake_client)
        assert gw.client is fake_client


class TestGatewayClientWithoutApiKey:
    def test_client_created_without_auth_header(self) -> None:
        from unittest.mock import patch

        with patch("integrations.ai.gateway.httpx") as mock_httpx:
            mock_client = Mock()
            mock_httpx.Client.return_value = mock_client

            with patch(
                "integrations.ai.gateway.httpx_client_kwargs",
                return_value={},
            ):
                gw = OpenAICompatibleGateway()
                with override_settings(AI_AGENT_API_KEY=None):
                    _ = gw.client
                    call_kwargs = mock_httpx.Client.call_args[1]
                    assert "Authorization" not in call_kwargs.get("headers", {})
