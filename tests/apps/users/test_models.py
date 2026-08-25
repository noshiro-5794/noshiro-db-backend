import pytest

from apps.users.models import User


class TestUserStr:
    @pytest.mark.django_db
    def test_str_returns_email(self) -> None:
        user = User.objects.create_user(email="test@example.com")
        assert str(user) == "test@example.com"
