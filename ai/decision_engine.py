import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from utils.logger import logger


class AIDecisionEngine:
    """
    Kripton AI Karar Destek ve Piyasa Rejimi Analiz Motoru:
    - Piyasa Rejimi Tespiti (Bullish Trend, Bearish Trend, Yatay/Ranging, Volatil Risk)
    - AI Güven Skoru Hesabı (%0 - %100)
    - Sinyal Doğrulama Kapısı (Signal Gatekeeper)
    - İnsan Dilinde Yapay Zeka Analiz Raporlaması
    """

    def __init__(self, min_confidence_threshold: float = 65.0):
        self.min_confidence_threshold = min_confidence_threshold

    def analyze_market_regime(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Mum verilerini (OHLCV) inceleyerek anlık piyasa rejimini ve AI Güven Skorunu hesaplar.
        """
        if df is None or len(df) < 50:
            return {
                "regime": "NEUTRAL",
                "confidence": 50.0,
                "volatility_status": "NORMAL",
                "reason": "Yetersiz veri derinliği."
            }

        last_row = df.iloc[-1]
        close = float(last_row.get("close", 0.0))
        atr = float(last_row.get("atr", 0.0)) if "atr" in last_row else 0.0
        stoch_k = float(last_row.get("stoch_k", 50.0)) if "stoch_k" in last_row else 50.0
        stoch_d = float(last_row.get("stoch_d", 50.0)) if "stoch_d" in last_row else 50.0
        fast_ema = float(last_row.get("ema_fast", 0.0)) if "ema_fast" in last_row else 0.0
        slow_ema = float(last_row.get("ema_slow", 0.0)) if "ema_slow" in last_row else 0.0
        trend_ema = float(last_row.get("ema_trend", 0.0)) if "ema_trend" in last_row else 0.0

        # Volatilite Analizi
        recent_atrs = df['atr'].tail(20) if 'atr' in df else pd.Series([atr])
        avg_atr = float(recent_atrs.mean()) if len(recent_atrs) > 0 else atr
        volatility_ratio = (atr / avg_atr) if avg_atr > 0 else 1.0

        volatility_status = "NORMAL"
        if volatility_ratio > 1.8:
            volatility_status = "EXTREME_HIGH"
        elif volatility_ratio < 0.6:
            volatility_status = "LOW_COMPRESSION"

        # Trend Rejimi Tespiti
        bullish_alignment = (fast_ema > slow_ema) and (close > trend_ema or trend_ema == 0)
        bearish_alignment = (fast_ema < slow_ema) and (close < trend_ema or trend_ema == 0)

        confidence_score = 50.0
        reasons = []

        if bullish_alignment:
            regime = "STRONG_BULL_TREND"
            confidence_score += 25.0
            reasons.append("38 EMA / 62 EMA Boğa Dizilimi Aktif")
            if close > trend_ema and trend_ema > 0:
                confidence_score += 10.0
                reasons.append("Fiyat 200 EMA Ana Trend Üzerinde")
            if stoch_k > stoch_d and stoch_k < 80:
                confidence_score += 10.0
                reasons.append("Stoch RSI Yukarı Momentum Teyidi")
        elif bearish_alignment:
            regime = "STRONG_BEAR_TREND"
            confidence_score += 25.0
            reasons.append("38 EMA / 62 EMA Ayı Dizilimi Aktif")
            if close < trend_ema and trend_ema > 0:
                confidence_score += 10.0
                reasons.append("Fiyat 200 EMA Ana Trend Altında")
            if stoch_k < stoch_d and stoch_k > 20:
                confidence_score += 10.0
                reasons.append("Stoch RSI Aşağı Momentum Teyidi")
        else:
            regime = "RANGING_CONSOLIDATION"
            reasons.append("Piyasa Yatay Konsolidasyon Bölgesinde")

        # Volatilite cezası / bonusu
        if volatility_status == "EXTREME_HIGH":
            confidence_score -= 15.0
            reasons.append("⚠️ Aşırı Volatilite Risk Bölgesi (ATR Yüksek)")
        elif volatility_status == "LOW_COMPRESSION":
            confidence_score += 5.0
            reasons.append("Düşük Volatilite (Patlama Öncesi Sıkışma)")

        confidence_score = float(np.clip(confidence_score, 10.0, 98.5))

        return {
            "regime": regime,
            "confidence": round(confidence_score, 1),
            "volatility_status": volatility_status,
            "reason": " | ".join(reasons),
            "close": close,
            "atr": atr
        }

    def validate_signal(
        self,
        signal_type: str,
        df: pd.DataFrame,
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Üretilen teknik sinyali AI mantık filtresinden geçirir.
        İşlemin açılıp açılmayacağına karar verir.
        """
        ai_market = self.analyze_market_regime(df)
        confidence = ai_market["confidence"]
        regime = ai_market["regime"]
        reason = ai_market["reason"]

        approved = False

        if signal_type == "LONG":
            if regime in ["STRONG_BULL_TREND", "RANGING_CONSOLIDATION"] and confidence >= self.min_confidence_threshold:
                approved = True
                verdict = f"AI LONG İŞLEMİ ONAYLADI (Güven: %{confidence:.1f})"
            else:
                verdict = f"AI LONG İŞLEMİNİ REDDETTİ (Güven Yetersiz: %{confidence:.1f} < %{self.min_confidence_threshold})"

        elif signal_type == "SHORT":
            if regime in ["STRONG_BEAR_TREND", "RANGING_CONSOLIDATION"] and confidence >= self.min_confidence_threshold:
                approved = True
                verdict = f"AI SHORT İŞLEMİ ONAYLADI (Güven: %{confidence:.1f})"
            else:
                verdict = f"AI SHORT İŞLEMİNİ REDDETTİ (Güven Yetersiz: %{confidence:.1f} < %{self.min_confidence_threshold})"

        else:
            verdict = "Sinyal Yok (Nötr)"

        logger.info(f"[AI DECISION ENGINE]: {verdict} | Rejim: {regime}")

        return {
            "approved": approved,
            "confidence": confidence,
            "regime": regime,
            "verdict": verdict,
            "reason": reason
        }

    def generate_ai_insight_summary(self, df: pd.DataFrame) -> str:
        """
        Dashboard ve Telegram için insan dilinde anlık Yapay Zeka Piyasa Özeti üretir.
        """
        market = self.analyze_market_regime(df)
        regime_tr = {
            "STRONG_BULL_TREND": "Güçlü Boğa Trendi 🟢",
            "STRONG_BEAR_TREND": "Güçlü Ayı Trendi 🔴",
            "RANGING_CONSOLIDATION": "Yatay Konsolidasyon 🟡",
            "NEUTRAL": "Nötr Piyasa"
        }.get(market["regime"], market["regime"])

        summary = (
            f"🤖 <b>AI Piyasa Raporu:</b> {regime_tr}\n"
            f"<b>AI Güven Skoru:</b> %{market['confidence']}\n"
            f"<b>Volatilite Durumu:</b> {market['volatility_status']}\n"
            f"<b>Analiz Özeti:</b> {market['reason']}"
        )
        return summary
