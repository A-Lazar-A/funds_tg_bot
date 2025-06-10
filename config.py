import os
from dotenv import load_dotenv

# Force reload environment variables
load_dotenv(override=True)

# Telegram Bot settings
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Google Sheets settings
GOOGLE_SHEETS_CREDENTIALS_FILE = os.getenv('GOOGLE_SHEETS_CREDENTIALS_FILE')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

# SaluteSpeech settings
SALUTE_SPEECH_AUTH_KEY = os.getenv("SALUTE_SPEECH_AUTH_KEY")
SALUTE_SPEECH_API_URL = os.getenv('SALUTE_SPEECH_API_URL', 'https://smartspeech.sber.ru/rest/v1')
SALUTE_SPEECH_API_AUTH_URL = os.getenv('SALUTE_SPEECH_API_AUTH_URL', 'https://ngw.devices.sberbank.ru:9443/api/v2/oauth')

# Google Sheets structure
SHEET_HEADERS = ['Дата', 'Тип', 'Категория', 'Сумма', 'Источник', 'Комментарий'] 