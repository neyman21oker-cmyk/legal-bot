"""
Обработчики команд и сообщений для бота "ТВОЙ ЛИЧНЫЙ АГЕНТ"
Юридические категории и логика консультаций через OpenAI
"""

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction
from openai import AsyncOpenAI

from config import Config
from database import (
    get_or_create_user,
    create_session,
    get_active_session,
    close_session,
    save_message,
    get_session_messages,
    get_user_history,
    increment_consultation_count,
)

logger = logging.getLogger(__name__)

# Инициализация OpenAI клиента
openai_client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)

# ── Юридические категории ──────────────────────────────────────────────────────

LEGAL_CATEGORIES = {
    "military_law": {
        "emoji": "🎖️",
        "title": "Военное право",
        "description": "Призыв, мобилизация, права военнослужащих, увольнение из армии",
    },
    "labor_law": {
        "emoji": "💼",
        "title": "Трудовое право",
        "description": "Трудовые договоры, увольнение, льготы, выплаты",
    },
    "family_law": {
        "emoji": "👨‍👩‍👧",
        "title": "Семейное право",
        "description": "Развод, алименты, раздел имущества, усыновление",
    },
    "housing_law": {
        "emoji": "🏠",
        "title": "Жилищное право",
        "description": "Аренда, ипотека, приватизация, споры с соседями",
    },
    "criminal_law": {
        "emoji": "⚖️",
        "title": "Уголовное право",
        "description": "Права при задержании, административные нарушения, апелляции",
    },
    "civil_law": {
        "emoji": "📋",
        "title": "Гражданское право",
        "description": "Договоры, долги, возмещение ущерба, наследство",
    },
    "administrative_law": {
        "emoji": "🏛️",
        "title": "Административное право",
        "description": "Жалобы на госорганы, штрафы, разрешения",
    },
    "social_law": {
        "emoji": "🤝",
        "title": "Социальное право",
        "description": "Пенсии, льготы, пособия, инвалидность",
    },
    "other": {
        "emoji": "❓",
        "title": "Другой вопрос",
        "description": "Любой другой юридический вопрос",
    },
}

# ── Системный промпт для юридического консультанта ────────────────────────────

SYSTEM_PROMPT = """Ты — "ТВОЙ ЛИЧНЫЙ АГЕНТ", профессиональный юридический консультант с глубокими знаниями российского законодательства. Специализируешься на военном праве, но компетентен во всех отраслях права.

Твоя задача:
1. Давать чёткие, практичные юридические консультации на русском языке
2. Объяснять сложные юридические термины доступным языком
3. Ссылаться на конкретные статьи законов и нормативные акты РФ
4. Предлагать конкретные шаги для решения проблемы
5. При необходимости рекомендовать обратиться к специалисту очно

Правила общения:
- Будь профессиональным, но доступным
- Не давай советов, которые могут навредить пользователю
- Всегда предупреждай, что консультация носит информационный характер
- Если вопрос выходит за рамки юридической помощи — вежливо перенаправь
- Задавай уточняющие вопросы, если ситуация требует деталей

Формат ответов:
- Структурируй ответ: краткое резюме → правовая база → практические шаги
- Используй нумерованные списки для шагов
- Выделяй важные термины и статьи законов
- Завершай ответ конкретной рекомендацией"""


# ── Вспомогательные функции ───────────────────────────────────────────────────

def build_categories_keyboard() -> InlineKeyboardMarkup:
    """Создать клавиатуру с категориями юридических вопросов."""
    keyboard = []
    items = list(LEGAL_CATEGORIES.items())
    # Располагаем кнопки по 2 в ряд
    for i in range(0, len(items) - 1, 2):
        key1, cat1 = items[i]
        key2, cat2 = items[i + 1]
        keyboard.append([
            InlineKeyboardButton(
                f"{cat1['emoji']} {cat1['title']}", callback_data=f"cat_{key1}"
            ),
            InlineKeyboardButton(
                f"{cat2['emoji']} {cat2['title']}", callback_data=f"cat_{key2}"
            ),
        ])
    # Последняя категория ("Другой вопрос") — отдельная строка
    if len(items) % 2 != 0:
        last_key, last_cat = items[-1]
        keyboard.append([
            InlineKeyboardButton(
                f"{last_cat['emoji']} {last_cat['title']}",
                callback_data=f"cat_{last_key}",
            )
        ])
    return InlineKeyboardMarkup(keyboard)


def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Создать главное меню."""
    keyboard = [
        [
            InlineKeyboardButton("📝 Новая консультация", callback_data="new_consultation"),
            InlineKeyboardButton("📚 История", callback_data="show_history"),
        ],
        [
            InlineKeyboardButton("📋 Категории", callback_data="show_categories"),
            InlineKeyboardButton("❓ Помощь", callback_data="show_help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def get_ai_response(messages: list[dict], user_question: str) -> str:
    """Получить ответ от OpenAI GPT."""
    try:
        # Формируем контекст разговора
        conversation = [{"role": "system", "content": SYSTEM_PROMPT}]
        # Добавляем историю (последние N сообщений)
        history_limit = Config.MAX_HISTORY_MESSAGES * 2  # user + assistant пары
        if len(messages) > history_limit:
            messages = messages[-history_limit:]
        conversation.extend(messages)

        response = await openai_client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=conversation,
            max_tokens=Config.MAX_TOKENS,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"Ошибка OpenAI API: {e}")
        return (
            "⚠️ Произошла техническая ошибка при обработке вашего запроса. "
            "Пожалуйста, попробуйте ещё раз или обратитесь позже."
        )


# ── Обработчики команд ────────────────────────────────────────────────────────

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    user = update.effective_user
    db_user = get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    welcome_text = (
        f"👋 Здравствуйте, {user.first_name}!\n\n"
        "⚖️ *ТВОЙ ЛИЧНЫЙ АГЕНТ* — ваш персональный юридический консультант.\n\n"
        "Здесь вы можете получить консультацию по любым правовым вопросам:\n"
        "• Военное право и права военнослужащих\n"
        "• Трудовые споры и увольнение\n"
        "• Семейные и жилищные вопросы\n"
        "• Уголовные и административные дела\n"
        "• И многое другое\n\n"
        "📌 *Как начать?*\n"
        "Просто напишите свой вопрос или выберите категорию ниже.\n\n"
        "_⚠️ Консультации носят информационный характер и не заменяют "
        "официальную юридическую помощь._"
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=build_main_menu_keyboard(),
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help."""
    help_text = (
        "📖 *Как пользоваться ботом:*\n\n"
        "1️⃣ *Задайте вопрос* — просто напишите его текстом\n"
        "2️⃣ *Выберите категорию* — используйте /categories\n"
        "3️⃣ *Новая консультация* — /new (сбрасывает контекст)\n"
        "4️⃣ *История* — /history (последние консультации)\n\n"
        "💡 *Советы для лучшего результата:*\n"
        "• Описывайте ситуацию максимально подробно\n"
        "• Указывайте регион и даты, если важно\n"
        "• Задавайте уточняющие вопросы\n\n"
        "📞 *Команды:*\n"
        "/start — главное меню\n"
        "/new — начать новую консультацию\n"
        "/categories — выбрать категорию\n"
        "/history — история консультаций\n"
        "/help — эта справка"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


async def category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /categories."""
    await update.message.reply_text(
        "📋 *Выберите категорию вашего вопроса:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=build_categories_keyboard(),
    )


async def new_consultation_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Обработчик команды /new — начать новую консультацию."""
    user = update.effective_user
    db_user = get_or_create_user(telegram_id=user.id)

    # Закрыть активную сессию, если есть
    active = get_active_session(db_user["id"])
    if active:
        close_session(active["id"])

    await update.message.reply_text(
        "🆕 *Новая консультация начата.*\n\n"
        "Задайте ваш юридический вопрос — я готов помочь!\n\n"
        "Или выберите категорию для более точного ответа:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=build_categories_keyboard(),
    )


async def history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /history."""
    user = update.effective_user
    db_user = get_or_create_user(telegram_id=user.id)
    history = get_user_history(db_user["id"])

    if not history:
        await update.message.reply_text(
            "📭 У вас пока нет истории консультаций.\n"
            "Задайте свой первый вопрос!",
        )
        return

    text = "📚 *Ваши последние консультации:*\n\n"
    for i, session in enumerate(history, 1):
        category = LEGAL_CATEGORIES.get(session.get("category", "other"), {})
        cat_title = category.get("title", "Общий вопрос")
        date = session.get("started_at", "")[:10] if session.get("started_at") else ""
        first_msg = session.get("first_message", "")
        if first_msg and len(first_msg) > 60:
            first_msg = first_msg[:60] + "..."
        text += (
            f"*{i}.* {cat_title} ({date})\n"
            f"└ {first_msg or 'Нет данных'}\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Новая консультация", callback_data="new_consultation")]
        ]),
    )


# ── Обработчик текстовых сообщений ───────────────────────────────────────────

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Основной обработчик юридических вопросов пользователя."""
    user = update.effective_user
    user_text = update.message.text.strip()

    if not user_text:
        return

    # Получаем или создаём пользователя в БД
    db_user = get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    # Получаем или создаём активную сессию
    session = get_active_session(db_user["id"])
    if not session:
        session_id = create_session(db_user["id"])
        session = {"id": session_id}
        increment_consultation_count(db_user["id"])
    else:
        session_id = session["id"]

    # Показываем индикатор набора
    await update.message.chat.send_action(ChatAction.TYPING)

    # Сохраняем вопрос пользователя
    save_message(session_id, db_user["id"], "user", user_text)

    # Получаем историю сессии для контекста
    session_messages = get_session_messages(session_id)

    # Запрашиваем ответ у OpenAI
    ai_response = await get_ai_response(session_messages, user_text)

    # Сохраняем ответ ассистента
    save_message(session_id, db_user["id"], "assistant", ai_response)

    # Клавиатура под ответом
    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Уточнить вопрос", callback_data="continue_session"),
            InlineKeyboardButton("🆕 Новая тема", callback_data="new_consultation"),
        ],
        [
            InlineKeyboardButton("📋 Категории", callback_data="show_categories"),
        ],
    ])

    # Отправляем ответ (разбиваем если длинный)
    if len(ai_response) > 4000:
        parts = [ai_response[i:i+4000] for i in range(0, len(ai_response), 4000)]
        for j, part in enumerate(parts):
            if j == len(parts) - 1:
                await update.message.reply_text(
                    part, reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(part)
    else:
        await update.message.reply_text(ai_response, reply_markup=reply_markup)


# ── Обработчик inline-кнопок ─────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на inline-кнопки."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data

    db_user = get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    # Выбор категории
    if data.startswith("cat_"):
        category_key = data[4:]
        category = LEGAL_CATEGORIES.get(category_key, {})

        # Закрываем старую сессию и создаём новую с категорией
        active = get_active_session(db_user["id"])
        if active:
            close_session(active["id"])
        create_session(db_user["id"], category_key)
        increment_consultation_count(db_user["id"])

        cat_title = category.get("title", "Общий вопрос")
        cat_desc = category.get("description", "")
        cat_emoji = category.get("emoji", "⚖️")

        await query.edit_message_text(
            f"{cat_emoji} *{cat_title}*\n\n"
            f"_{cat_desc}_\n\n"
            "✏️ Опишите вашу ситуацию подробно — и я помогу разобраться!",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data == "new_consultation":
        active = get_active_session(db_user["id"])
        if active:
            close_session(active["id"])
        await query.edit_message_text(
            "🆕 *Новая консультация*\n\n"
            "Выберите категорию или просто задайте вопрос:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=build_categories_keyboard(),
        )

    elif data == "show_categories":
        await query.edit_message_text(
            "📋 *Выберите категорию вашего вопроса:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=build_categories_keyboard(),
        )

    elif data == "show_help":
        help_text = (
            "📖 *Помощь*\n\n"
            "Просто напишите ваш юридический вопрос, и я отвечу на него.\n\n"
            "Команды:\n"
            "/new — новая консультация\n"
            "/categories — выбрать тему\n"
            "/history — ваши консультации\n"
            "/help — подробная справка"
        )
        await query.edit_message_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
            ]),
        )

    elif data == "show_history":
        history = get_user_history(db_user["id"])
        if not history:
            await query.edit_message_text(
                "📭 История консультаций пока пуста.\nЗадайте первый вопрос!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
                ]),
            )
        else:
            text = "📚 *Последние консультации:*\n\n"
            for i, s in enumerate(history, 1):
                category = LEGAL_CATEGORIES.get(s.get("category", "other"), {})
                cat_title = category.get("title", "Общий вопрос")
                date = s.get("started_at", "")[:10] if s.get("started_at") else ""
                first_msg = s.get("first_message", "")
                if first_msg and len(first_msg) > 50:
                    first_msg = first_msg[:50] + "..."
                text += f"*{i}.* {cat_title} ({date})\n└ {first_msg or '—'}\n\n"
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
                ]),
            )

    elif data == "back_to_menu":
        await query.edit_message_text(
            "🏠 *Главное меню*\n\nЧем могу помочь?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=build_main_menu_keyboard(),
        )

    elif data == "continue_session":
        await query.answer("Задайте уточняющий вопрос в чате 👇", show_alert=False)
