import os

BANGUMI_API_BASE_URL = os.getenv(
    "BANGUMI_API_BASE_URL",
    "https://api.bgm.tv",
)

BANGUMI_API_KEY = os.getenv("BANGUMI_API_KEY")

BANGUMI_USER_AGENT = os.getenv(
    "BANGUMI_USER_AGENT",
    "Noshiro_5794/noshiro_db (https://github.com/LHYHENRY/noshiro_db_backend)",
)

BANGUMI_TIMEOUT = float(os.getenv("BANGUMI_TIMEOUT", "30"))

SYNC_INCREMENTAL_SUBJECT_BATCH_SIZE = int(
    os.getenv("SYNC_INCREMENTAL_SUBJECT_BATCH_SIZE", "1000")
)

SYNC_INCREMENTAL_MAX_CONSECUTIVE_ERRORS = int(
    os.getenv("SYNC_INCREMENTAL_MAX_CONSECUTIVE_ERRORS", "20")
)

SYNC_INCREMENTAL_MAX_CONSECUTIVE_SKIPS = int(
    os.getenv("SYNC_INCREMENTAL_MAX_CONSECUTIVE_SKIPS", "50")
)

AI_AGENT_API_BASE_URL = os.getenv(
    "AI_AGENT_API_BASE_URL",
    "https://api.siliconflow.cn/v1/chat/completions",
)

AI_AGENT_API_KEY = os.getenv("AI_AGENT_API_KEY")

AI_AGENT_MODEL = os.getenv(
    "AI_AGENT_MODEL",
    "Pro/zai-org/GLM-4.7",
)

AI_AGENT_TIMEOUT = float(os.getenv("AI_AGENT_TIMEOUT", "30"))

HCAPTCHA_ENABLED = os.getenv("HCAPTCHA_ENABLED", "False") == "True"

HCAPTCHA_SECRET_KEY = os.getenv("HCAPTCHA_SECRET_KEY", "")

HCAPTCHA_SITEVERIFY_URL = os.getenv(
    "HCAPTCHA_SITEVERIFY_URL",
    "https://api.hcaptcha.com/siteverify",
)

HCAPTCHA_TIMEOUT = float(os.getenv("HCAPTCHA_TIMEOUT", "5"))
