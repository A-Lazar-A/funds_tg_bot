import functools
import json
import os
from telegram import Update
from telegram.ext import ContextTypes


def require_auth(func):
    """Декоратор для проверки авторизации пользователя."""

    @functools.wraps(func)
    async def wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ):
        user_id = update.effective_user.id

        # Проверяем доступ пользователя
        if not is_user_allowed(user_id):
            await update.message.reply_text(
                "❌ У вас нет доступа к этому боту.\n"
                "Обратитесь к администратору для получения доступа."
            )
            return

        return await func(update, context, *args, **kwargs)

    return wrapper


def is_user_allowed(user_id: int) -> bool:
    """Проверяет, разрешен ли доступ пользователю."""
    try:
        users_file_path = "data/allowed_users.json"
        if not os.path.exists(users_file_path):
            return False

        with open(users_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            allowed_users = data.get("allowed_users", [])
            return user_id in allowed_users
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return False
