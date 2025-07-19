import logging
import aiohttp
import time
import ssl
import uuid
import re
from config import (
    SALUTE_SPEECH_API_AUTH_URL,
    SALUTE_SPEECH_AUTH_KEY,
    SALUTE_SPEECH_API_URL,
)
from services.category_service import CategoryService

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class SpeechService:
    def __init__(self, category_service: CategoryService):

        self.auth_key = SALUTE_SPEECH_AUTH_KEY
        self.api_url = SALUTE_SPEECH_API_URL
        self.api_auth_url = SALUTE_SPEECH_API_AUTH_URL
        self._access_token = None
        self._token_expires_at = 0
        self.category_service = category_service

        # Create SSL context that doesn't verify certificates
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    async def _get_access_token(self) -> str:
        """Get access token for SaluteSpeech API."""
        current_time = int(time.time() * 1000)

        # If token exists and not expired (with 30 seconds buffer), return it
        logger.info(f"Current time {current_time}, expires {self._token_expires_at}")
        if self._access_token and current_time < self._token_expires_at - 30 * 1000:
            return self._access_token

        # Get new token
        logger.info("POST Request to access token")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_auth_url}",
                headers={
                    "Authorization": f"Basic {self.auth_key}",
                    "RqUID": str(uuid.uuid4()),  # Уникальный идентификатор запроса
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={"scope": "SALUTE_SPEECH_PERS"},  # Версия API для физических лиц
                ssl=self.ssl_context,
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"Failed to get access token: {error_text}")
                    raise Exception("Failed to get access token")

                data = await response.json()
                self._access_token = data["access_token"]
                self._token_expires_at = data["expires_at"]
                return self._access_token

    async def transcribe_voice(self, voice_file_path: str) -> str:
        """Transcribe voice message to text using SaluteSpeech API."""
        try:
            # Get access token
            logger.info("Get access token")
            access_token = await self._get_access_token()

            # Read the audio file
            with open(voice_file_path, "rb") as audio_file:
                audio_data = audio_file.read()

            # Prepare the request
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "audio/ogg;codecs=opus",
            }

            params = {"sample_rate": 48000}

            # Send the request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/speech:recognize",
                    headers=headers,
                    data=audio_data,
                    ssl=self.ssl_context,
                    params=params,
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("result", "")[0]
                    else:
                        error_text = await response.text()
                        logger.error(f"Error from SaluteSpeech: {error_text}")
                        return ""

        except Exception as e:
            logger.exception(e)
            return ""

    def parse_transcription(self, text: str) -> dict:
        """Parse transcribed text to extract transaction details."""
        # Convert to lowercase for easier matching
        text = text.lower().rstrip(".")

        # Initialize result
        result = {"type": None, "category": None, "amount": None, "comment": text}

        # Determine transaction type using type synonyms
        transaction_type = self.category_service.detect_transaction_type(text)
        if transaction_type:
            result["type"] = "Доход" if transaction_type == "income" else "Расход"

            # Extract amount (looking for numbers)

            amount_match = re.search(r"\d+(?: \d{3})*(?:[.,]\d{2})?", text)
            if amount_match:
                result["amount"] = float(
                    amount_match.group().replace(",", ".").replace(" ", "")
                )

            # Try to detect category
            category = self.category_service.detect_category(transaction_type, text)
            if category:
                result["category"] = category

        return result
