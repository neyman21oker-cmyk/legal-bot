"""
Модуль работы с базой данных SQLite
Хранение истории консультаций пользователей
"""

import sqlite3
import logging
from datetime import datetime
from config import Config

logger = logging.getLogger(__name__)


def get_connection():
    """Получение соединения с базой данных."""
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Инициализация базы данных и создание таблиц."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Таблица пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                consultation_count INTEGER DEFAULT 0
            )
        """)

        # Таблица сессий консультаций
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Таблица сообщений
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,  -- 'user' или 'assistant'
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        conn.commit()
        logger.info("Таблицы базы данных созданы/проверены")


def get_or_create_user(telegram_id: int, username: str = None,
                        first_name: str = None, last_name: str = None) -> dict:
    """Получить или создать пользователя."""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = cursor.fetchone()

        if not user:
            cursor.execute("""
                INSERT INTO users (telegram_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            """, (telegram_id, username, first_name, last_name))
            conn.commit()
            cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            user = cursor.fetchone()
        else:
            # Обновляем данные пользователя
            cursor.execute("""
                UPDATE users SET username = ?, first_name = ?, last_name = ?
                WHERE telegram_id = ?
            """, (username, first_name, last_name, telegram_id))
            conn.commit()

        return dict(user)


def create_session(user_id: int, category: str = None) -> int:
    """Создать новую сессию консультации."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sessions (user_id, category)
            VALUES (?, ?)
        """, (user_id, category))
        conn.commit()
        return cursor.lastrowid


def get_active_session(user_id: int) -> dict | None:
    """Получить активную сессию пользователя."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM sessions
            WHERE user_id = ? AND ended_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
        """, (user_id,))
        session = cursor.fetchone()
        return dict(session) if session else None


def close_session(session_id: int):
    """Закрыть сессию консультации."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE sessions SET ended_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (session_id,))
        conn.commit()


def save_message(session_id: int, user_id: int, role: str, content: str):
    """Сохранить сообщение в базу данных."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages (session_id, user_id, role, content)
            VALUES (?, ?, ?, ?)
        """, (session_id, user_id, role, content))

        # Увеличить счётчик сообщений в сессии
        cursor.execute("""
            UPDATE sessions SET message_count = message_count + 1
            WHERE id = ?
        """, (session_id,))

        conn.commit()


def get_session_messages(session_id: int) -> list[dict]:
    """Получить все сообщения сессии для контекста."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT role, content FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC
        """, (session_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_user_history(user_id: int, limit: int = 5) -> list[dict]:
    """Получить историю консультаций пользователя."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.category, s.started_at, s.message_count,
                   m.content as first_message
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id AND m.role = 'user'
            WHERE s.user_id = ?
            GROUP BY s.id
            ORDER BY s.started_at DESC
            LIMIT ?
        """, (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]


def increment_consultation_count(user_id: int):
    """Увеличить счётчик консультаций пользователя."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET consultation_count = consultation_count + 1
            WHERE id = ?
        """, (user_id,))
        conn.commit()
