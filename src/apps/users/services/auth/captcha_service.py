import requests
from django.conf import settings

from apps.users.exceptions import InvalidCaptcha


class CaptchaService:
    @classmethod
    def verify_hcaptcha(
        cls, *, token: str | None, remote_ip: str | None = None
    ) -> None:
        if not getattr(settings, "HCAPTCHA_ENABLED", False):
            return

        secret = getattr(settings, "HCAPTCHA_SECRET_KEY", "")
        if not secret or not token:
            raise InvalidCaptcha()

        payload = {
            "secret": secret,
            "response": token,
        }
        if remote_ip:
            payload["remoteip"] = remote_ip

        try:
            response = requests.post(
                getattr(
                    settings,
                    "HCAPTCHA_SITEVERIFY_URL",
                    "https://api.hcaptcha.com/siteverify",
                ),
                data=payload,
                timeout=getattr(settings, "HCAPTCHA_TIMEOUT", 5),
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise InvalidCaptcha() from exc

        if not data.get("success"):
            raise InvalidCaptcha()
