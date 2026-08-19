from django.db import transaction
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from apps.users.exceptions import UserNotFound
from apps.users.models import EmailVerification, User
from apps.users.services.auth.verification_service import VerificationService


class PasswordService:
    @classmethod
    @transaction.atomic
    def reset_password(cls, *, email: str, code: str, new_password: str) -> None:
        verification = VerificationService.verify_code(
            email=email, purpose=EmailVerification.Purpose.RESET_PASSWORD, code=code
        )
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise UserNotFound()
        user.set_password(new_password)
        user.save(update_fields=["password"])
        cls._revoke_refresh_tokens(user=user)
        VerificationService.mark_as_used(verification)

    @staticmethod
    def _revoke_refresh_tokens(*, user: User) -> None:
        outstanding = OutstandingToken.objects.filter(
            user=user,
            blacklistedtoken__isnull=True,
        )
        BlacklistedToken.objects.bulk_create(
            [BlacklistedToken(token=token) for token in outstanding],
            ignore_conflicts=True,
        )
