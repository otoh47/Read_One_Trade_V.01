import os
import logging
import requests
import streamlit as st

logger = logging.getLogger(__name__)

def send_telegram_message(message):
    """Kirim pesan ke Telegram."""
    try:
        token = st.secrets["telegram_token"]
        chat_id = st.secrets["telegram_chat_id"]
        if not token or not chat_id:
            logger.error("Telegram token atau chat_id belum diset di secrets.toml")
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
        token = st.secrets["telegram_token"]
        chat_id = st.secrets["telegram_chat_id"]
        if not token or not chat_id:
            logger.error("Telegram token atau chat_id belum diset di secrets.toml")
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

def get_current_config():
    """Ambil konfigurasi dari st.secrets"""
    return {
        "exchange": st.secrets["exchange"],
        "api_key": st.secrets["api_key"],
        "api_secret": st.secrets["api_secret"],
        "telegram_token": st.secrets["telegram_token"],
        "telegram_chat_id": st.secrets["telegram_chat_id"]
    }
