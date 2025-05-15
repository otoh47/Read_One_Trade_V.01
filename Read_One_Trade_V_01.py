# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                                IMPORT & SETUP                                  ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
import streamlit as st
import pandas as pd
import os
import plotly.graph_objs as go
import logging
import time
import threading
import requests
import base64
from io import BytesIO
from PIL import Image, ImageGrab
from datetime import datetime, timedelta
from modules.indodax_api import get_indodax_summary, get_trade_volume, load_indodax_pairs, get_candlestick_data, fetch_all_tickers
from modules.indicators import apply_indicators
from modules.telegram_bot import send_telegram_message, send_telegram_photo, save_config_to_env
from modules.signal_engine import scan_signals
from utils.helpers import get_top_movers

# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                            KONFIGURASI & GET CONFIG                            ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(layout="wide")

def get_current_config():
    return {
        "exchange": st.secrets["exchange"],
        "api_key": st.secrets["api_key"],
        "api_secret": st.secrets["api_secret"],
        "telegram_token": st.secrets["telegram_token"],
        "telegram_chat_id": st.secrets["telegram_chat_id"]
    }

config = get_current_config()
exchange = config["exchange"]
api_key = config["api_key"]
api_secret = config["api_secret"]
telegram_token = config["telegram_token"]
telegram_chat_id = config["telegram_chat_id"]

# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                             KONFIGURASI & LOGO UI                              ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
logo_path = "logo.png"

if os.path.exists(logo_path):
    try:
        logo = Image.open(logo_path)
        if logo.mode not in ("RGB", "RGBA"):
            logo = logo.convert("RGB")
    except Exception:
        st.warning("Gagal memuat logo dari file. Menggunakan logo default.")
        logo = Image.new("RGB", (100, 100), color="gray")
else:
    st.warning("File logo tidak ditemukan. Menggunakan logo default.")
    logo = Image.new("RGB", (100, 100), color="gray")

st.sidebar.image(logo, width=120)

buffered = BytesIO()
logo.save(buffered, format="PNG")
base64_logo = base64.b64encode(buffered.getvalue()).decode()

st.markdown(
    f"""
    <div style="display: flex; align-items: center;">
        <img src="data:image/png;base64,{base64_logo}" width="30" style="margin-right:10px;">
        <h1 style="display:inline;">Read ONE Trade Dashboard</h1>
    </div>
    """,
    unsafe_allow_html=True
)

# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                          FUNGSI FORMAT HARGA & VARIABEL                        ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
def format_price(price, pair):
    pair = pair.lower()
    if any(currency in pair for currency in ["usdt", "usdc", "usd"]):
        return f"{price:,.8f}"
    elif "idr" in pair:
        if price < 1:
            return f"{price:,.6f}"
        else:
            return f"{price:,.0f}"
    else:
        return f"{price:,.2f}"

LAST_SIGNAL = None
SENT_SIGNALS = {}
last_screenshot_time = None
screenshot_interval = 3600

# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                         SIDEBAR - PAIR & PENGATURAN LAIN                       ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
pairs = load_indodax_pairs()
if not pairs:
    st.error("Gagal mengambil daftar pair dari Indodax API")
    st.stop()
pair = st.sidebar.selectbox("Pilih Pair", pairs)

with st.sidebar.expander("⚙️ Pengaturan API & Telegram", expanded=False):
    st.text_input("Exchange", value="(tersimpan)", type="password")
    st.text_input("API Key", value="(tersimpan)", type="password")
    st.text_input("API Secret", value="(tersimpan)", type="password")
    st.text_input("Telegram Token", value="(tersimpan)", type="password")
    st.text_input("Telegram Chat ID", value="(tersimpan)", type="password")

with st.sidebar.expander("⏱️ Pengaturan Sinyal", expanded=False):
    signal_interval = st.selectbox("Interval Sinyal", ["5min", "30min", "1H", "4H", "1D"], index=2)

    if st.button("🔄 Reset Sinyal ke Default"):
        SENT_SIGNALS.clear()
        st.success("✅ Semua sinyal berhasil di-reset.")

    with st.sidebar.expander("🖼️ Pengaturan Screenshot", expanded=False):
        screenshot_interval_map = {
            "15 Menit": 900, "30 Menit": 1800, "1 Jam": 3600,
            "2 Jam": 7200, "4 Jam": 14400, "Nonaktif": 0
        }
        screenshot_interval_label = st.selectbox(
            "Interval Screenshot ke Telegram",
            options=list(screenshot_interval_map.keys()),
            index=2,
            key="screenshot_interval_label_select"
        )
        screenshot_interval = screenshot_interval_map[screenshot_interval_label]

# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                          FUNGSI & THREAD SCREENSHOT                            ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
def send_periodic_screenshot():
    global last_screenshot_time
    while True:
        now = datetime.now()
        if screenshot_interval > 0 and ((last_screenshot_time is None) or ((now - last_screenshot_time).total_seconds() >= screenshot_interval)):
            try:
                screenshot_path = "screenshot_ui.png"
                image = ImageGrab.grab()
                image.save(screenshot_path)
                send_telegram_photo(screenshot_path)
                last_screenshot_time = now
            except Exception as e:
                logger.error(f"Gagal kirim screenshot: {e}")
        time.sleep(60)

# Jalankan thread screenshot
threading.Thread(target=send_periodic_screenshot, daemon=True).start()

# Notifikasi awal saat startup
if "startup_notified" not in st.session_state:
    if telegram_token and telegram_chat_id:
        send_telegram_message("✅ Aplikasi aktif dan UI aktif Lur!")
        try:
            ss = ImageGrab.grab()
            ss.save("startup_ui.png")
            send_telegram_photo("startup_ui.png")
        except Exception as e:
            logger.warning(f"Gagal kirim screenshot awal: {e}")
        st.session_state.startup_notified = True

# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║Jalankan thread screenshot berkala                                              ║ 
# ╚════════════════════════════════════════════════════════════════════════════════╝
threading.Thread(target=send_periodic_screenshot, daemon=True).start()

# ==================================================================================
# Kirim notifikasi awal saat app start
# ==================================================================================
if "startup_notified" not in st.session_state:
    if telegram_token and chat_id:
        send_telegram_message("✅ Aplikasi aktif dan UI aktif Lur!")
    try:
        ss = ImageGrab.grab()
        ss.save("startup_ui.png")
        send_telegram_photo("startup_ui.png")
    except Exception as e:
        logger.warning(f"Gagal kirim screenshot awal: {e}")
    st.session_state.startup_notified = True

try:
    with st.spinner('Memperbarui data...'):
        candle_df = get_candlestick_data(pair, tf=signal_interval)
        if candle_df.empty:
            st.warning(f"Tidak dapat mengambil data candlestick untuk {pair}")
            st.stop()

        candle_df = apply_indicators(candle_df)
        signals = scan_signals(pair, candle_df)

        tickers = fetch_all_tickers()
        top_gainers, top_losers, top_volume = get_top_movers(tickers)

except Exception as e:
    logger.error(f"Error: {str(e)}", exc_info=True)
    st.error(f"Terjadi error: {str(e)}")
    st.stop()

# ==================================================================================
# Tampilkan informasi pair
# ==================================================================================
try:
    summary = get_indodax_summary(pair)
    if summary:
        with st.expander("📊 Informasi Pair"):
            cols = st.columns(4)
            cols[0].metric("Harga Sekarang", format_price(summary['last'], pair),
                           delta=f"{((summary['last'] - summary['low']) / summary['low'] * 100):.2f}%")
            cols[1].metric("24h Tertinggi", format_price(summary['high'], pair),
                          delta=f"{((summary['high'] - summary['last']) / summary['last'] * 100):.2f}%")
            cols[2].metric("24h Terendah", format_price(summary['low'], pair),
                          delta=f"{((summary['low'] - summary['last']) / summary['last'] * 100):.2f}%")
            cols[3].metric("Kenaikan dari Terendah", 
                          f"{((summary['last'] - summary['low']) / summary['low'] * 100):.2f}%",
                          delta=f"{((summary['last'] - summary['low']) / summary['low'] * 100):.2f}%")
    else:
        st.warning("Tidak dapat mengambil informasi pair.")
except Exception as e:
    st.error(f"Gagal mengambil data summary: {e}")
    logger.error(f"Error fetching summary: {e}", exc_info=True)

# ==================================================================================
# Tampilkan sinyal dalam expander
# ==================================================================================
with st.expander("📈 Sinyal MACD & Volume Spike", expanded=True):
    if not signals.empty:
        st.dataframe(signals.tail(5))

        last_signal = signals.iloc[-1]
        current_signal = last_signal['macd_signal_label'] or last_signal['volume_spike_label']

        if current_signal and SENT_SIGNALS.get(pair) != current_signal:
            msg = f"📢 Sinyal Detected pada {pair.upper()} ({signal_interval})\n"
            msg += f"- MACD: {last_signal['macd_signal_label']}\n" if last_signal['macd_signal_label'] else ""
            msg += f"- Volume Spike: {last_signal['volume_spike_label']}\n" if last_signal['volume_spike_label'] else ""
            msg += f"- Harga: {format_price(summary['last'], pair)}"

            if send_telegram_message(msg):
                st.success("Sinyal terkirim ke Telegram!")
                SENT_SIGNALS[pair] = {'signal': current_signal, 'time': datetime.now()}
                with open("signal_logs.txt", "a") as f:
                    f.write(f"{datetime.now()} - {pair} - {msg}\n")
    else:
        st.write("Tidak ada sinyal terdeteksi.")
        
# ==================================================================================
# Tampilkan sinyal Golabal Ticker Pair dalam expander
# ==================================================================================
# ======== Fungsi Format Harga (Hilangkan "Rp" jika bukan IDR) ========
def format_price(price_value, pair_name):
    normalized_pair = str(pair_name).upper().replace("/", "").replace("_", "")
    is_idr = "IDR" in normalized_pair

    if is_idr:
        if price_value >= 1:
            return f"Rp {price_value:,.0f}"
        else:
            return f"Rp {price_value:,.8f}"
    else:
        if abs(price_value) < 0.00001:
            return f"{price_value:,.8f}"
        elif abs(price_value) < 1:
            return f"{price_value:,.6f}"
        elif abs(price_value) >= 1000:
            return f"{price_value:,.2f}"
        else:
            return f"{price_value:,.2f}"

# ======== Ambil data market dari Indodax (Real-time) ========
@st.cache_data(ttl=30)
def fetch_all_tickers():
    url = "https://indodax.com/api/tickers"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json().get('tickers', {})
        result = {}
        for pair, item in data.items():
            result[pair.upper()] = {
                'last': float(item.get('last', 0)),
                'buy': float(item.get('buy', 0)),
                'sell': float(item.get('sell', 0)),
            }
        return result
    except Exception as e:
        st.error(f"❌ Gagal mengambil data dari Indodax: {e}")
        return {}

# ======== Sinyal Berdasarkan Rasio Volume ========
def generate_signal(buy, sell):
    if sell == 0:
        return "STRONG BUY"
    diff_percent = abs(buy - sell) / max(buy, sell) * 100
    if buy > sell:
        if diff_percent > 5:
            return "STRONG BUY"
        elif diff_percent > 3:
            return "BUY"
    elif sell > buy:
        if diff_percent > 5:
            return "STRONG SELL"
        elif diff_percent > 3:
            return "SELL"
    return "HOLD"

# ======== Warna untuk Sinyal ========
def color_signal(val):
    if "STRONG BUY" in val:
        return "color: green; font-weight: bold"
    elif "BUY" in val:
        return "color: lightgreen"
    elif "STRONG SELL" in val:
        return "color: red; font-weight: bold"
    elif "SELL" in val:
        return "color: orange"
    else:
        return "color: blue"

# ======== Logika Open Posisi Berdasarkan Sinyal ========
def open_position_logic(signal):
    if signal == 'STRONG BUY':
        return 'Open Posisi BUY 🟢'
    elif signal == 'BUY':
        return 'Pertimbangkan BUY 🟩'
    elif signal == 'STRONG SELL':
        return 'Open Posisi SELL 🔴'
    elif signal == 'SELL':
        return 'Pertimbangkan SELL 🟥'
    else:
        return 'Tidak ada aksi ⚪'

# ======== UI Streamlit ========
with st.expander("📡 Deteksi Global: Buy/Sell Dominan & Lonjakan Harga", expanded=True):
    all_tickers = fetch_all_tickers()

    if all_tickers:
        df = pd.DataFrame.from_dict(all_tickers, orient='index')
        df.index.name = 'Pair'
        df = df[['last', 'buy', 'sell']].copy()

        # Hitung volume dan sinyal
        df['Volume Buy'] = df['buy']
        df['Volume Sell'] = df['sell']
        df['Rasio'] = df.apply(lambda x: "Demand" if x['buy'] > x['sell'] else "Supply", axis=1)
        df['Sinyal'] = df.apply(lambda x: generate_signal(x['buy'], x['sell']), axis=1)
        df['Open Posisi'] = df['Sinyal'].apply(open_position_logic)
        df['Harga'] = [format_price(x, pair) for x, pair in zip(df['last'], df.index)]

        # Urutkan berdasarkan kekuatan sinyal
        df['Sinyal_Val'] = df['Sinyal'].map({
            'STRONG BUY': 4, 'BUY': 3, 'HOLD': 2, 'SELL': 1, 'STRONG SELL': 0
        })
        df = df.sort_values(by='Sinyal_Val', ascending=False)

        # Tampilkan kolom utama
        styled_df = df[['Harga', 'Volume Buy', 'Volume Sell', 'Rasio', 'Sinyal', 'Open Posisi']].style\
            .format({
                'Volume Buy': '{:,.0f}',
                'Volume Sell': '{:,.0f}',
            })\
            .applymap(color_signal, subset=['Sinyal'])

        st.dataframe(styled_df, use_container_width=True)
    else:
        st.warning("❗ Tidak ada data ticker tersedia dari Indodax.")      
        
# ==================================================================================
# Top Movers dalam expander
# ==================================================================================
with st.expander("🔥 Top Movers", expanded=True):
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.write("### 🚀Gainers")
        if top_gainers.empty:
            st.warning("Tidak ada top gainers untuk ditampilkan.")
        else:
            st.dataframe(top_gainers[['last', 'change']].style.format({
                'last': lambda x: format_price(x, 'idr'),
                'change': '{:.2f}%'
            }))

    with col2:
        st.write("### 🔻Losers")
        if top_losers.empty:
            st.warning("Tidak ada top losers untuk ditampilkan.")
        else:
            st.dataframe(top_losers[['last', 'change']].style.format({
                'last': lambda x: format_price(x, 'idr'),
                'change': '{:.2f}%'
            }))

    with col3:
        st.write("### 💰 Top Volume")
        if top_volume.empty:
            st.warning("Tidak ada top volume movers untuk ditampilkan.")
        else:
            st.dataframe(top_volume[['vol_idr']].style.format({
                'vol_idr': '{:,.0f} IDR'
            }))

# ==================================================================================
# Candlestick chart dalam expander
# ==================================================================================
with st.expander("📈 Candlestick Chart", expanded=True):
    # Dropdown untuk memilih ukuran chart
    chart_size = st.selectbox("Pilih Ukuran Chart", ["Small", "Medium", "Large"], index=1)

    # Menentukan ukuran berdasarkan pilihan dropdown
    if chart_size == "Small":
        chart_height = 250
    elif chart_size == "Medium":
        chart_height = 350
    else:
        chart_height = 450

    # Membuat chart
    if not candle_df.empty:
        fig = go.Figure(data=[go.Candlestick(
            x=candle_df['timestamp'] if 'timestamp' in candle_df else candle_df.index,
            open=candle_df['open'],
            high=candle_df['high'],
            low=candle_df['low'],
            close=candle_df['close'],
            increasing_line_color='green',  # warna naik
            decreasing_line_color='red',  # warna turun
            name='Candlestick'
        )])

        # Menambahkan volume di bawah chart
        fig.add_trace(go.Bar(
            x=candle_df['timestamp'] if 'timestamp' in candle_df else candle_df.index,
            y=candle_df['volume'],
            name='Volume',
            marker=dict(color='rgba(0,0,255,0.3)')
        ))

        # Menambahkan indikator (contoh Moving Average)
        fig.add_trace(go.Scatter(
            x=candle_df['timestamp'] if 'timestamp' in candle_df else candle_df.index,
            y=candle_df['close'].rolling(window=50).mean(),  # Contoh 50-period Moving Average
            mode='lines',
            name='50-period SMA',
            line=dict(color='orange')
        ))

        # Menambahkan indikator Bollinger Bands
        fig.add_trace(go.Scatter(
            x=candle_df['timestamp'] if 'timestamp' in candle_df else candle_df.index,
            y=candle_df['bb_upper'],  # Upper Bollinger Band
            mode='lines',
            name='BB Upper',
            line=dict(color='rgba(173,216,230,0.5)', dash='dot')
        ))

        fig.add_trace(go.Scatter(
            x=candle_df['timestamp'] if 'timestamp' in candle_df else candle_df.index,
            y=candle_df['bb_lower'],  # Lower Bollinger Band
            mode='lines',
            name='BB Lower',
            line=dict(color='rgba(173,216,230,0.5)', dash='dot')
        ))

        # Desain dan Layout Chart
        fig.update_layout(
            title=f"Candlestick: {pair.upper()} ({signal_interval})",
            xaxis_rangeslider_visible=False,  # Menyembunyikan range slider
            template="plotly_dark",  # Menambahkan tema gelap untuk tampilan lebih mirip TradingView
            height=chart_height,  # Mengatur tinggi chart
            xaxis_title="Waktu",  # Label untuk axis X
            yaxis_title="Harga",  # Label untuk axis Y
            showlegend=True,  # Menampilkan legend
            plot_bgcolor='rgba(0,0,0,0)',  # Background transparan
            paper_bgcolor='rgba(0,0,0,0)',  # Background transparent di luar chart
        )

        st.plotly_chart(fig, use_container_width=True)

