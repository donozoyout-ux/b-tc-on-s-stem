import requests
from config import settings
from utils.logger import logger


class TelegramNotifier:
    """
    Telegram Bot API üzerinden HTML formatında anlık işlem ve durum bildirimleri gönderen modül.
    """

    @staticmethod
    def send_message(message: str) -> bool:
        """
        Telegram kanalına/sohbetine HTML formatında mesaj gönderir.
        Token veya Chat ID ayarlanmamışsa log uyarısı verip işlemi atlar.
        """
        token = settings.TELEGRAM_BOT_TOKEN
        chat_id = settings.TELEGRAM_CHAT_ID

        if not token or not chat_id:
            logger.warning("Telegram Bot Token veya Chat ID tanımlanmamış. Bildirim atlandı.")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Telegram bildirimi başarıyla gönderildi.")
                return True
            else:
                logger.error(f"Telegram bildirimi başarısız! HTTP Status: {response.status_code}, Yanıt: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Telegram bildirim hatası: {str(e)}")
            return False
