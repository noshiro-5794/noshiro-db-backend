from django.db import IntegrityError, transaction

from apps.users.exceptions import EmailAlreadyExists, NicknameAlreadyExists
from apps.users.models import EmailVerification, User, UserProfile
from apps.users.services.auth.verification_service import VerificationService


class RegisterService:
    @staticmethod
    def _check_email_exists(email: str) -> None:
        exists = User.objects.filter(email__iexact=email).exists()
        if exists:
            raise EmailAlreadyExists()

    @classmethod
    @transaction.atomic
    def register(cls, *, email: str, password: str, nickname: str, code: str) -> User:
        email = User.objects.normalize_email(email)
        cls._check_email_exists(email)
        verification = VerificationService.verify_code(
            email=email, purpose=EmailVerification.Purpose.REGISTER, code=code
        )
        try:
            with transaction.atomic():
                user = User.objects.create_user(email=email, password=password)
                UserProfile.objects.create(user=user, nickname=nickname)
        except IntegrityError as exc:
            if User.objects.filter(email__iexact=email).exists():
                raise EmailAlreadyExists() from exc
            if UserProfile.objects.filter(nickname=nickname).exists():
                raise NicknameAlreadyExists() from exc
            raise
        VerificationService.mark_as_used(verification)
        return user
