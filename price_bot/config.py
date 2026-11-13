from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


class Config:
    """Конфигурация бота из переменных окружения (Secrets/Variables GitHub Actions)."""

    def __init__(self) -> None:
        # Можно использовать существующего бота канала (@ne_perepl_bot):
        # тогда токен уже лежит в TELEGRAM_BOT_TOKEN.
        self.bot_token = _env("PRICE_BOT_TOKEN") or _env("TELEGRAM_BOT_TOKEN")
        # Точка доставки для Купера (по умолчанию — Москва, юго-восток).
        self.lat = _env_float("BOT_LAT", 55.68)
        self.lon = _env_float("BOT_LON", 37.75)
        self.state_dir = Path(_env("BOT_STATE_DIR", "state/bot"))
        self.session_minutes = _env_int("BOT_SESSION_MINUTES", 50)
        self.poll_timeout = _env_int("BOT_POLL_TIMEOUT", 30)
        # Email (необязательно, включается заданием SMTP_*).
        self.smtp_host = _env("SMTP_HOST")
        self.smtp_port = _env_int("SMTP_PORT", 465)
        self.smtp_user = _env("SMTP_USER")
        self.smtp_pass = _env("SMTP_PASS")
        self.smtp_from = _env("SMTP_FROM", self.smtp_user)
        self.smtp_to = _env("SMTP_TO")

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_pass and self.smtp_to)
