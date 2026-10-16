"""
Обработчики команд и сообщений бота «ТВОЙ ЛИЧНЫЙ АГЕНТ».
"""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
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

openai_client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)

LAWYER_URL = "https://t.me/Romanneyman"

CONTACT_TEXT = (
    "\n\n⚖️ Нужна помощь юриста?\n"
    "Напиши Роману, чтобы оставить заявку:\n"
    f"{LAWYER_URL}"
)

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
        "description": "Права при задержании, уголовные дела, обжалование приговора",
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

SYSTEM_PROMPT = """
Ты — «ТВОЙ ЛИЧНЫЙ АГЕНТ», ИИ-помощник по юридическим вопросам.
Помогай человеку разобраться в ситуации простыми словами.
Не выдавай себя за человека, адвоката или юриста с личной практикой.

СТИЛЬ ОБЩЕНИЯ:
- Общайся на «ты», тепло и уважительно. Если пользователь просит
  обращаться на «вы», уважай эту просьбу.
- Не используй канцелярит, нравоучения и длинные вступления.
- Проявляй сочувствие, когда это уместно, без шаблонных фраз.
- Не обесценивай проблему словами «не переживай» или «всё просто».
- Используй 1–3 уместных эмодзи. В ситуациях насилия, задержания,
  утраты или опасности избегай весёлых эмодзи и шуток.
- Не начинай каждое сообщение с приветствия.

КАК ПОМОГАТЬ:
- Сначала коротко ответь по сути.
- Если уместно, предложи 2–4 конкретных практических шага.
- Объясняй юридические термины обычными словами.
- Если важных данных не хватает, задай 1–2 уточняющих вопроса.
- Уточняй страну и регион, если они неизвестны и от них зависит ответ.
  Не считай автоматически, что вопрос касается законодательства РФ.
- Учитывай предыдущие сообщения.
- Не проси паспортные данные, банковские реквизиты, пароли.
  Предлагай скрывать персональные данные в документах.

ТОЧНОСТЬ:
- Не выдумывай статьи законов, сроки, судебные решения и факты.
- Приводи номера статей только при достаточной уверенности.
- Не утверждай, что проверил законодательство онлайн:
  в этом боте у тебя нет доступа к поиску.
- Если не уверен, прямо скажи об этом и объясни, что нужно проверить.
- Не обещай выигрыш дела, получение выплаты или другой результат.
- При возможных срочных процессуальных сроках предупреждай,
  что их нужно уточнить без промедления.
- Кратко поясняй, что ответ информационный и не заменяет
  индивидуальную консультацию юриста. Без длинного дисклеймера.

ФОРМАТ:
- Пиши короткими абзацами.
- Для шагов используй обычную нумерацию.
- Не используй Markdown, HTML и таблицы: ответы идут обычным текстом.
- Не навязывай большую структуру для простого вопроса.
- Не добавляй контакт юриста и рекламный блок:
  их автоматически добавляет код.
"""


def lawyer_button():
    return InlineKeyboardButton("✍️ Написать юристу", url=LAWYER_URL)


def build_categories_keyboard() -> InlineKeyboardMarkup:
    items = list(LEGAL_CATEGORIES.items())
    keyboard = []
    for i in range(0, len(items), 2):
        row = [
            InlineKeyboardButton(
                f"{cat['emoji']} {cat['title']}",
                callback_data=f"cat_{key}",
            )
            for key, cat in items[i:i + 2]
        ]
        keyboard.append(row)
    keyboard.append([lawyer_button()])
    return InlineKeyboardMarkup(keyboard)


def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 Новая консультация", callback_data="new_consultation"),
            InlineKeyboardButton("📚 История", callback_data="show_history"),
        ],
        [
            InlineKeyboardButton("📋 Категории", callback_data="show_categories"),
            InlineKeyboardButton("❓ Помощь", callback_data="show_help"),
        ],
        [lawyer_button()],
    ])


def build_answer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [lawyer_button()],
        [
            InlineKeyboardButton("🔄 Уточнить вопрос", callback_data="continue_session"),
            InlineKeyboardButton("🆕 Новая тема", callback_data="new_consultation"),
        ],
        [InlineKeyboardButton("📋 Категории", callback_data="show_categories")],
    ])


def split_text(text, limit=3500):
    parts = []
    current = []
    units = 0
    for char in text:
        size = len(char.encode("utf-16-le")) // 2
        if units + size > limit:
            parts.append("".join(current))
            current = []
            units = 0
        current.append(char)
        units += size
    if current:
        parts.append("".join(current))
    return parts or ["Не получилось подготовить ответ. Попробуй ещё раз."]


def ensure_user(user):
    return get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )


def close_current_session(user_id):
    active = get_active_session(user_id)
    if active:
        close_session(active["id"])


def format_history(history):
    if not history:
        return "📭 История консультаций пока пуста.\nЗадай первый вопрос!"
    lines = ["📚 Последние консультации:\n"]
    for i, session in enumerate(history[:10], 1):
        category = LEGAL_CATEGORIES.get(session.get("category"), {})
        title = category.get("title", "Общий вопрос")
        date = str(session.get("started_at") or "")[:10]
        first = str(session.get("first_message") or "Нет данных")
        if len(first) > 60:
            first = first[:60] + "…"
        lines.append(f"{i}. {title} ({date})\n└ {first}\n")
    return "\n".join(lines)


HELP_TEXT = (
    "📖 Как пользоваться ботом\n\n"
    "Просто напиши юридический вопрос своими словами.\n"
    "Укажи страну, регион и важные даты, если они относятся к делу.\n"
    "Не присылай пароли, паспортные данные и реквизиты карт.\n\n"
    "/start — главное меню\n"
    "/new — новая консультация\n"
    "/categories — выбрать тему\n"
    "/history — история консультаций\n"
    "/help — эта справка"
)


async def get_ai_response(messages: list[dict], user_question: str) -> str:
    try:
        limit = max(1, int(Config.MAX_HISTORY_MESSAGES)) * 2
        history = [
            {"role": item["role"], "content": item["content"]}
            for item in messages
            if item["role"] in ("user", "assistant") and item["content"]
        ][-limit:]
        if not history or history[-1]["role"] != "user":
            history.append({"role": "user", "content": user_question})
        conversation = [{"role": "system", "content": SYSTEM_PROMPT}] + history
        response = await openai_client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=conversation,
            max_tokens=Config.MAX_TOKENS,
            temperature=0.7,
        )
        answer = response.choices[0].message.content
        if not answer or not answer.strip():
            raise ValueError("OpenAI вернул пустой ответ")
        return answer.strip()
    except Exception:
        logger.exception("Ошибка при получении ответа OpenAI")
        return (
            "⚠️ Сейчас не получилось подготовить ответ из-за технической ошибки. "
            "Попробуй немного позже или напиши юристу напрямую."
        )


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    ensure_user(user)
    text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я — «ТВОЙ ЛИЧНЫЙ АГЕНТ», ИИ-помощник по юридическим вопросам.\n\n"
        "Помогу разобраться с работой, жильём, семейными спорами, "
        "военным правом и другими правовыми вопросами.\n\n"
        "📌 Напиши свой вопрос или выбери категорию в меню.\n\n"
        "Ответы носят информационный характер и не заменяют "
        "индивидуальную консультацию юриста."
    )
    await update.message.reply_text(
        text, parse_mode=None, reply_markup=build_main_menu_keyboard()
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        HELP_TEXT, parse_mode=None, reply_markup=build_main_menu_keyboard()
    )


async def category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📋 Выбери категорию вопроса:",
        parse_mode=None,
        reply_markup=build_categories_keyboard(),
    )


async def new_consultation_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    db_user = ensure_user(update.effective_user)
    close_current_session(db_user["id"])
    await update.message.reply_text(
        "🆕 Начинаем новую консультацию.\n\nВыбери категорию или напиши вопрос:",
        parse_mode=None,
        reply_markup=build_categories_keyboard(),
    )


async def history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db_user = ensure_user(update.effective_user)
    history = get_user_history(db_user["id"])
    await update.message.reply_text(
        format_history(history),
        parse_mode=None,
        reply_markup=build_main_menu_keyboard(),
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    user_text = update.message.text.strip()
    if not user_text:
        return

    db_user = ensure_user(update.effective_user)
    session = get_active_session(db_user["id"])
    if session:
        session_id = session["id"]
    else:
        session_id = create_session(db_user["id"])
        increment_consultation_count(db_user["id"])

    await update.message.chat.send_action(ChatAction.TYPING)
    save_message(session_id, db_user["id"], "user", user_text)
    messages = get_session_messages(session_id)
    answer = await get_ai_response(messages, user_text)
    save_message(session_id, db_user["id"], "assistant", answer)

    parts = split_text(answer)
    for index, part in enumerate(parts):
        is_last = index == len(parts) - 1
        await update.message.reply_text(
            text=part + CONTACT_TEXT if is_last else part,
            parse_mode=None,
            reply_markup=build_answer_keyboard() if is_last else None,
            disable_web_page_preview=True,
        )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    data = query.data or ""

    if data == "continue_session":
        await query.answer()
        await query.message.reply_text(
            "✏️ Напиши уточняющий вопрос в чат — продолжим эту консультацию.",
            parse_mode=None,
        )
        return

    await query.answer()
    db_user = ensure_user(query.from_user)

    if data.startswith("cat_"):
        category_key = data[4:]
        category = LEGAL_CATEGORIES.get(category_key)
        if not category:
            return
        close_current_session(db_user["id"])
        create_session(db_user["id"], category_key)
        increment_consultation_count(db_user["id"])
        await query.edit_message_text(
            f"{category['emoji']} {category['title']}\n\n"
            f"{category['description']}\n\n"
            "✏️ Опиши свою ситуацию — помогу разобраться.",
            parse_mode=None,
            reply_markup=InlineKeyboardMarkup([[lawyer_button()]]),
        )

    elif data == "new_consultation":
        close_current_session(db_user["id"])
        await query.edit_message_text(
            "🆕 Новая консультация\n\nВыбери категорию или напиши вопрос:",
            parse_mode=None,
            reply_markup=build_categories_keyboard(),
        )

    elif data == "show_categories":
        await query.edit_message_text(
            "📋 Выбери категорию вопроса:",
            parse_mode=None,
            reply_markup=build_categories_keyboard(),
        )

    elif data == "show_help":
        await query.edit_message_text(
            HELP_TEXT,
            parse_mode=None,
            reply_markup=InlineKeyboardMarkup([
                [lawyer_button()],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")],
            ]),
        )

    elif data == "show_history":
        history = get_user_history(db_user["id"])
        await query.edit_message_text(
            format_history(history),
            parse_mode=None,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "📝 Новая консультация", callback_data="new_consultation"
                )],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")],
            ]),
        )

    elif data == "back_to_menu":
        await query.edit_message_text(
            "🏠 Главное меню\n\nЧем помочь?",
            parse_mode=None,
            reply_markup=build_main_menu_keyboard(),
        )
