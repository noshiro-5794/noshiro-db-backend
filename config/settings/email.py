import os

RESEND_API_KEY = os.getenv("RESEND_API_KEY")

EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@noshiro.moe")

FRONTEND_SITE_URL = os.getenv("FRONTEND_SITE_URL", "https://noshiro.moe")
