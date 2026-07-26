from unittest.mock import Mock, patch

from django.test import override_settings

from apps.sync.providers.ai import AIClient
from apps.sync.providers.bangumi import BangumiClient


@override_settings(AI_AGENT_API_KEY=None, AI_AGENT_TIMEOUT=15)
def test_ai_http_client_is_created_lazily() -> None:
    with patch("apps.sync.providers.ai.httpx.Client") as client_factory:
        client = AIClient()

        client_factory.assert_not_called()

        assert client.client is client_factory.return_value
        assert client.client is client_factory.return_value
        client_factory.assert_called_once_with(
            headers={"Content-Type": "application/json"},
            timeout=15,
        )


@override_settings(
    BANGUMI_API_BASE_URL="https://api.bgm.tv",
    BANGUMI_API_KEY=None,
    BANGUMI_TIMEOUT=30,
    BANGUMI_USER_AGENT=("Noshiro_5794/noshiro_db (https://github.com/noshiro-5794)"),
)
def test_bangumi_http_client_is_created_lazily() -> None:
    with patch("apps.sync.providers.bangumi.httpx.Client") as client_factory:
        client = BangumiClient()

        client_factory.assert_not_called()

        assert client.client is client_factory.return_value
        assert client.client is client_factory.return_value
        client_factory.assert_called_once_with(
            base_url="https://api.bgm.tv",
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "Noshiro_5794/noshiro_db (https://github.com/noshiro-5794)"
                ),
            },
            timeout=30,
            follow_redirects=True,
        )


@override_settings(
    BANGUMI_API_BASE_URL="https://api.bgm.tv",
    BANGUMI_API_KEY=None,
    BANGUMI_TIMEOUT=30,
    BANGUMI_USER_AGENT=("Noshiro_5794/noshiro_db (https://github.com/noshiro-5794)"),
)
def test_http_client_can_be_recreated_after_close() -> None:
    initial_client = Mock()
    client = BangumiClient(initial_client)

    client.close()
    initial_client.close.assert_called_once_with()

    with patch("apps.sync.providers.bangumi.httpx.Client") as client_factory:
        assert client.client is client_factory.return_value
        client_factory.assert_called_once_with(
            base_url="https://api.bgm.tv",
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "Noshiro_5794/noshiro_db (https://github.com/noshiro-5794)"
                ),
            },
            timeout=30,
            follow_redirects=True,
        )
