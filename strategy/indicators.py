import pandas as pd
import numpy as np
import pandas_ta as ta
from typing import Dict, Any
from utils.logger import logger


class TechnicalIndicators:
    """
    Pandas ve Pandas-TA kullanarak Kripton Gezegeni Stratejisi için indikatör hesaplama sınıfı.
    """

    @staticmethod
    def calculate_all(
        df: pd.DataFrame,
        ema_fast: int = 38,
        ema_slow: int = 62,
        ema_trend: int = 200,
        supertrend_len: int = 10,
        supertrend_mult: float = 1.6,
        stoch_k: int = 3,
        stoch_d: int = 3,
        rsi_len: int = 8,
        stoch_len: int = 10,
        atr_period: int = 14
    ) -> pd.DataFrame:
        """
        Gelen mum (OHLCV) DataFrame'ine tüm gerekli teknik indikatörleri ekler.
        """
        if df is None or len(df) < max(ema_trend, stoch_len + rsi_len):
            logger.warning("İndikatör hesaplaması için yeterli mum verisi yok.")
            return df

        df = df.copy()

        # 1. EMA Ribbon & Ana Trend
        df['ema_fast'] = ta.ema(df['close'], length=ema_fast)
        df['ema_slow'] = ta.ema(df['close'], length=ema_slow)
        df['ema_trend'] = ta.ema(df['close'], length=ema_trend)

        # 2. SuperTrend (Uzunluk: 10, Çarpan: 1.6)
        st = ta.supertrend(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            length=supertrend_len,
            multiplier=supertrend_mult
        )
        
        if st is not None and not st.empty:
            # pandas_ta varsayılan sütun isimleri: SUPERTd_10_1.6, SUPERT_10_1.6
            st_dir_col = f"SUPERTd_{supertrend_len}_{supertrend_mult}"
            st_val_col = f"SUPERT_{supertrend_len}_{supertrend_mult}"
            
            if st_dir_col in st.columns:
                df['supertrend_direction'] = st[st_dir_col]  # 1: Bullish, -1: Bearish
                df['supertrend_value'] = st[st_val_col]
            else:
                # İlk eşleşen sütunları al
                df['supertrend_direction'] = st.iloc[:, 1]
                df['supertrend_value'] = st.iloc[:, 0]
        else:
            df['supertrend_direction'] = 0
            df['supertrend_value'] = 0.0

        # 3. Stochastic RSI (3, 3, 8, 10)
        stochrsi = ta.stochrsi(
            close=df['close'],
            length=rsi_len,
            rsi_length=rsi_len,
            k=stoch_k,
            d=stoch_d
        )
        
        if stochrsi is not None and not stochrsi.empty:
            # Stoch RSI %K ve %D sütunlarını al
            df['stoch_k'] = stochrsi.iloc[:, 0]
            df['stoch_d'] = stochrsi.iloc[:, 1]
        else:
            # Native yedek hesaplama
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=rsi_len).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_len).mean()
            rs = gain / (loss + 1e-10)
            rsi = 100 - (100 / (1 + rs))
            
            stoch_rsi_min = rsi.rolling(window=stoch_len).min()
            stoch_rsi_max = rsi.rolling(window=stoch_len).max()
            stoch = 100 * (rsi - stoch_rsi_min) / (stoch_rsi_max - stoch_rsi_min + 1e-10)
            df['stoch_k'] = stoch.rolling(window=stoch_k).mean()
            df['stoch_d'] = df['stoch_k'].rolling(window=stoch_d).mean()

        # 4. ATR (Average True Range)
        df['atr'] = ta.atr(high=df['high'], low=df['low'], close=df['close'], length=atr_period)

        return df
