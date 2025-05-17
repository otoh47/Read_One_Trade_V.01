# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                                IMPORT & SETUP REQUIREMENTS                                  ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
import os
import platform
import streamlit as st
import pandas as pd
import plotly.graph_objs as go
import logging
import time
import threading
import requests
import base64
import schedule
import csv
from io import BytesIO
from PIL import Image, ImageGrab
from datetime import datetime, timedelta
from modules.indodax_api import get_indodax_summary, get_trade_volume, load_indodax_pairs, get_candlestick_data, fetch_all_tickers
from modules.indicators import apply_indicators
from modules.telegram_bot import send_telegram_message, send_telegram_photo
from modules.signal_engine import scan_signals
from utils.helpers import get_top_movers

# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                            KONFIGURASI & GET CONFIG                            ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
# Streamlit config ================================================================================
st.set_page_config(layout="wide")

# Inisialisasi session_state
default_keys = {
    "SENT_SIGNALS": [],
    "TRADE_HISTORY": [],
    "USER_LOGGED_IN": False,
    "CURRENT_PAGE": "Home"
}

for key, default_value in default_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

# Logging setup ===================================================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inisialisasi aman untuk session state============================================================
try:
    if "SENT_SIGNALS" not in st.session_state:
        st.session_state["SENT_SIGNALS"] = {}

    if "startup_notified" not in st.session_state:
        st.session_state["startup_notified"] = False
except Exception as e:
    st.error("Terjadi kesalahan saat inisialisasi session state.")
    logger.error(f"Gagal inisialisasi session state: {e}")
    st.stop()

# KONFIGURASI DARI SECRETS.TOML ===================================================================
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

# SCREENSHOT ===========================================================================
def send_ui_screenshot(filepath="startup_ui.png"):
    if platform.system() in ["Windows", "Darwin"]:
        try:
            ss = ImageGrab.grab()
            ss.save(filepath)
            send_telegram_photo(filepath)
            logger.info("✅ Screenshot UI dikirim ke Telegram.")
        except Exception as e:
            logger.warning(f"❌ Gagal ambil/kirim screenshot: {e}")
    else:
        logger.info("📸 Screenshot dinonaktifkan (platform tidak mendukung).")

def send_periodic_screenshot():
    global last_screenshot_time
    while True:
        now = datetime.now()
        if screenshot_interval > 0 and ((last_screenshot_time is None) or ((now - last_screenshot_time).total_seconds() >= screenshot_interval)):
            send_ui_screenshot("screenshot_ui.png")
            last_screenshot_time = now
        time.sleep(60)

# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                             PENGATURAN LOGO                                    ║
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

# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                         SIDEBAR - PAIR & PENGATURAN LAIN                       ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
pairs = load_indodax_pairs() 
if not pairs:
    st.error("Gagal mengambil daftar pair dari Indodax API")
    st.stop()

pair = st.sidebar.selectbox("🎯 Pilih Pair", pairs)

# ⚙️ Pengaturan API & Telegram
with st.sidebar.expander("⚙️ Pengaturan API & Telegram", expanded=False):
    st.text_input("Exchange", value="(tersimpan)", type="password")
    st.text_input("API Key", value="(tersimpan)", type="password")
    st.text_input("API Secret", value="(tersimpan)", type="password")
    st.text_input("Telegram Token", value="(tersimpan)", type="password")
    st.text_input("Telegram Chat ID", value="(tersimpan)", type="password")

# ⏱️ Pengaturan Sinyal + Reset
with st.sidebar.expander("⏱️ Pengaturan Sinyal", expanded=False):
    signal_interval = st.selectbox("Interval Sinyal", ["5min", "30min", "1H", "4H", "1D"], index=2)

    # Fungsi reset
    def reset_signals():
        keys_to_clear = ["SENT_SIGNALS", "startup_notified"]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        st.success("✅ Semua sinyal berhasil di-reset.")

    # Tombol reset di dalam sidebar
    if st.button("🔄 Reset Sinyal ke Default", key="reset_signals_button"):
        reset_signals()

# 🖼️ Pengaturan Screenshot
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
def send_ui_screenshot(filepath="startup_ui.png"):
    if platform.system() in ["Windows", "Darwin"]:
        try:
            ss = ImageGrab.grab()
            ss.save(filepath)
            send_telegram_photo(filepath)
            logger.info("✅ Screenshot UI dikirim ke Telegram.")
        except Exception as e:
            logger.warning(f"❌ Gagal ambil/kirim screenshot: {e}")
    else:
        logger.info("📸 Screenshot dinonaktifkan (platform tidak mendukung).")

def send_periodic_screenshot():
    global last_screenshot_time
    while True:
        now = datetime.now()
        if screenshot_interval > 0 and ((last_screenshot_time is None) or ((now - last_screenshot_time).total_seconds() >= screenshot_interval)):
            send_ui_screenshot("screenshot_ui.png")
            last_screenshot_time = now
        time.sleep(60)

# Jalankan thread screenshot
threading.Thread(target=send_periodic_screenshot, daemon=True).start()

# Notifikasi awal saat startup
if "startup_notified" not in st.session_state:
    if telegram_token and telegram_chat_id:
        send_telegram_message("✅ Sistem Selalu Aktif Lur!")
        send_ui_screenshot("startup_ui.png")
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

# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                         FUNGSI PLOT TEKNIKAL & SCANNER                         ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
def plot_technical_charts(df, pair):
    """Fungsi untuk membuat plot teknikal"""
    fig = go.Figure()
    
    # Tambahkan candlestick
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name='Candlestick'
    ))
    
    # Tambahkan indikator-indikator
    if 'sma' in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df['sma'],
            name='SMA',
            line=dict(color='orange')
        ))
    
    if 'rsi' in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df['rsi'],
            name='RSI',
            yaxis='y2',
            line=dict(color='purple')
        ))
    
    fig.update_layout(
        title=f'Analisis Teknikal {pair}',
        yaxis_title='Harga',
        yaxis2=dict(title='RSI', overlaying='y', side='right'),
        xaxis_rangeslider_visible=False
    )
    
    st.plotly_chart(fig, use_container_width=True)

def scan_all_pairs(pairs):
    alerted_pairs = []
    for p in pairs:
        try:
            df = get_candlestick_data(p, interval='1h', limit=100)
            if df is not None and not df.empty:
                df = apply_indicators(df)
                latest = df.iloc[-1]
                alerts = []
                if latest['rsi'] > 70:
                    alerts.append(f"📊 RSI Overbought on {p.upper()}")
                elif latest['rsi'] < 30:
                    alerts.append(f"📉 RSI Oversold on {p.upper()}")
                if latest['macd'] > latest['macd_signal'] and latest['macd_hist'] > 0:
                    alerts.append(f"✅ MACD Bullish Crossover on {p.upper()}")
                elif latest['macd'] < latest['macd_signal'] and latest['macd_hist'] < 0:
                    alerts.append(f"⚠️ MACD Bearish Crossover on {p.upper()}")
                if alerts:
                    send_telegram_message("\n".join(alerts))
                    alerted_pairs.append(p)
        except Exception as e:
            logger.warning(f"Error scanning pair {p}: {e}")
    return alerted_pairs

def auto_scan_job():
    hasil = scan_all_pairs(pairs)
    if hasil:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("auto_scan_log.csv", "a", newline='') as f:
            writer = csv.writer(f)
            for pair in hasil:
                writer.writerow([timestamp, pair, "Sinyal Terdeteksi"])
        logger.info(f"Sinyal auto-scan terdeteksi di: {', '.join(hasil)}")
    else:
        logger.info("Auto-scan selesai: tidak ada sinyal.")

# 1. INFORMASI PAIR =========================================================================================
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

# 2. CANDLESTICK CHART ======================================================================
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
            increasing_line_color='green',
            decreasing_line_color='red',
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
            y=candle_df['close'].rolling(window=50).mean(),
            mode='lines',
            name='50-period SMA',
            line=dict(color='orange')
        ))

        # Menambahkan indikator Bollinger Bands
        fig.add_trace(go.Scatter(
            x=candle_df['timestamp'] if 'timestamp' in candle_df else candle_df.index,
            y=candle_df['bb_upper'],
            mode='lines',
            name='BB Upper',
            line=dict(color='rgba(173,216,230,0.5)', dash='dot')
        ))

        fig.add_trace(go.Scatter(
            x=candle_df['timestamp'] if 'timestamp' in candle_df else candle_df.index,
            y=candle_df['bb_lower'],
            mode='lines',
            name='BB Lower',
            line=dict(color='rgba(173,216,230,0.5)', dash='dot')
        ))

        # Desain dan Layout Chart
        fig.update_layout(
            title=f"Candlestick: {pair.upper()} ({signal_interval})",
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            height=chart_height,
            xaxis_title="Waktu",
            yaxis_title="Harga",
            showlegend=True,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
        )

        st.plotly_chart(fig, use_container_width=True)

# 3. VISUALISASI TEKNIKAL & SCANNER===============================================================
st.header("📉 Visualisasi Teknikal & Scanner")
selected_pair = st.selectbox("Pilih Pair untuk Analisis Teknikal", pairs, index=0)
df_chart = get_candlestick_data(selected_pair, tf='1h')
if df_chart is not None and not df_chart.empty:
    df_chart = apply_indicators(df_chart)
    plot_technical_charts(df_chart, selected_pair)
    
# 4. SCAN SEMUA PAIR UNTUK SINYAL TEKNIKAL =======================================================
if st.button("🔍 Scan Semua Pair untuk Sinyal Teknikal"):
    st.info("Sedang memindai semua pair, mohon tunggu...")
    hasil_alert = scan_all_pairs(pairs)
    if hasil_alert:
        st.success(f"🚨 Sinyal terdeteksi pada: {', '.join(hasil_alert)}")
    else:
        st.warning("Tidak ada sinyal teknikal terdeteksi.")

# Auto-scan setiap jam dan log ke CSV
if "auto_scan_started" not in st.session_state:
    schedule.every().hour.at(":00").do(auto_scan_job)
    def run_auto_scan():
        while True:
            schedule.run_pending()
            time.sleep(30)
    threading.Thread(target=run_auto_scan, daemon=True).start()
    st.session_state.auto_scan_started = True
    
# 5. SINYAL MACD & VOLUME SPIKE ====================================================================
with st.expander("📈 Sinyal MACD & Volume Spike", expanded=True):
    if not signals.empty:
        st.dataframe(signals.tail(5))

        last_signal = signals.iloc[-1]
        current_signal = last_signal['macd_signal_label'] or last_signal['volume_spike_label']

        # Inisialisasi sebagai LIST
        if "SENT_SIGNALS" not in st.session_state:
            st.session_state["SENT_SIGNALS"] = []

        sent_signals = st.session_state["SENT_SIGNALS"]

        # Cek apakah sinyal sudah dikirim sebelumnya untuk pair yang sama
        already_sent = any(s['pair'] == pair and s['signal'] == current_signal for s in sent_signals)

        if current_signal and not already_sent:
            msg = f"📢 Sinyal Detected pada {pair.upper()} ({signal_interval})\n"
            msg += f"- MACD: {last_signal['macd_signal_label']}\n" if last_signal['macd_signal_label'] else ""
            msg += f"- Volume Spike: {last_signal['volume_spike_label']}\n" if last_signal['volume_spike_label'] else ""
            msg += f"- Harga: {format_price(summary['last'], pair)}"

            if send_telegram_message(msg):
                st.success("Sinyal terkirim ke Telegram! 🚀")
                sent_signals.append({
                    'pair': pair,
                    'signal': current_signal,
                    'time': datetime.now()
                })
                st.session_state["SENT_SIGNALS"] = sent_signals  # simpan ulang
                with open("signal_logs.txt", "a") as f:
                    f.write(f"{datetime.now()} - {pair} - {msg}\n")
    else:
        st.write("Tidak ada sinyal terdeteksi.")

# 6. PENGATURAN WARNA DETEKSI GLOBAL: BUY/SELL DOMINAN & LONJAKAN HARGA ============================================
SENT_SIGNALS = {}

def generate_signal(buy, sell):
    if buy > sell * 1.2:
        return "STRONG BUY"
    elif buy > sell:
        return "BUY"
    elif buy == sell:
        return "HOLD"
    elif sell > buy * 1.2:
        return "STRONG SELL"
    else:
        return "SELL"

def open_position_logic(signal):
    if signal in ["STRONG BUY", "BUY"]:
        return "Buka LONG"
    elif signal in ["STRONG SELL", "SELL"]:
        return "Buka SHORT"
    else:
        return "-"
        
def color_signal(val):
    if val == "STRONG BUY":
        return "background-color: green; color: white"
    elif val == "BUY":
        return "background-color: lightgreen"
    elif val == "HOLD":
        return "background-color: gray; color: white"
    elif val == "SELL":
        return "background-color: orange"
    elif val == "STRONG SELL":
        return "background-color: red; color: white"
    else:
        return ""
# TABEL DETEKSI GLOBAL: BUY/SELL DOMINAN & LONJAKAN HARGA ============================================
with st.expander("📡 Deteksi Global: Buy/Sell Dominan & Lonjakan Harga", expanded=True):
    all_tickers = fetch_all_tickers()

    all_tickers = fetch_all_tickers()

    if all_tickers:
        df = pd.DataFrame.from_dict(all_tickers, orient='index')
        df.index.name = 'Pair'

        # ✅ VALIDASI sebelum akses kolom + tambahkan jika hilang
        required_cols = ['last', 'buy', 'sell']
        for col in required_cols:
            if col not in df.columns:
                logger.warning(f"⚠️ Kolom '{col}' tidak ditemukan di data ticker. Ditambahkan dengan nilai default 0.")
                df[col] = 0

        # ✅ Final check sebelum lanjut
        missing_final = [col for col in required_cols if col not in df.columns]
        if missing_final:
            st.error(f"❌ Masih ada kolom hilang setelah fallback: {', '.join(missing_final)}")
            st.stop()

        # Aman bro! Gas akses kolom
        df = df[required_cols].copy()

        # ⏩ lanjutkan logika kamu di sini...
        df['Volume Buy'] = df['buy']
        df['Volume Sell'] = df['sell']
        df['Rasio'] = df.apply(lambda x: "Demand" if x['buy'] > x['sell'] else "Supply", axis=1)
        df['Sinyal'] = df.apply(lambda x: generate_signal(x['buy'], x['sell']), axis=1)
        df['Open Posisi'] = df['Sinyal'].apply(open_position_logic)
        df['Harga'] = [format_price(x, pair) for x, pair in zip(df['last'], df.index)]

        df['Sinyal_Val'] = df['Sinyal'].map({
            'STRONG BUY': 4, 'BUY': 3, 'HOLD': 2, 'SELL': 1, 'STRONG SELL': 0
        })
        df = df.sort_values(by='Sinyal_Val', ascending=False)

        styled_df = df[['Harga', 'Volume Buy', 'Volume Sell', 'Rasio', 'Sinyal', 'Open Posisi']].style\
            .format({'Volume Buy': '{:,.0f}', 'Volume Sell': '{:,.0f}'})\
            .applymap(color_signal, subset=['Sinyal'])

        st.dataframe(styled_df, use_container_width=True)
    else:
        st.warning("❗ Tidak ada data ticker tersedia dari Indodax.")
            
# 7. TOP MOVERS ==============================================================================================
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
# PALING BAWAH PAGE ============================================================================================
