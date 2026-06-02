from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from apps.core.response import success_response
from apps.users.services.auth.login_service import LoginService
from apps.users.services.auth.token_service import TokenService
from apps.users.services.auth.password_service import PasswordService
from apps.users.services.auth.register_service import RegisterService
from apps.users.services.auth.verification_service import VerificationService
from apps.users.services.auth.captcha_service import CaptchaService
from apps.users.api.serializers.auth.auth_serializer import (
    SendCodeSerializer,
    RegisterSerializer,
    PasswordLoginSerializer,
    CodeLoginSerializer,
    ResetPasswordSerializer,
)


def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class SendCodeView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        CaptchaService.verify_hcaptcha(
            token=serializer.validated_data.get("hcaptcha_token"),
            remote_ip=get_client_ip(request),
        )
        VerificationService.send_code(
            email=serializer.validated_data["email"],
            purpose=serializer.validated_data["purpose"],
        )
        return success_response(message="verification code sent")


class RegisterView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = RegisterService.register(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
            nickname=serializer.validated_data["nickname"],
            code=serializer.validated_data["code"],
        )
        tokens = TokenService.create_tokens(user)
        response = success_response(
            data={"access": tokens["access"]},
            message="register success",
        )
        TokenService.set_refresh_cookie(response, tokens["refresh"])
        return response


class PasswordLoginView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = LoginService.password_login(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        tokens = TokenService.create_tokens(user)
        response = success_response(
            data={"access": tokens["access"]},
            message="login success",
        )
        TokenService.set_refresh_cookie(response, tokens["refresh"])
        return response


class CodeLoginView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CodeLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = LoginService.code_login(
            email=serializer.validated_data["email"],
            code=serializer.validated_data["code"],
        )
        tokens = TokenService.create_tokens(user)
        response = success_response(
            data={"access": tokens["access"]},
            message="login success",
        )
        TokenService.set_refresh_cookie(response, tokens["refresh"])
        return response


class CookieTokenRefreshView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):
        refresh = TokenService.get_refresh_token_from_cookie(request)
        tokens = TokenService.rotate_refresh_token(refresh)
        response = success_response(data={"access": tokens["access"]})
        if "refresh" in tokens:
            TokenService.set_refresh_cookie(response, tokens["refresh"])
        return response


class LogoutView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):
        refresh = TokenService.get_optional_refresh_token_from_cookie(request)
        if refresh:
            TokenService.blacklist_refresh_token(refresh)
        response = success_response(message="logout success")
        TokenService.clear_refresh_cookie(response)
        return response


class ResetPasswordView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PasswordService.reset_password(
            email=serializer.validated_data["email"],
            code=serializer.validated_data["code"],
            new_password=serializer.validated_data["new_password"],
        )
        return success_response(message="password reset success")
