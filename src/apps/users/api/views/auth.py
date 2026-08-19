from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.api.serializers.auth import (
    CodeLoginSerializer,
    PasswordLoginSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    SendCodeSerializer,
)
from apps.users.api.serializers.contracts import (
    AcceptedSerializer,
    AccessTokenSerializer,
)
from apps.users.services.auth.captcha_service import CaptchaService
from apps.users.services.auth.login_service import LoginService
from apps.users.services.auth.password_service import PasswordService
from apps.users.services.auth.register_service import RegisterService
from apps.users.services.auth.token_service import TokenService
from apps.users.services.auth.verification_service import VerificationService
from shared.api.contracts import api_responses
from shared.http import get_client_ip


class SendCodeView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "verification"

    @extend_schema(
        request=SendCodeSerializer,
        responses=api_responses({202: AcceptedSerializer}, errors=(400, 429)),
    )
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
        return Response({"status": "accepted"}, status=status.HTTP_202_ACCEPTED)


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth_register"

    @extend_schema(
        request=RegisterSerializer,
        responses=api_responses({201: AccessTokenSerializer}, errors=(400, 409, 429)),
    )
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
        response = Response(
            {"access": tokens["access"]}, status=status.HTTP_201_CREATED
        )
        TokenService.set_refresh_cookie(response, tokens["refresh"])
        return response


class PasswordLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth_login"

    @extend_schema(
        request=PasswordLoginSerializer,
        responses=api_responses({200: AccessTokenSerializer}, errors=(400, 401, 429)),
    )
    def post(self, request):
        serializer = PasswordLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = LoginService.password_login(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        tokens = TokenService.create_tokens(user)
        response = Response({"access": tokens["access"]})
        TokenService.set_refresh_cookie(response, tokens["refresh"])
        return response


class CodeLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth_login"

    @extend_schema(
        request=CodeLoginSerializer,
        responses=api_responses({200: AccessTokenSerializer}, errors=(400, 401, 429)),
    )
    def post(self, request):
        serializer = CodeLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = LoginService.code_login(
            email=serializer.validated_data["email"],
            code=serializer.validated_data["code"],
        )
        tokens = TokenService.create_tokens(user)
        response = Response({"access": tokens["access"]})
        TokenService.set_refresh_cookie(response, tokens["refresh"])
        return response


class CookieTokenRefreshView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth_refresh"

    @extend_schema(
        request=None,
        responses=api_responses({200: AccessTokenSerializer}, errors=(401, 429)),
    )
    def post(self, request):
        refresh = TokenService.get_refresh_token_from_cookie(request)
        tokens = TokenService.rotate_refresh_token(refresh)
        response = Response({"access": tokens["access"]})
        if "refresh" in tokens:
            TokenService.set_refresh_cookie(response, tokens["refresh"])
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses=api_responses({204: None}, errors=()))
    def post(self, request):
        refresh = TokenService.get_optional_refresh_token_from_cookie(request)
        if refresh:
            TokenService.blacklist_refresh_token(refresh)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        TokenService.clear_refresh_cookie(response)
        return response


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth_reset"

    @extend_schema(
        request=ResetPasswordSerializer,
        responses=api_responses({204: None}, errors=(400, 429)),
    )
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PasswordService.reset_password(
            email=serializer.validated_data["email"],
            code=serializer.validated_data["code"],
            new_password=serializer.validated_data["new_password"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
