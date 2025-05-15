import requests
import pandas as pd
import json
import logging

logger = logging.getLogger(__name__)

# Fungsi untuk mendapatkan summary dari pair tertentu
def get_indodax_summary(pair):
    url = f"https://indodax.com/api/{pair}/ticker"
    try:
        response = requests.get(url)
        response.raise_for_status()
        json_data = response.json()
        if "ticker" not in json_data:
            raise ValueError(f"Pair '{pair}' tidak ditemukan atau tidak valid.")
        data = json_data["ticker"]
        return {
            "high": float(data["high"]),
            "low": float(data["low"]),
            "last": float(data["last"]),
            "percent": ((float(data["last"]) - float(data["low"])) / float(data["low"])) * 100
        }
    except Exception as e:
        logger.error(f"Gagal mengambil data ticker dari Indodax: {e}")
        raise RuntimeError from e

# Fungsi untuk mendapatkan volume perdagangan buy dan sell dari pair tertentu
def get_trade_volume(pair):
    url = f"https://indodax.com/api/{pair}/trades"
    try:
        response = requests.get(url)
        response.raise_for_status()
        trades = response.json()
        df = pd.DataFrame(trades)
        df["price"] = df["price"].astype(float)
        df["amount"] = df["amount"].astype(float)
        df["type"] = df["type"].astype(str)
        buy_volume = df[df["type"] == "buy"]["amount"].sum()
        sell_volume = df[df["type"] == "sell"]["amount"].sum()
        return buy_volume, sell_volume
    except Exception as e:
        logger.error(f"Gagal mengambil data volume perdagangan: {e}")
        return 0, 0

# Fungsi untuk memuat daftar pair yang tersedia di Indodax
def load_indodax_pairs():
    url = "https://indodax.com/api/tickers"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return sorted(data["tickers"].keys())
    except Exception as e:
        logger.error(f"Gagal mengambil daftar pair: {e}")
        return []

# Fungsi untuk mendapatkan data candlestick (ohlc) dari pair tertentu
def get_candlestick_data(pair, tf='5min'):
    url = f"https://indodax.com/api/{pair}/trades"
    try:
        response = requests.get(url)
        response.raise_for_status()
        trades = response.json()
        df = pd.DataFrame(trades)

        if df.empty:
            return pd.DataFrame()

        df['date'] = pd.to_datetime(df['date'], unit='s')
        df['price'] = df['price'].astype(float)
        df['amount'] = df['amount'].astype(float)
        df.set_index('date', inplace=True)

        ohlc = df['price'].resample(tf).ohlc().dropna()
        ohlc['volume'] = df['amount'].resample(tf).sum()

        return ohlc.reset_index()

    except Exception as e:
        logger.error(f"Gagal mengambil data candlestick: {e}")
        return pd.DataFrame()

# Fungsi untuk mengambil semua tickers (pair mata uang) beserta data harga, perubahan, dan volume
def fetch_all_tickers():
    url = "https://indodax.com/api/tickers"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()["tickers"]

        tickers_data = {}
        for pair, info in data.items():
            try:
                tickers_data[pair] = {
                    "last": float(info.get("last", 0)),
                    "change": float(info.get("change", 0)),
                    "vol_idr": float(info.get("vol_idr", 0))
                }
            except (ValueError, TypeError):
                continue

        return tickers_data

    except Exception as e:
        logger.error(f"Gagal mengambil data tickers: {e}")
        return {}

# Fungsi untuk mendapatkan top movers: top gainers, top losers, dan top volume
def get_top_movers(tickers):
    try:
        # Top Gainers: Pairs dengan perubahan harga tertinggi
        top_gainers = sorted(tickers.items(), key=lambda x: x[1]["change"], reverse=True)[:10]
        
        # Top Losers: Pairs dengan perubahan harga terendah
        top_losers = sorted(tickers.items(), key=lambda x: x[1]["change"])[:10]
        
        # Top Volume: Pairs dengan volume tertinggi dalam IDR
        top_volume = sorted(tickers.items(), key=lambda x: x[1]["vol_idr"], reverse=True)[:10]
        
        # Return top gainers, losers, and volume data
        return top_gainers, top_losers, top_volume
    
    except Exception as e:
        logger.error(f"Gagal memproses data top movers: {e}")
        return [], [], []

# Fungsi untuk menampilkan hasil top movers
def display_top_movers(top_gainers, top_losers, top_volume):
    print("\nTop Gainers (Highest Change in Price):")
    for idx, (pair, data) in enumerate(top_gainers, start=1):
        print(f"{idx}. {pair} | Change: {data['change']:.2f}% | Last Price: {data['last']}")

    print("\nTop Losers (Lowest Change in Price):")
    for idx, (pair, data) in enumerate(top_losers, start=1):
        print(f"{idx}. {pair} | Change: {data['change']:.2f}% | Last Price: {data['last']}")

    print("\nTop Volume (Highest Volume in IDR):")
    for idx, (pair, data) in enumerate(top_volume, start=1):
        print(f"{idx}. {pair} | Volume: {data['vol_idr']} IDR | Last Price: {data['last']}")
