from html import escape

import resend
from celery import shared_task
from django.conf import settings
from requests import RequestException
from resend.exceptions import ApplicationError as ResendApplicationError
from resend.exceptions import RateLimitError

BRAND_NAME = "Noshiro DB"
BRAND_TAGLINE = "Collect · Preserve · Relive"
ACCENT_COLOR = "#7F6FB0"
ACCENT_DARK = "#665792"
CODE_EXPIRE_MINUTES = 5
DEFAULT_SITE_URL = "https://noshiro.moe"

PURPOSE_COPY = {
    "register": {
        "subject": "Your Noshiro DB sign-up code",
        "title": "Create your account",
        "preheader": "Use this code to finish creating your Noshiro DB account.",
        "intro": "Enter this verification code to finish creating your Noshiro DB account.",
        "intent": "Account registration",
    },
    "login": {
        "subject": "Your Noshiro DB login code",
        "title": "Log in to Noshiro DB",
        "preheader": "Use this code to continue signing in. It expires in 5 minutes.",
        "intro": "Enter this verification code to continue signing in to your Noshiro DB workspace.",
        "intent": "Email code login",
    },
    "reset_password": {
        "subject": "Reset your Noshiro DB password",
        "title": "Reset your password",
        "preheader": "Use this code to reset your password. It expires in 5 minutes.",
        "intro": "Enter this verification code to confirm your password reset request.",
        "intent": "Password reset",
    },
}


def get_site_url() -> str:
    return getattr(settings, "FRONTEND_SITE_URL", DEFAULT_SITE_URL).rstrip("/")


def get_purpose_copy(purpose: str | None) -> dict[str, str]:
    return PURPOSE_COPY.get(purpose or "", PURPOSE_COPY["login"])


def format_code_for_display(code: str) -> str:
    return escape(code)


def build_verification_text(code: str, purpose: str | None = None) -> str:
    copy = get_purpose_copy(purpose)
    site_url = get_site_url()

    return f"""{copy["title"]}

Your {BRAND_NAME} verification code is:

{code}

This code expires in {CODE_EXPIRE_MINUTES} minutes. Do not share it with anyone.

Requested action: {copy["intent"]}
Open Noshiro DB: {site_url}

If you did not request this email, you can safely ignore it.
"""


def build_verification_html(code: str, purpose: str | None = None) -> str:
    copy = get_purpose_copy(purpose)
    safe_code = format_code_for_display(code)
    site_url = escape(get_site_url())
    safe_brand = escape(BRAND_NAME)
    safe_title = escape(copy["title"])
    safe_preheader = escape(copy["preheader"])
    safe_intro = escape(copy["intro"])
    safe_intent = escape(copy["intent"])

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <title>{safe_title}</title>
  </head>
  <body style="margin:0;padding:0;background:#f6f4ef;color:#1c1b20;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;mso-hide:all;">
      {safe_preheader}
    </div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;background:#f6f4ef;">
      <tr>
        <td align="center" style="padding:44px 16px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;max-width:560px;border-collapse:separate;border-spacing:0;">
            <tr>
              <td style="padding:0 0 14px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="vertical-align:middle;">
                      <div style="font-size:15px;line-height:22px;font-weight:700;color:#1c1b20;letter-spacing:0;">{safe_brand}</div>
                      <div style="margin-top:2px;font-size:12px;line-height:18px;color:#77717f;">{BRAND_TAGLINE}</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="overflow:hidden;border:1px solid #e3dfd8;border-radius:24px;background:#fffdf8;box-shadow:0 22px 70px rgba(44,39,56,0.10);">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="padding:34px 34px 10px;">
                      <div style="display:inline-block;padding:6px 10px;border-radius:999px;background:#f0ecf8;color:{ACCENT_DARK};font-size:12px;line-height:16px;font-weight:700;">{safe_intent}</div>
                      <h1 style="margin:18px 0 0;font-size:28px;line-height:34px;font-weight:750;color:#1c1b20;letter-spacing:0;">{safe_title}</h1>
                      <p style="margin:12px 0 0;font-size:15px;line-height:24px;color:#625d69;">
                        {safe_intro}
                      </p>
                    </td>
                  </tr>
                  <tr>
                    <td align="center" style="padding:26px 34px 24px;">
                      <div style="display:inline-block;min-width:272px;padding:20px 24px;border-radius:18px;background:#f7f3ff;border:1px solid #ded6f2;color:#1c1b20;font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;font-size:36px;line-height:44px;font-weight:800;letter-spacing:3px;text-align:center;">{safe_code}</div>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:0 34px 34px;">
                      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:separate;border-spacing:0;background:#faf8f3;border:1px solid #ebe7df;border-radius:16px;">
                        <tr>
                          <td style="padding:16px 18px;font-size:14px;line-height:22px;color:#625d69;">
                            This code expires in <strong style="color:{ACCENT_DARK};">{CODE_EXPIRE_MINUTES} minutes</strong>. For your security, do not share it with anyone.
                          </td>
                        </tr>
                      </table>
                      <p style="margin:18px 0 0;font-size:13px;line-height:21px;color:#827c89;">
                        If you did not request this email, you can ignore it. No changes will be made to your account.
                      </p>
                      <p style="margin:14px 0 0;font-size:13px;line-height:21px;color:#827c89;">
                        Open Noshiro DB: <a href="{site_url}" style="color:{ACCENT_DARK};text-decoration:none;font-weight:700;">{site_url}</a>
                      </p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td align="center" style="padding:18px 24px 0;font-size:12px;line-height:18px;color:#928c98;">
                Sent by {safe_brand}. This is an automated security email.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


@shared_task(
    autoretry_for=(RequestException, ResendApplicationError, RateLimitError),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={"max_retries": 3},
)
def send_verification_email(email: str, code: str, purpose: str | None = None) -> None:
    resend.api_key = settings.RESEND_API_KEY
    copy = get_purpose_copy(purpose)

    resend.Emails.send(
        {
            "from": f"{BRAND_NAME} <{settings.EMAIL_FROM}>",
            "to": [email],
            "subject": copy["subject"],
            "html": build_verification_html(code, purpose),
            "text": build_verification_text(code, purpose),
        }
    )
