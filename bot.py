import logging
import os
import tempfile
import json
import socket
import typing
import warnings
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
)
from telegram.request import HTTPXRequest
from telegram.warnings import PTBUserWarning
from config import (
    TELEGRAM_BOT_TOKEN, GOOGLE_SHEETS_CREDENTIALS_FILE,
    SPREADSHEET_ID_MY, SPREADSHEET_ID_HER, SPREADSHEET_ID_COMMON
)

from services.speech_service import SpeechService
from services.sheets_service import GoogleSheetsService
from services.category_service import CategoryService
from services.auth_decorator import require_auth, is_user_allowed
from services.telegram_utils import safe_edit_text, safe_reply_text

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
TELEGRAM_API_HOSTS = {"api.telegram.org", "api.telegram.org."}

# States for conversation
(
    WAITING_CATEGORY,
    WAITING_CONFIRMATION,
) = range(2)
category_service = CategoryService()
# Initialize services
speech_service = SpeechService(category_service)
# Создаём один экземпляр сервиса
sheets_service = GoogleSheetsService()

SPREADSHEET_IDS = [SPREADSHEET_ID_MY, SPREADSHEET_ID_HER, SPREADSHEET_ID_COMMON]

def get_sheet_choices():
    """Возвращает dict: {имя_таблицы: spreadsheet_id}"""
    return dict(sheets_service.get_available_sheets(SPREADSHEET_IDS))

ALLOWED_USERS_PATH = 'data/allowed_users.json'

# Удаляю USER_SHEETS_PATH и все обращения к нему

def load_allowed_users():
    try:
        with open(ALLOWED_USERS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('allowed_users', [])
    except Exception:
        return []

def save_allowed_users(users):
    with open(ALLOWED_USERS_PATH, 'w', encoding='utf-8') as f:
        json.dump({"allowed_users": users}, f, ensure_ascii=False, indent=2)

def get_user_entry(user_id):
    users = load_allowed_users()
    for user in users:
        if user["user_id"] == user_id:
            return user
    return None

def get_spreadsheet_id_for_user(user_id):
    users = load_allowed_users()
    sheet_choices = get_sheet_choices()
    user = get_user_entry(user_id)
    if user is None:
        # Неавторизованный пользователь
        raise Exception("User not allowed")
    # Если не выбран лист — присваиваем первую таблицу
    if not user.get("selected_sheet") or user["selected_sheet"] not in sheet_choices:
        user["selected_sheet"] = next(iter(sheet_choices.keys()))
        save_allowed_users(users)
    return sheet_choices[user["selected_sheet"]]


def force_ipv4_for_telegram() -> None:
    """Prefer IPv4 for Telegram API to avoid broken IPv6 routes in Docker."""
    original_getaddrinfo = socket.getaddrinfo

    def ipv4_first_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if host in TELEGRAM_API_HOSTS and family in (0, socket.AF_UNSPEC, socket.AF_INET6):
            ipv4_results = original_getaddrinfo(
                host,
                port,
                socket.AF_INET,
                type,
                proto,
                flags,
            )
            if ipv4_results:
                return ipv4_results
        return original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = ipv4_first_getaddrinfo


async def send_user_message(
    update: Update,
    text: str,
    **kwargs: typing.Any,
):
    """Reply in chat with retry logic for transient Telegram API failures."""
    if not update.message:
        logger.warning("Cannot reply to update without message: %s", update)
        return None
    return await safe_reply_text(update.message, text, **kwargs)


async def send_or_edit_message(
    update: Update,
    text: str,
    **kwargs: typing.Any,
):
    """Edit callback message or reply to the chat depending on update type."""
    if update.callback_query:
        return await safe_edit_text(update.callback_query.message, text, **kwargs)
    return await send_user_message(update, text, **kwargs)


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Log unhandled exceptions from telegram handlers."""
    if isinstance(context.error, (TimedOut, NetworkError)):
        logger.warning("Transient Telegram API error while handling update", exc_info=context.error)
        return

    logger.exception("Unhandled exception while processing update %s", update, exc_info=context.error)




@require_auth
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    welcome_message = (
        "👋 Привет! Я бот для учёта доходов и расходов.\n\n"
        "Вы можете:\n"
        "• Отправить голосовое сообщение с описанием операции\n"
        "• Отправить фото с QR-кодом чека\n"
        "• Использовать текстовые команды\n\n"
        "Доступные команды:\n"
        "/stats - Показать статистику за месяц\n"
        "/categories - Показать список категорий\n"
        "/delete - Удалить последнюю запись\n"
        "/select_table - Выбрать, в какую таблицу записывать транзакции\n"
        "/help - Показать это сообщение\n\n"
        "🆕 Теперь вы можете выбрать, в какую Google Таблицу будут записываться ваши транзакции: свою личную или общую. Используйте /select_table!"
    )
    await send_user_message(update, welcome_message)


@require_auth
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_message = (
        "📝 Доступные команды:\n\n"
        "/start - Начать работу с ботом\n"
        "/stats - Показать статистику за месяц\n"
        "/categories - Показать список категорий\n"
        "/delete - Удалить последнюю запись\n"
        "/help - Показать это сообщение\n\n"
        "Вы также можете:\n"
        "• Отправить голосовое сообщение\n"
        "• Отправить фото с QR-кодом\n"
        "• Написать текст в формате: 'Доход/Расход Категория Сумма'"
    )
    await send_user_message(update, help_message)


async def process_transaction_text(
    text: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> int:
    transaction = speech_service.parse_transcription(text)
    logger.info(f"Transaction: {transaction}")

    if not transaction["amount"]:
        await send_user_message(update, "❌ Не удалось определить сумму.")
        return ConversationHandler.END

    context.user_data["transaction"] = transaction
    context.user_data["type"] = "text"

    if not transaction["category"]:
        keyboard = []
        categories = (
            category_service.get_categories("income")
            if transaction["type"] == "Доход"
            else category_service.get_categories("expense")
        )
        for category in categories:
            keyboard.append([
                InlineKeyboardButton(category, callback_data=f"category_{category}")
            ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_user_message(
            update,
            f"Вы сказали: {text}\n\n"
            f"Тип: {transaction['type']}\n"
            f"Сумма: {transaction['amount']} руб.\n\n"
            "Выберите категорию:",
            reply_markup=reply_markup,
        )
        return WAITING_CATEGORY

    return await confirm_transaction(update, context)


@require_auth
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle voice messages."""
    try:
        # Get voice file
        voice = await update.message.voice.get_file()

        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_file:
            temp_filename = temp_file.name

        # Download voice file
        await voice.download_to_drive(temp_filename)

        # Transcribe voice to text
        transcribed_text = await speech_service.transcribe_voice(temp_filename)

        # Clean up temporary file
        os.unlink(temp_filename)

        if not transcribed_text:
            await send_user_message(
                update,
                "❌ Не удалось распознать голосовое сообщение. Попробуйте еще раз."
            )
            return ConversationHandler.END
        logger.info(f"Transcribed text: {transcribed_text}")
        context.user_data["type"] = "voice"
        # Используем общий обработчик
        return await process_transaction_text(transcribed_text, update, context)

    except Exception as e:
        logger.exception(e)
        await send_user_message(
            update,
            "❌ Произошла ошибка при обработке голосового сообщения."
        )
        return ConversationHandler.END


async def handle_category_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle category selection."""
    # Check authorization for callback queries
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.callback_query.answer(
            "❌ У вас нет доступа к этому боту.", show_alert=True
        )
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()

    # Get selected category
    category = query.data.replace("category_", "")
    context.user_data["transaction"]["category"] = category

    return await confirm_transaction(update, context)


async def confirm_transaction(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Ask for transaction confirmation."""
    # Check authorization for callback queries
    if update.callback_query:
        user_id = update.effective_user.id
        if not is_user_allowed(user_id):
            await update.callback_query.answer(
                "❌ У вас нет доступа к этому боту.", show_alert=True
            )
            return ConversationHandler.END

    transaction = context.user_data["transaction"]

    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data="confirm_yes"),
            InlineKeyboardButton("❌ Нет", callback_data="confirm_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = (
        f"Подтвердите транзакцию:\n\n"
        f"Тип: {transaction['type']}\n"
        f"Категория: {transaction['category']}\n"
        f"Сумма: {transaction['amount']} руб.\n"
        f"Комментарий: {transaction['comment']}"
    )

    await send_or_edit_message(
        update,
        message, reply_markup=reply_markup
    )

    return WAITING_CONFIRMATION


async def handle_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle transaction confirmation."""
    # Check authorization for callback queries
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.callback_query.answer(
            "❌ У вас нет доступа к этому боту.", show_alert=True
        )
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()

    transaction = context.user_data["transaction"]
    base_message = (
        f"Транзакция:\n\n"
        f"Тип: {transaction['type']}\n"
        f"Категория: {transaction['category']}\n"
        f"Сумма: {transaction['amount']} руб.\n"
        f"Комментарий: {transaction['comment']}\n\n"
    )

    if query.data == "confirm_yes":
        try:
            # Save transaction to Google Sheets
            spreadsheet_id = get_spreadsheet_id_for_user(user_id)
            sheets_service.add_transaction(
                spreadsheet_id=spreadsheet_id,
                transaction_type=transaction["type"],
                category=transaction["category"],
                amount=transaction["amount"],
                source=context.user_data["type"],
                comment=transaction["comment"],
            )

            await safe_edit_text(
                query.message,
                base_message + "✅ Статус: Транзакция успешно сохранена!",
                reply_markup=None,
            )

        except Exception as e:
            logger.exception(e)
            await safe_edit_text(
                query.message,
                base_message + "❌ Статус: Произошла ошибка при сохранении транзакции.",
                reply_markup=None,
            )

    else:
        await safe_edit_text(
            query.message,
            base_message + "❌ Статус: Транзакция отменена.", reply_markup=None
        )

    # Clear user data
    context.user_data.clear()
    return ConversationHandler.END


@require_auth
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send statistics when the command /stats is issued."""
    try:
        user_id = update.effective_user.id
        spreadsheet_id = get_spreadsheet_id_for_user(user_id)
        stats = sheets_service.get_monthly_statistics(spreadsheet_id)

        message = (
            f"📊 Статистика за текущий месяц:\n\n"
            f"Доходы: {stats['total_income']:.2f} руб.\n"
            f"Расходы: {stats['total_expense']:.2f} руб.\n"
            f"Средний расход в день: {stats['avg_daily_expense']:.2f} руб.\n\n"
            "Топ расходы:\n"
        )

        for category, amount in stats["top_expenses"]:
            message += f"• {category}: {amount:.2f} руб.\n"

        await send_user_message(update, message)

    except Exception as e:
        logger.exception(e)
        await send_user_message(update, "❌ Произошла ошибка при получении статистики.")


@require_auth
async def categories_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show categories when the command /categories is issued."""
    # TODO

    await send_user_message(update, "Категории...")


@require_auth
async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete last transaction when the command /delete is issued."""
    # TODO: Implement delete
    await send_user_message(update, "🗑 Удаление последней записи...")


@require_auth
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photos with QR codes."""
    # TODO: Implement QR code handling
    await send_user_message(update, "📷 Обрабатываю фото с QR-кодом...")


@require_auth
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages."""
    text_msg = update.message.text
    return await process_transaction_text(text_msg, update, context)



@require_auth
async def select_table_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    sheet_choices = get_sheet_choices()
    user = get_user_entry(user_id)
    current = user["selected_sheet"] if user else None
    keyboard = []
    for name in sheet_choices:
        text = f"{'✅ ' if name == current else ''}{name}"
        keyboard.append([
            InlineKeyboardButton(text, callback_data=f"select_table_{name}")
        ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_user_message(
        update,
        "В какую таблицу будем записывать транзакции?",
        reply_markup=reply_markup
    )

async def select_table_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    sheet_choices = get_sheet_choices()
    users = load_allowed_users()
    user = None
    for u in users:
        if u["user_id"] == user_id:
            user = u
            break
    if not user:
        await query.answer("Нет доступа", show_alert=True)
        return
    # Получаем выбранное имя таблицы
    sheet_name = query.data.replace("select_table_", "")
    if sheet_name not in sheet_choices:
        await query.answer("Ошибка выбора", show_alert=True)
        return
    user["selected_sheet"] = sheet_name
    save_allowed_users(users)
    await query.answer()
    await safe_edit_text(
        query.message,
        f"Готово. Все новые транзакции будут записываться в таблицу: {sheet_name}",
    )


def build_application() -> Application:
    """Create and configure the Telegram application."""
    request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=10.0,
    )
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).request(request).build()

    voice_and_txt_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.VOICE, handle_voice),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
        ],
        states={
            WAITING_CATEGORY: [
                CallbackQueryHandler(handle_category_selection, pattern="^category_")
            ],
            WAITING_CONFIRMATION: [
                CallbackQueryHandler(handle_confirmation, pattern="^confirm_")
            ],
        },
        fallbacks=[],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(voice_and_txt_handler)
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CommandHandler("select_table", select_table_command))
    application.add_handler(CallbackQueryHandler(select_table_callback, pattern="^select_table_"))
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    """Start the bot."""
    warnings.filterwarnings(
        "ignore",
        message=r"If 'per_message=False'.*",
        category=PTBUserWarning,
    )
    force_ipv4_for_telegram()

    users = load_allowed_users()
    sheet_choices = get_sheet_choices()

    for user in users:
        user["selected_sheet"] = next(iter(sheet_choices.keys()))

    save_allowed_users(users)
    for spreadsheet_id in sheet_choices.values():
        sheets_service.ensure_summary_sheet(spreadsheet_id)

    application = build_application()
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        bootstrap_retries=-1,
    )


if __name__ == "__main__":
    main()
