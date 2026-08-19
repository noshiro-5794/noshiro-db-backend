import secrets
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from apps.users.exceptions import (
    EmailSendTooFrequent,
    InvalidVerifyCode,
    VerifyCodeExpired,
)
from apps.users.models import EmailVerification, User
from apps.users.tasks.email_tasks import send_verification_email


class VerificationService:
    CODE_EXPIRE_SECONDS = 300
    SEND_INTERVAL_SECONDS = 60
    MAX_VERIFY_ATTEMPTS = 5

    @staticmethod
    def _generate_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    def _normalize_email(email: str) -> str:
        return User.objects.normalize_email(email)

    @staticmethod
    def _lock_verification_scope(*, email: str, purpose: str) -> None:
        lock_key = f"email-verification:{email}:{purpose}"
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                [lock_key],
            )

    @classmethod
    def _get_latest_verification(
        cls, *, email: str, purpose: str
    ) -> EmailVerification | None:
        return (
            EmailVerification.objects.filter(email__iexact=email, purpose=purpose)
            .order_by("-created_at")
            .first()
        )

    @classmethod
    def _check_send_interval(cls, *, email: str, purpose: str) -> None:
        latest = cls._get_latest_verification(email=email, purpose=purpose)
        if not latest:
            return
        now = timezone.now()
        delta = (now - latest.created_at).total_seconds()
        if delta < cls.SEND_INTERVAL_SECONDS:
            raise EmailSendTooFrequent()

    @classmethod
    @transaction.atomic
    def create_verification(cls, *, email: str, purpose: str) -> EmailVerification:
        email = cls._normalize_email(email)
        cls._lock_verification_scope(email=email, purpose=purpose)
        cls._check_send_interval(email=email, purpose=purpose)
        code = cls._generate_code()
        verification = EmailVerification.objects.create(
            email=email,
            code=code,
            purpose=purpose,
            expire_at=timezone.now() + timedelta(seconds=cls.CODE_EXPIRE_SECONDS),
        )
        return verification

    @classmethod
    def send_code(cls, *, email: str, purpose: str) -> EmailVerification:
        verification = cls.create_verification(email=email, purpose=purpose)
        send_verification_email.delay(verification_id=verification.id)
        return verification

    @classmethod
    @transaction.atomic
    def verify_code(cls, *, email: str, purpose: str, code: str) -> EmailVerification:
        email = cls._normalize_email(email)
        verification = (
            EmailVerification.objects.select_for_update()
            .filter(email__iexact=email, purpose=purpose, is_used=False)
            .order_by("-created_at")
            .first()
        )
        if not verification:
            raise InvalidVerifyCode()
        if verification.attempts >= cls.MAX_VERIFY_ATTEMPTS:
            raise InvalidVerifyCode()
        if verification.expire_at < timezone.now():
            raise VerifyCodeExpired()
        if not secrets.compare_digest(verification.code, code):
            verification.attempts += 1
            verification.save(update_fields=["attempts"])
            raise InvalidVerifyCode()
        return verification

    @classmethod
    def mark_as_used(cls, verification: EmailVerification) -> None:
        verification.is_used = True
        verification.save(update_fields=["is_used"])
