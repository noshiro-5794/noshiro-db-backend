from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[3]

env = environ.Env()


def env_list(name: str, *, default: tuple[str, ...] = ()) -> list[str]:
    values = env.list(name, default=list(default))
    return [value.strip() for value in values if value.strip()]


def load_local_environment() -> None:
    env_file = BASE_DIR / ".env"
    if env_file.is_file():
        environ.Env.read_env(env_file, overwrite=False)
