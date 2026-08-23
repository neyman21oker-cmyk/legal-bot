"""
Конфигурация бота "ТВОЙ ЛИЧНЫЙ АГЕНТ"
Загружает настройки из переменных окружения (.env файла)
"""

import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()


class Config:
    # ── Telegram ──────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # ── OpenAI ────────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "2000"))

    # ── База данных ───────────────────────────────────────────────────────────
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "legal_bot.db")

    # ── Настройки консультаций ────────────────────────────────────────────────
    # Сколько пар сообщений (вопрос+ответ) держать в контексте
    MAX_HISTORY_MESSAGES: int = int(os.getenv("MAX_HISTORY_MESSAGES", "10"))

    @classmethod
    def validate(cls) -> None:
        """Проверить наличие обязательных параметров."""
        errors = []
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN не задан")
        if not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY не задан")
        if errors:
            raise ValueError(
                "Ошибки конфигурации:\n" + "\n".join(f"  • {e}" for e in errors)
            )
