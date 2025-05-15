import pandas as pd
import logging

logger = logging.getLogger(__name__)

def get_top_movers(tickers):
    """Ambil top gainers, top losers dan top volume movers."""
    try:
        if not tickers:
            logger.warning("Data tickers kosong")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        df = pd.DataFrame.from_dict(tickers, orient='index')

        if df.empty:
            logger.warning("DataFrame tickers kosong")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        required_columns = ['last', 'change', 'vol_idr']
        if not all(col in df.columns for col in required_columns):
            logger.error(f"Kolom yang diperlukan tidak ada: {required_columns}. Kolom yang tersedia: {df.columns.tolist()}")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # Konversi tipe data
        df['last'] = pd.to_numeric(df['last'], errors='coerce')
        df['change'] = pd.to_numeric(df['change'], errors='coerce')
        df['vol_idr'] = pd.to_numeric(df['vol_idr'], errors='coerce')

        # Filter NaN values
        df = df.dropna(subset=['last', 'change', 'vol_idr'])

        # Top gainers (nilai 'change' terbesar)
        top_gainers = df.sort_values(by='change', ascending=False).head(10)

        # Top losers (nilai 'change' terkecil)
        top_losers = df.sort_values(by='change').head(10)

        # Top volume movers (volume terbesar)
        top_volume = df.sort_values(by='vol_idr', ascending=False).head(10)

        logger.info(f"Kolom top_gainers sebelum return: {top_gainers.columns.tolist()}")
        return top_gainers, top_losers, top_volume

    except Exception as e:
        logger.error(f"Error dalam get_top_movers: {str(e)}", exc_info=True)
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()