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

    def evaluate_kripton_prompt_schema(
        self,
        current_price: float,
        ema_38: float,
        ema_62: float,
        stoch_k: float,
        account_balance: float = 10000.00,
        current_position: Optional[Dict[str, Any]] = None,
        symbol: str = "BTCUSDT",
        leverage: int = 5,
        risk_per_trade_pct: float = 2.0,
        taker_fee_pct: float = 0.05,
        slippage_pct: float = 0.02
    ) -> Dict[str, Any]:
        """
        KRIPTON ALGO-TRADER Otonom Strateji ve Risk Yönetim Motoru.
        Sistem talimatı JSON şeması formatında birebir çıktı üretir.
        """
        # STEP 1: Açık pozisyonu değerlendir
        if current_position is not None:
            side = current_position.get("side", "NONE")
            entry_price = float(current_position.get("entry_price", 0.0))
            stop_loss = float(current_position.get("stop_loss", 0.0))
            take_profit = float(current_position.get("take_profit", 0.0))
            size_usdt = float(current_position.get("position_size_usdt", current_position.get("size_usdt", 0.0)))

            sl_hit = (side == "LONG" and current_price <= stop_loss) or (side == "SHORT" and current_price >= stop_loss)
            tp_hit = (side == "LONG" and current_price >= take_profit) or (side == "SHORT" and current_price <= take_profit)

            if sl_hit or tp_hit:
                reason_type = "TAKE_PROFIT" if tp_hit else "STOP_LOSS"
                # Kayma uygulayarak çıkış fiyatı
                exec_exit = current_price * (1 - (slippage_pct / 100)) if side == "LONG" else current_price * (1 + (slippage_pct / 100))
                
                # Brüt PnL
                if side == "LONG":
                    gross_pnl = (exec_exit - entry_price) / entry_price * size_usdt
                else:
                    gross_pnl = (entry_price - exec_exit) / entry_price * size_usdt

                total_fees = size_usdt * (taker_fee_pct / 100) * 2  # Giriş + Çıkış komisyonu
                net_pnl = gross_pnl - total_fees
                new_balance = account_balance + net_pnl

                return {
                    "action": "CLOSE",
                    "reasoning": f"Açık {side} pozisyonu {reason_type} seviyesine ulaştı. Kapatıldı @ ${exec_exit:.2f}. Net PnL: ${net_pnl:.2f}.",
                    "trade_details": {
                        "symbol": symbol,
                        "side": side,
                        "entry_price": entry_price,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit,
                        "position_size_usdt": size_usdt,
                        "estimated_fee_usdt": round(total_fees, 2)
                    },
                    "account_state": {
                        "balance_usdt": round(new_balance, 2),
                        "active_position": null
                    }
                }

        # STEP 2: Pozisyon yoksa strateji kurallarını tara
        is_bullish_alignment = (ema_38 > ema_62)
        is_bearish_alignment = (ema_38 < ema_62)
        
        # Flat / Sık kesişim kontrolü
        ema_diff_pct = abs(ema_38 - ema_62) / current_price if current_price > 0 else 0.0
        is_flat = (ema_diff_pct < 0.0005)

        is_long_pullback = (stoch_k < 50.0)
        is_short_pullback = (stoch_k > 50.0)

        action = "WAIT"
        side = "NONE"
        entry_price = 0.0
        stop_loss = 0.0
        take_profit = 0.0
        position_size_usdt = 0.0
        estimated_fee_usdt = 0.0
        reasoning = "EMA_38 ve EMA_62 yatay/nötr veya sinyal koşulları karşılanmadı."

        if is_flat:
            action = "WAIT"
            reasoning = "EMA_38 ve EMA_62 yatay seyrediyor ve sıklıkla kesişiyor. Aksiyon: WAIT."
        elif is_bullish_alignment and is_long_pullback:
            action = "BUY"
            side = "LONG"
            entry_price = current_price * (1 + (slippage_pct / 100))
            stop_loss = round(entry_price * 0.99, 2)    # -1.0% Stop Loss
            take_profit = round(entry_price * 1.02, 2)  # +2.0% Take Profit
            
            risk_amount = account_balance * (risk_per_trade_pct / 100)
            position_size_usdt = min(account_balance * leverage, risk_amount / 0.01)
            estimated_fee_usdt = position_size_usdt * (taker_fee_pct / 100)
            reasoning = f"Trend: EMA_38 (${ema_38}) > EMA_62 (${ema_62}) Boğa dizilimi. Tetikleyici: Stoch_K ({stoch_k}) < 50 pullback girişi. BUY (LONG) sinyali."

        elif is_bearish_alignment and is_short_pullback:
            action = "SELL"
            side = "SHORT"
            entry_price = current_price * (1 - (slippage_pct / 100))
            stop_loss = round(entry_price * 1.01, 2)    # +1.0% Stop Loss
            take_profit = round(entry_price * 0.98, 2)  # -2.0% Take Profit

            risk_amount = account_balance * (risk_per_trade_pct / 100)
            position_size_usdt = min(account_balance * leverage, risk_amount / 0.01)
            estimated_fee_usdt = position_size_usdt * (taker_fee_pct / 100)
            reasoning = f"Trend: EMA_38 (${ema_38}) < EMA_62 (${ema_62}) Ayı dizilimi. Tetikleyici: Stoch_K ({stoch_k}) > 50 pullback girişi. SELL (SHORT) sinyali."

        active_position = None
        if action in ["BUY", "SELL"]:
            active_position = {
                "symbol": symbol,
                "side": side,
                "entry_price": round(entry_price, 2),
                "size_usdt": round(position_size_usdt, 2),
                "stop_loss": stop_loss,
                "take_profit": take_profit
            }

        return {
            "action": action,
            "reasoning": reasoning,
            "trade_details": {
                "symbol": symbol,
                "side": side,
                "entry_price": round(entry_price, 2),
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "position_size_usdt": round(position_size_usdt, 2)
            }
        }
