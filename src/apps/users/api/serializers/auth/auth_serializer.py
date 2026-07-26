from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.users.models import EmailVerification


class SendCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()
    purpose = serializers.ChoiceField(choices=EmailVerification.Purpose.choices)
    hcaptcha_token = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=True
    )


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        min_length=8, write_only=True, trim_whitespace=False
    )
    code = serializers.RegexField(regex=r"^\d{6}$", write_only=True)
    nickname = serializers.CharField(min_length=2, max_length=32)

    def validate_password(self, value):
        validate_password(value)
        return value


class PasswordLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class CodeLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.RegexField(regex=r"^\d{6}$", write_only=True)


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.RegexField(regex=r"^\d{6}$", write_only=True)
    new_password = serializers.CharField(
        min_length=8, write_only=True, trim_whitespace=False
    )

    def validate_new_password(self, value):
        validate_password(value)
        return value
