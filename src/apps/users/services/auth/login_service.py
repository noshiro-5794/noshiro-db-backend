from django.contrib.auth import authenticate
from django.db import transaction

from apps.users.exceptions import InvalidEmailOrPassword, UserNotFound
from apps.users.models import EmailVerification, User
from apps.users.services.auth.verification_service import VerificationService


class LoginService:
    @classmethod
    def password_login(cls, *, email: str, password: str) -> User:
        user = authenticate(username=email, password=password)
        if not user:
            # Preserve case-insensitive login for accounts created before email
            # normalization was enforced by the user manager.
            candidate = User.objects.filter(email__iexact=email).only("email").first()
            if candidate and candidate.email != email:
                user = authenticate(username=candidate.email, password=password)
        if not user:
            raise InvalidEmailOrPassword()
        return user

    @classmethod
    @transaction.atomic
    def code_login(cls, *, email: str, code: str) -> User:
        verification = VerificationService.verify_code(
            email=email, purpose=EmailVerification.Purpose.LOGIN, code=code
        )
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise UserNotFound()
        VerificationService.mark_as_used(verification)
        return user
