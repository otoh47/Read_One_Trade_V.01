import os
import logging
import requests
# import streamlit as st # Tidak diperlukan lagi di sini jika token/chat_id dilewatkan

logger = logging.getLogger(__name__)

# === send_telegram_message ===
# Fungsi diubah untuk menerima token dan chat_id sebagai parameter
def send_telegram_message(message, token, chat_id):
    """Kirim pesan ke Telegram menggunakan token dan chat_id yang diberikan."""
    if not token or not chat_id:
        # logger.error("Telegram token atau chat_id belum diset atau diteruskan.") # Log ini mungkin terlalu sering
        return False # Langsung keluar jika token/chat_id tidak ada

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML" # Menggunakan HTML agar format pesan lebih kaya (bold, italic, dll.)
        }
        # Gunakan json=payload untuk header Content-Type: application/json
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status() # Angkat HTTPError untuk status kode buruk (4xx atau 5xx)
        # logger.info("✅ Pesan Telegram terkirim.") # Log ini mungkin terlalu sering jika banyak sinyal
        return response.json().get('ok', False) # Kembalikan status berhasil/gagal

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Gagal mengirim pesan Telegram: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Terjadi kesalahan lain saat mengirim pesan Telegram: {e}")
        return False


# === send_telegram_photo ===
# Fungsi diubah untuk menerima token dan chat_id sebagai parameter
def send_telegram_photo(photo_path, token, chat_id, caption="📸 Screenshot UI"):
    """Kirim foto ke Telegram menggunakan token dan chat_id yang diberikan."""
    if not os.path.exists(photo_path):
        logger.error(f"❌ File foto tidak ditemukan: {photo_path}")
        return False

    if not token or not chat_id:
        # logger.error("Telegram token atau chat_id belum diset atau diteruskan.")
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        with open(photo_path, 'rb') as photo:
            files = {"photo": photo}
            data = {"chat_id": chat_id, "caption": caption}
            response = requests.post(url, files=files, data=data, timeout=20) # Timeout lebih lama untuk foto
            response.raise_for_status()
        # logger.info(f"✅ Foto '{photo_path}' terkirim ke Telegram.")
        return True

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Gagal mengirim foto Telegram: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Terjadi kesalahan lain saat mengirim foto Telegram: {e}")
        return False

# === get_current_config ===
# Fungsi ini mungkin tidak lagi dibutuhkan jika konfigurasi dibaca di skrip utama
# Namun, saya biarkan saja jika ada bagian lain yang menggunakannya.
# Perlu diingat, jika fungsi ini tetap ada dan dipanggil, dia akan membaca dari st.secrets
# seperti sebelumnya.
def get_current_config():
    """Ambil konfigurasi dari st.secrets"""
    # Pastikan Streamlit diimpor jika fungsi ini digunakan
    try:
         import streamlit as st
         return {
             "exchange": st.secrets["exchange"],
             "api_key": st.secrets["api_key"],
             "api_secret": st.secrets["api_secret"],
             "telegram_token": st.secrets["telegram_token"],
             "telegram_chat_id": st.secrets["telegram_chat_id"]
         }
    except ImportError:
         logger.error("Streamlit tidak diimpor, get_current_config tidak bisa berjalan.")
         return {} # Kembalikan dict kosong jika Streamlit tidak ada
    except Exception as e:
         logger.error(f"Gagal memuat konfigurasi dari st.secrets dalam get_current_config: {e}")
         return {}
