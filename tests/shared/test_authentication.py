from unittest.mock import MagicMock, patch

from shared.api.authentication import ContextJWTAuthentication


class TestContextJWTAuthentication:
    def test_authenticate_calls_set_user_id_when_user_exists(self) -> None:
        auth = ContextJWTAuthentication()
        mock_user = MagicMock()
        mock_user.pk = 42
        mock_request = MagicMock()

        with (
            patch(
                "shared.api.authentication.JWTAuthentication.authenticate",
                return_value=(mock_user, "token"),
            ),
            patch("shared.api.authentication.set_user_id") as mock_set,
        ):
            result = auth.authenticate(mock_request)
            mock_set.assert_called_once_with(42)
            assert result == (mock_user, "token")

    def test_authenticate_skips_when_result_is_none(self) -> None:
        auth = ContextJWTAuthentication()
        mock_request = MagicMock()

        with (
            patch(
                "shared.api.authentication.JWTAuthentication.authenticate",
                return_value=None,
            ),
            patch("shared.api.authentication.set_user_id") as mock_set,
        ):
            result = auth.authenticate(mock_request)
            mock_set.assert_not_called()
            assert result is None
