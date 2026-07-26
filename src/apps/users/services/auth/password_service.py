from django.db import transaction

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
        VerificationService.mark_as_used(verification)
