from rest_framework_simplejwt.authentication import JWTAuthentication

from shared.observability.context import set_user_id


class ContextJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            set_user_id(result[0].pk)
        return result
