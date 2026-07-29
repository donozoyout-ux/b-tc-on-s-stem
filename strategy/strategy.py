from enum import Enum
from typing import Dict, Any, Optional
import pandas as pd
from strategy.indicators import TechnicalIndicators
from utils.logger import logger


class SignalType(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class KriptonStrategy:
    """
    'Kripton Gezegeni' Strateji Mantığı:
    1. Trend Filtresi (EMA 38 > EMA 62 / Price > EMA 200)
    2. SuperTrend Sinyali (Uzunluk: 10, Çarpan: 1.6)
    3. Stoch RSI Teyidi (Aşırı Alım/Satım Bölgesinden Çıkış)
    """

    def __init__(
        self,
        ema_fast: int = 38,
        ema_slow: int = 62,
        ema_trend: int = 200,
        supertrend_len: int = 10,
        supertrend_mult: float = 1.6,
        stoch_k: int = 3,
        stoch_d: int = 3,
        rsi_len: int = 8,
        stoch_len: int = 10,
        stoch_oversold: float = 35.0,
        stoch_overbought: float = 65.0
    ):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_trend = ema_trend
        self.supertrend_len = supertrend_len
        self.supertrend_mult = supertrend_mult
        self.stoch_k = stoch_k
        self.stoch_d = stoch_d
        self.rsi_len = rsi_len
        self.stoch_len = stoch_len
        self.stoch_oversold = stoch_oversold
        self.stoch_overbought = stoch_overbought

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Geçmiş ve canlı veriyi işleyerek güncel Al/Sat/Nötr sinyali ve indikatör değerlerini üretir.
        """
        df_calc = TechnicalIndicators.calculate_all(
            df=df,
            ema_fast=self.ema_fast,
            ema_slow=self.ema_slow,
            ema_trend=self.ema_trend,
            supertrend_len=self.supertrend_len,
            supertrend_mult=self.supertrend_mult,
            stoch_k=self.stoch_k,
            stoch_d=self.stoch_d,
            rsi_len=self.rsi_len,
            stoch_len=self.stoch_len
        )

        if df_calc is None or len(df_calc) < 2:
            return {"signal": SignalType.NEUTRAL, "reason": "Yetersiz veri"}

        # Son tamamlanmış ve canlı mum verisi
        last = df_calc.iloc[-1]
        prev = df_calc.iloc[-2]

        close_price = last['close']
        fast_ema = last['ema_fast']
        slow_ema = last['ema_slow']
        trend_ema = last['ema_trend']
        st_dir = last['supertrend_direction']
        
        curr_k = last['stoch_k']
        curr_d = last['stoch_d']
        prev_k = prev['stoch_k']
        prev_d = prev['stoch_d']
        
        atr = last.get('atr', 0.0)

        # --- KRIPTON ALGO-TRADER STRATEJİ KURALLARI ---
        # 1. Trend Dizilimi (Bullish Alignment: EMA_38 > EMA_62 / Bearish Alignment: EMA_38 < EMA_62)
        is_bullish_alignment = (fast_ema > slow_ema)
        is_bearish_alignment = (fast_ema < slow_ema)

        # Flat / Yatay Trend Kesişim Kontrolü
        ema_diff_pct = abs(fast_ema - slow_ema) / close_price if close_price > 0 else 0.0
        is_flat_or_crossing = (ema_diff_pct < 0.0005)

        # 2. Pullback Tetikleyicisi (Stoch_K < 50 for Long, Stoch_K > 50 for Short)
        is_long_pullback = (curr_k < self.stoch_oversold)
        is_short_pullback = (curr_k > self.stoch_overbought)

        # --- 3. BİRLEŞİK İŞLEM SİNYALİ ---
        signal = SignalType.NEUTRAL
        reason = "EMA38/EMA62 yatay veya sinyal bulunamadı, bekleniyor (WAIT)."

        if is_flat_or_crossing:
            reason = "EMA38 ve EMA62 yatay/sık kesişiyor (Flat market). Bekleniyor (WAIT)."
        elif is_bullish_alignment and is_long_pullback:
            signal = SignalType.LONG
            reason = f"BUY (LONG) Onaylandı: Trend Boğa Dizilimi (EMA38 > EMA62) & Pullback Tetikleyici (Stoch_K={curr_k:.1f} < 50)."
        elif is_bearish_alignment and is_short_pullback:
            signal = SignalType.SHORT
            reason = f"SELL (SHORT) Onaylandı: Trend Ayı Dizilimi (EMA38 < EMA62) & Pullback Tetikleyici (Stoch_K={curr_k:.1f} > 50)."

        return {
            "signal": signal,
            "reason": reason,
            "close": close_price,
            "atr": atr,
            "supertrend_direction": st_dir,
            "stoch_k": curr_k,
            "stoch_d": curr_d,
            "ema_fast": fast_ema,
            "ema_slow": slow_ema,
            "ema_trend": trend_ema
        }
