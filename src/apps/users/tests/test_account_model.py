from unittest.mock import Mock

import pytest

from apps.users.models import EmailVerification, User, UserManager


def test_create_user_uses_safe_privilege_defaults() -> None:
    manager = UserManager()
    user = Mock()
    manager.model = Mock(return_value=user)

    result = manager.create_user(
        email="person@EXAMPLE.COM",
        password="test-password",
    )

    assert result is user
    manager.model.assert_called_once_with(
        email="person@example.com",
        is_staff=False,
        is_superuser=False,
    )
    user.set_password.assert_called_once_with("test-password")
    user.save.assert_called_once_with(using=manager._db)


@pytest.mark.parametrize("field", ["is_staff", "is_superuser"])
def test_create_superuser_requires_privilege_flags(field: str) -> None:
    manager = UserManager()

    with pytest.raises(ValueError):
        manager.create_superuser(
            email="admin@example.com",
            password="test-password",
            **{field: False},
        )


def test_email_indexes_match_model_constraints_and_queries() -> None:
    user_email = User._meta.get_field("email")
    user_index_fields = [index.fields for index in User._meta.indexes]
    verification_index_fields = [
        index.fields for index in EmailVerification._meta.indexes
    ]

    assert user_email.unique is True
    assert ["email"] not in user_index_fields
    assert ["email", "purpose", "-created_at"] in verification_index_fields
