import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def send_telegram_message(message):
    """Kirim pesan ke Telegram."""
    try:
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            logger.error("Telegram token atau chat_id belum diset di .env")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        logger.info("✅ Pesan Telegram terkirim.")
        return True

    except Exception as e:
        logger.error(f"❌ Gagal mengirim pesan Telegram: {e}")
        return False

def send_telegram_photo(photo_path, caption="📸 Screenshot UI"):
    """Kirim foto ke Telegram."""
    try:
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            logger.error("Telegram token atau chat_id belum diset di .env")
            return False

        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        with open(photo_path, 'rb') as photo:
            files = {"photo": photo}
            data = {"chat_id": chat_id, "caption": caption}
            response = requests.post(url, files=files, data=data, timeout=10)
            response.raise_for_status()
        logger.info("✅ Foto UI terkirim ke Telegram.")
        return True

    except Exception as e:
        logger.error(f"❌ Gagal mengirim foto ke Telegram: {e}")
        return False

def save_config_to_env(exchange, api_key, api_secret, telegram_token, telegram_chat_id):
    """Simpan pengaturan ke file .env"""
    try:
        lines = [
            f"EXCHANGE={exchange}",
            f"API_KEY={api_key}",
            f"API_SECRET={api_secret}",
            f"TELEGRAM_TOKEN={telegram_token}",
            f"TELEGRAM_CHAT_ID={telegram_chat_id}"
        ]
        with open(".env", "w") as f:
            f.write("\n".join(lines))
        load_dotenv(override=True)
        logger.info("✅ Konfigurasi berhasil disimpan ke .env")
        return True
    except Exception as e:
        logger.error(f"❌ Gagal menyimpan konfigurasi: {e}")
        return False

def get_current_config():
    """Ambil konfigurasi saat ini dari .env"""
    return {
        "exchange": os.getenv("EXCHANGE", ""),
        "api_key": os.getenv("API_KEY", ""),
        "api_secret": os.getenv("API_SECRET", ""),
        "telegram_token": os.getenv("TELEGRAM_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", "")
    }
