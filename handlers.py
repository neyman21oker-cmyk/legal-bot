"""Обработчики юридического бота: российское право и контекст категории."""
import logging
from openai import AsyncOpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from config import Config
from database import (get_or_create_user, create_session, get_active_session,
                      close_session, save_message, get_session_messages,
                      get_user_history, increment_consultation_count)

logger = logging.getLogger(__name__)
openai_client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
LAWYER_URL = "https://t.me/Romanneyman"
CONTACT_TEXT = "\n\n⚖️ Нужна помощь юриста?\nНапиши Роману:\n" + LAWYER_URL
LEGAL_CATEGORIES = {
    "military_law": {"emoji": "🎖️", "title": "Военное право", "description": "Контракт, призыв, мобилизация, увольнение, выплаты"},
    "labor_law": {"emoji": "💼", "title": "Трудовое право", "description": "Работа, зарплата, трудовые договоры"},
    "family_law": {"emoji": "👨‍👩‍👧", "title": "Семейное право", "description": "Развод, алименты, раздел имущества"},
    "housing_law": {"emoji": "🏠", "title": "Жилищное право", "description": "Жильё, аренда, ЖКХ"},
    "criminal_law": {"emoji": "⚖️", "title": "Уголовное право", "description": "Уголовные дела, задержание, защита"},
    "civil_law": {"emoji": "📋", "title": "Гражданское право", "description": "Договоры, долги, наследство, защита потребителей"},
    "administrative_law": {"emoji": "🏛️", "title": "Административное право", "description": "Штрафы, жалобы на госорганы"},
    "social_law": {"emoji": "🤝", "title": "Социальное право", "description": "Пенсии, пособия, льготы"},
    "other": {"emoji": "❓", "title": "Другой вопрос", "description": "Определим отрасль по твоему вопросу"},
}
SYSTEM_PROMPT = """
Ты — «ТВОЙ ЛИЧНЫЙ АГЕНТ», ИИ-помощник по российскому праву.
ЮРИСДИКЦИЯ: Россия по умолчанию. Не спрашивай страну и не предлагай
выбрать законодательство. Только если пользователь явно сообщает о другой
стране или иностранном элементе, объясни ограничение и уточни применимое право.
Регион уточняй лишь тогда, когда он действительно влияет на ответ.

ОТРАСЛЬ ПРАВА И КОНТЕКСТ:
Перед ответом определи отрасль по выбранной категории, текущему вопросу
и истории. Не выводи внутренние рассуждения. В начале содержательной
консультации коротко обозначай: «🎖️ Военное право РФ» или аналогичную
подходящую отрасль. На приветствие достаточно короткого приглашения задать вопрос.
Если выбрана конкретная категория, неоднозначные слова толкуй в её контексте.
Если вопрос явно относится к другой отрасли, разбирай фактический вопрос,
кратко отметив смену темы. При пересечении отраслей учитывай обе.
Если категория не выбрана или выбран «Другой вопрос», определяй отрасль сам.
Если вопрос реально неоднозначен и история не помогает, задай один точный
вопрос о сути ситуации, а не спрашивай пользователя, какую отрасль выбрать.
Неюридические запросы вежливо перенаправляй к правовым вопросам.

ВОЕННОЕ ПРАВО:
В военной категории «контракт» по умолчанию означает контракт о прохождении
военной службы, «увольнение» — увольнение с военной службы, а «выплаты» —
выплаты военнослужащему. Сохраняй этот контекст в уточняющих вопросах.
Не применяй к военной службе правила возврата товаров, дистанционной продажи,
потребительский период отказа или обычное увольнение по Трудовому кодексу.
Не обещай прекращение военной службы из-за того, что человек передумал.
Различай подписание контракта, его вступление в силу и прохождение службы.
Учитывай специальные правила периода мобилизации; не обещай увольнение
по окончании срока контракта без проверки применимых специальных норм.
При необходимости используй как правовые ориентиры закон № 53-ФЗ,
закон № 76-ФЗ, Положение о порядке прохождения военной службы (Указ № 1237),
специальные нормы, включая Указ № 647, только если они относятся к вопросу.
Это не исчерпывающий список и не гарантия актуальности редакций.
Не приписывай этим актам неподтверждённое содержание.

ТОЧНОСТЬ:
Объясняй применимую правовую основу, а не отделывайся «проверь закон».
Не выдумывай статьи, основания увольнения, сроки, судебные решения.
Номер статьи указывай только при достаточной уверенности; иначе назови акт
и честно обозначь, что конкретную норму и действующую редакцию надо проверить.
У тебя нет онлайн-поиска: не утверждай, что проверил действующие редакции.
Не обещай результат. Если деталей недостаточно, дай осторожный общий ориентир
и задай 1–2 существенных вопроса. Учитывай уже сообщённые факты.
При риске пропустить процессуальный срок рекомендуй без промедления его уточнить.
Кратко отмечай информационный характер консультации без длинных дисклеймеров.

СТИЛЬ:
Общайся на «ты», тепло, уважительно и по делу; на «вы» — по просьбе.
Простые слова, короткие абзацы, уместные 1–3 эмодзи, без канцелярита.
Сначала суть и правовая основа, затем практические шаги, если они нужны.
Не обесценивай серьёзные проблемы. Не выдавай себя за адвоката или человека.
Не проси пароли, паспортные данные и реквизиты. Предлагай обезличить документы.
Обычный текст, без Markdown, звёздочек, HTML и таблиц.
Контакт юриста не добавляй: код добавляет его автоматически.
"""

def lawyer_button():
    return InlineKeyboardButton("✍️ Написать юристу", url=LAWYER_URL)

def build_categories_keyboard():
    items = list(LEGAL_CATEGORIES.items())
    rows = [[InlineKeyboardButton(f"{cat['emoji']} {cat['title']}", callback_data=f"cat_{key}")
             for key, cat in items[i:i + 2]] for i in range(0, len(items), 2)]
    return InlineKeyboardMarkup(rows + [[lawyer_button()]])

def build_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Новая консультация", callback_data="new_consultation"),
         InlineKeyboardButton("📚 История", callback_data="show_history")],
        [InlineKeyboardButton("📋 Категории", callback_data="show_categories"),
         InlineKeyboardButton("❓ Помощь", callback_data="show_help")], [lawyer_button()]])

def build_answer_keyboard():
    return InlineKeyboardMarkup([[lawyer_button()],
        [InlineKeyboardButton("🔄 Уточнить вопрос", callback_data="continue_session"),
         InlineKeyboardButton("🆕 Новая тема", callback_data="new_consultation")],
        [InlineKeyboardButton("📋 Категории", callback_data="show_categories")]])

def ensure_user(user):
    return get_or_create_user(telegram_id=user.id, username=user.username,
                              first_name=user.first_name, last_name=user.last_name)

def close_current_session(user_id):
    active = get_active_session(user_id)
    if active:
        close_session(active["id"])

def split_text(text, limit=3500):
    parts, current, units = [], [], 0
    for char in text:
        size = len(char.encode("utf-16-le")) // 2
        if units + size > limit:
            parts.append("".join(current))
            current, units = [], 0
        current.append(char)
        units += size
    if current:
        parts.append("".join(current))
    return parts or ["Не получилось подготовить ответ. Попробуй ещё раз."]

def format_history(history):
    if not history:
        return "📭 История пока пуста. Задай первый вопрос!"
    lines = ["📚 Последние консультации:\n"]
    for i, session in enumerate(history[:10], 1):
        title = LEGAL_CATEGORIES.get(session.get("category"), {}).get("title", "Общий вопрос")
        date = str(session.get("started_at") or "")[:10]
        first = str(session.get("first_message") or "Нет данных")[:60]
        lines.append(f"{i}. {title} ({date})\n└ {first}\n")
    return "\n".join(lines)

HELP_TEXT = ("📖 Помогаю с юридическими вопросами по законодательству России.\n\n"
             "Выбери категорию или опиши ситуацию — определю отрасль по вопросу.\n"
             "Не присылай паспортные данные, пароли и реквизиты.\n\n"
             "/start — меню\n/new — новая консультация\n/categories — категории\n"
             "/history — история\n/help — помощь")

async def get_ai_response(messages: list[dict], user_question: str, category_key=None) -> str:
    try:
        limit = max(1, int(Config.MAX_HISTORY_MESSAGES)) * 2
        history = [{"role": m["role"], "content": m["content"]} for m in messages
                   if m["role"] in ("user", "assistant") and m["content"]][-limit:]
        if not history or history[-1] != {"role": "user", "content": user_question}:
            history.append({"role": "user", "content": user_question})
        category = LEGAL_CATEGORIES.get(category_key)
        if category and category_key != "other":
            category_context = (f"Выбранная категория этой сессии: {category['title']}. "
                                f"Область: {category['description']}. "
                                "Используй её для толкования неоднозначных вопросов.")
        else:
            category_context = "Конкретная категория не выбрана. Определи отрасль по вопросу и истории."
        conversation = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + category_context}] + history
        response = await openai_client.chat.completions.create(
            model=Config.OPENAI_MODEL, messages=conversation,
            max_tokens=Config.MAX_TOKENS, temperature=0.3)
        answer = response.choices[0].message.content
        if not answer or not answer.strip():
            raise ValueError("Пустой ответ OpenAI")
        return answer.strip()
    except Exception:
        logger.exception("Ошибка OpenAI")
        return "⚠️ Не получилось подготовить ответ из-за технической ошибки. Попробуй позже или напиши юристу."

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_user(update.effective_user)
    await update.message.reply_text(
        "👋 Привет! Я — «ТВОЙ ЛИЧНЫЙ АГЕНТ», ИИ-помощник по российскому праву.\n\n"
        "Выбери категорию или напиши вопрос. Помогу разобраться простыми словами.\n\n"
        "Консультации информационные и не заменяют индивидуальную помощь юриста.",
        parse_mode=None, reply_markup=build_main_menu_keyboard())

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode=None, reply_markup=build_main_menu_keyboard())

async def category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📋 Выбери категорию:", parse_mode=None, reply_markup=build_categories_keyboard())

async def new_consultation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db_user = ensure_user(update.effective_user)
    close_current_session(db_user["id"])
    context.user_data.pop("legal_category", None)
    await update.message.reply_text("🆕 Новая консультация. Выбери категорию или напиши вопрос:",
                                    parse_mode=None, reply_markup=build_categories_keyboard())

async def history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db_user = ensure_user(update.effective_user)
    await update.message.reply_text(format_history(get_user_history(db_user["id"])),
                                    parse_mode=None, reply_markup=build_main_menu_keyboard())

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not update.message.text.strip():
        return
    user_text = update.message.text.strip()
    db_user = ensure_user(update.effective_user)
    session = get_active_session(db_user["id"])
    if session:
        session_id = session["id"]
        category_key = session.get("category") or context.user_data.get("legal_category")
    else:
        session_id = create_session(db_user["id"])
        increment_consultation_count(db_user["id"])
        category_key = None
        context.user_data.pop("legal_category", None)
    await update.message.chat.send_action(ChatAction.TYPING)
    save_message(session_id, db_user["id"], "user", user_text)
    answer = await get_ai_response(get_session_messages(session_id), user_text, category_key)
    save_message(session_id, db_user["id"], "assistant", answer)
    parts = split_text(answer)
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        await update.message.reply_text(part + CONTACT_TEXT if last else part, parse_mode=None,
            reply_markup=build_answer_keyboard() if last else None, disable_web_page_preview=True)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    db_user = ensure_user(query.from_user)
    if data == "continue_session":
        await query.message.reply_text("✏️ Напиши уточняющий вопрос — продолжим эту консультацию.", parse_mode=None)
    elif data.startswith("cat_"):
        key = data[4:]
        cat = LEGAL_CATEGORIES.get(key)
        if not cat:
            return
        close_current_session(db_user["id"])
        create_session(db_user["id"], key)
        increment_consultation_count(db_user["id"])
        context.user_data["legal_category"] = key
        await query.edit_message_text(f"{cat['emoji']} {cat['title']} РФ\n\n{cat['description']}\n\nОпиши ситуацию:",
            parse_mode=None, reply_markup=InlineKeyboardMarkup([[lawyer_button()]]))
    elif data in ("new_consultation", "show_categories"):
        if data == "new_consultation":
            close_current_session(db_user["id"])
            context.user_data.pop("legal_category", None)
        await query.edit_message_text("📋 Выбери категорию или напиши вопрос:",
            parse_mode=None, reply_markup=build_categories_keyboard())
    elif data in ("show_help", "show_history"):
        text = HELP_TEXT if data == "show_help" else format_history(get_user_history(db_user["id"]))
        await query.edit_message_text(text, parse_mode=None, reply_markup=InlineKeyboardMarkup([
            [lawyer_button()], [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]))
    elif data == "back_to_menu":
        await query.edit_message_text("🏠 Главное меню. Чем помочь?", parse_mode=None,
                                      reply_markup=build_main_menu_keyboard())
