import logging
import os
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from config import TELEGRAM_BOT_TOKEN, GOOGLE_SHEETS_CREDENTIALS_FILE
from services.speech_service import SpeechService
from services.sheets_service import GoogleSheetsService
from services.category_service import CategoryService

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for conversation
(
    WAITING_CATEGORY,
    WAITING_CONFIRMATION,
) = range(2)
print(GOOGLE_SHEETS_CREDENTIALS_FILE)
# Initialize services
speech_service = SpeechService()
sheets_service = GoogleSheetsService()
category_service = CategoryService()

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
        "/help - Показать это сообщение"
    )
    await update.message.reply_text(welcome_message)

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
    await update.message.reply_text(help_message)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle voice messages."""
    try:
        # Get voice file
        voice = await update.message.voice.get_file()
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
            temp_filename = temp_file.name
            
        # Download voice file
        await voice.download_to_drive(temp_filename)
        
        # Transcribe voice to text
        transcribed_text = await speech_service.transcribe_voice(temp_filename)
        
        # Clean up temporary file
        os.unlink(temp_filename)
        
        if not transcribed_text:
            await update.message.reply_text("❌ Не удалось распознать голосовое сообщение. Попробуйте еще раз.")
            return ConversationHandler.END
        logger.info(f"Transcribed text: {transcribed_text}")
        # Parse transcription
        transaction = speech_service.parse_transcription(transcribed_text)
        logger.info(f"Transaction: {transaction}")

        if not transaction['type'] or not transaction['amount']:
            await update.message.reply_text(
                "❌ Не удалось определить тип операции или сумму. "
                "Пожалуйста, говорите четко, например: 'Расход на продукты 500 рублей'"
            )
            return ConversationHandler.END
            
        # Store transaction data in context
        context.user_data['transaction'] = transaction
        
        # If category is not specified, ask for it
        if not transaction['category']:
            keyboard = []
            categories = category_service.get_categories('income') if transaction['type'] == 'Доход' else category_service.get_categories('expense')
            
            # Create keyboard with categories
            for category in categories:
                keyboard.append([InlineKeyboardButton(category, callback_data=f"category_{category}")])
                
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"Вы сказали: {transcribed_text}\n\n"
                f"Тип: {transaction['type']}\n"
                f"Сумма: {transaction['amount']} руб.\n\n"
                "Выберите категорию:",
                reply_markup=reply_markup
            )
            return WAITING_CATEGORY
        # If category is specified, ask for confirmation
        return await confirm_transaction(update, context)
        
    except Exception as e:
        logger.exception(e)
        await update.message.reply_text("❌ Произошла ошибка при обработке голосового сообщения.")
        return ConversationHandler.END

async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection."""
    query = update.callback_query
    await query.answer()
    
    # Get selected category
    category = query.data.replace("category_", "")
    context.user_data['transaction']['category'] = category
    
    return await confirm_transaction(update, context)

async def confirm_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for transaction confirmation."""
    transaction = context.user_data['transaction']
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data="confirm_yes"),
            InlineKeyboardButton("❌ Нет", callback_data="confirm_no")
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
    
    if update.callback_query:
        await update.callback_query.message.edit_text(message, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message, reply_markup=reply_markup)
    
    return WAITING_CONFIRMATION

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle transaction confirmation."""
    query = update.callback_query
    await query.answer()
    
    transaction = context.user_data['transaction']
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
            sheets_service.add_transaction(
                transaction_type=transaction['type'],
                category=transaction['category'],
                amount=transaction['amount'],
                source="Голос",
                comment=transaction['comment']
            )
            
            await query.message.edit_text(
                base_message + "✅ Статус: Транзакция успешно сохранена!",
                reply_markup=None
            )
            
        except Exception as e:
            logger.exception(e)
            await query.message.edit_text(
                base_message + "❌ Статус: Произошла ошибка при сохранении транзакции.",
                reply_markup=None
            )
            
    else:
        await query.message.edit_text(
            base_message + "❌ Статус: Транзакция отменена.",
            reply_markup=None
        )
    
    # Clear user data
    context.user_data.clear()
    return ConversationHandler.END

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send statistics when the command /stats is issued."""
    try:
        stats = sheets_service.get_monthly_statistics()
        
        message = (
            f"📊 Статистика за текущий месяц:\n\n"
            f"Доходы: {stats['total_income']:.2f} руб.\n"
            f"Расходы: {stats['total_expense']:.2f} руб.\n"
            f"Средний расход в день: {stats['avg_daily_expense']:.2f} руб.\n\n"
            "Топ расходы:\n"
        )
        
        for category, amount in stats['top_expenses']:
            message += f"• {category}: {amount:.2f} руб.\n"
            
        await update.message.reply_text(message)
        
    except Exception as e:
        logger.exception(e)
        await update.message.reply_text("❌ Произошла ошибка при получении статистики.")

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show categories when the command /categories is issued."""
    # TODO
        
    await update.message.reply_text("Категории...")

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete last transaction when the command /delete is issued."""
    # TODO: Implement delete
    await update.message.reply_text("🗑 Удаление последней записи...")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photos with QR codes."""
    # TODO: Implement QR code handling
    await update.message.reply_text("📷 Обрабатываю фото с QR-кодом...")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages."""
    # TODO: Implement text message handling
    await update.message.reply_text("📝 Обрабатываю текстовое сообщение...")

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Create conversation handler for voice messages
    voice_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.VOICE, handle_voice)],
        states={
            WAITING_CATEGORY: [
                CallbackQueryHandler(handle_category_selection, pattern="^category_")
            ],
            WAITING_CONFIRMATION: [
                CallbackQueryHandler(handle_confirmation, pattern="^confirm_")
            ],
        },
        fallbacks=[]
    )

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(voice_handler)
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 