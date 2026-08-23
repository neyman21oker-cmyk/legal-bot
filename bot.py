"""
ТВОЙ ЛИЧНЫЙ АГЕНТ — Telegram-бот для юридических консультаций
Основной файл запуска бота
"""

import logging
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from config import Config
from handlers import (
    start_handler,
    help_handler,
    category_handler,
    message_handler,
    callback_handler,
    new_consultation_handler,
    history_handler,
)
from database import init_db

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Запуск бота."""
    # Инициализация базы данных
    init_db()
    logger.info("База данных инициализирована")

    # Создание приложения
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("categories", category_handler))
    application.add_handler(CommandHandler("new", new_consultation_handler))
    application.add_handler(CommandHandler("history", history_handler))

    # Обработчик inline-кнопок
    application.add_handler(CallbackQueryHandler(callback_handler))

    # Обработчик текстовых сообщений (юридические вопросы)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)
    )

    logger.info("Бот 'ТВОЙ ЛИЧНЫЙ АГЕНТ' запущен и ожидает сообщений...")

    # Запуск бота (polling)
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
