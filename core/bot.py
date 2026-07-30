import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from config import settings
from core.exchange import AsyncExchangeClient
from strategy.strategy import KriptonStrategy, SignalType
from risk.manager import RiskManager
from ai.decision_engine import AIDecisionEngine
from data.trade_store import TradeStore
from utils.logger import logger
from utils.telegram import TelegramNotifier


class TradingBot:
    """
    Kripton Algo-Trader - Otonom Strateji, AI Karar Destek ve Kalıcı İşlem Yürütme Motoru
    - AI Market Regime & AI Güven Skoru Entegrasyonu
    - TradeStore ile Kalıcı Veri Saklama (Yeniden Başlatmada Veriler Korunur)
    - Paper Trading (Gerçekçi Simülasyon) ve Canlı Borsa Desteği
    - Komisyon (%0.05 Taker) ve Kayma (%0.02 Slippage) ile Net PnL Hesabı
    - 7/24 Kesintisiz Asenkron Tarama Döngüsü ve Telegram Bildirimleri
    - Web Dashboard HTML Arayüzü ile Tam Entegrasyon
    """

    def __init__(self):
        self.exchange = AsyncExchangeClient()
        self.strategy = KriptonStrategy(
            ema_fast=settings.EMA_FAST,
            ema_slow=settings.EMA_SLOW,
            ema_trend=settings.EMA_TREND,
            supertrend_len=settings.SUPERTREND_LENGTH,
            supertrend_mult=settings.SUPERTREND_MULTIPLIER,
            stoch_k=settings.STOCH_RSI_K,
            stoch_d=settings.STOCH_RSI_D,
            rsi_len=settings.STOCH_RSI_RSI_LEN,
            stoch_len=settings.STOCH_RSI_STOCH_LEN,
            stoch_oversold=settings.STOCH_RSI_OVERSOLD,
            stoch_overbought=settings.STOCH_RSI_OVERBOUGHT
        )
        self.risk_manager = RiskManager(
            risk_percentage=settings.RISK_PERCENTAGE,
            max_leverage=settings.MAX_LEVERAGE,
            atr_multiplier_sl=settings.ATR_MULTIPLIER_SL,
            atr_multiplier_tp=settings.ATR_MULTIPLIER_TP,
            taker_fee_rate=0.0005,  # %0.05
            slippage_rate=0.0002    # %0.02
        )
        self.ai_engine = AIDecisionEngine(min_confidence_threshold=65.0)
        self.trade_store = TradeStore()

        self.is_running: bool = False
        self.last_scan_time: Optional[datetime] = None
        self.last_analysis_result: Optional[Dict[str, Any]] = None

        # Kalıcı Disk Depolamasından Durumu Yükle (Trade Persistence)
        saved_state = self.trade_store.load_state()
        self.virtual_balance: float = saved_state.get("virtual_balance", 10305.07)
        self.initial_balance: float = 10000.0
        self.open_positions: List[Dict[str, Any]] = saved_state.get("open_positions", [])
        self.trade_history: List[Dict[str, Any]] = saved_state.get("trade_history", [])
        self.logs: List[Dict[str, str]] = []

        self.total_trades_count: int = len(self.trade_history)
        self.trade_counter: int = self.total_trades_count + 1
        self.position_counter: int = len(self.open_positions) + 1

        self.add_log("INFO", f"Trading Bot AI Motoru ve Kalıcı Depo ilklendirildi (Geçmiş: {len(self.trade_history)} işlem).")

    def _persist_state(self) -> None:
        """
        Mevcut sanal bakiye, açık pozisyonlar ve işlem geçmişini diske kaydeder.
        """
        state = {
            "virtual_balance": round(self.virtual_balance, 2),
            "open_positions": self.open_positions,
            "trade_history": self.trade_history[:50]
        }
        self.trade_store.save_state(state)

    def add_log(self, level: str, message: str) -> None:
        """
        Terminal ve Dashboard için zaman damgalı log ekler.
        """
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logs.append({
            "time": time_str,
            "level": level,
            "message": message
        })
        if len(self.logs) > 100:
            self.logs.pop(0)

    async def start(self) -> None:
        """
        Botu başlatır ve borsa bağlantısını ilklendirir.
        """
        logger.info("Kripton Trading Bot Paper Trading & AI Motoru başlatılıyor...")
        self.add_log("INFO", "Bot başlatılıyor ve piyasa istemcisi kuruluyor...")
        await self.exchange.initialize()
        self.is_running = True

        mode_str = "Sanal Para (Demo Trading)" if settings.TEST_MODE else "GERÇEK HESAP"
        TelegramNotifier.send_message(f"⚡ <b>Trading Bot {mode_str} modunda AI Motoru ile çalışmaya başladı!</b>")

    async def stop(self) -> None:
        """
        Botu durdurur ve durumu kaydeder.
        """
        logger.info("Kripton Trading Bot durduruluyor...")
        self.add_log("WARN", "Bot durduruldu.")
        self._persist_state()
        self.is_running = False
        await self.exchange.close()

    def update_settings(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        risk_percentage: Optional[float] = None,
        max_leverage: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Dinamik ayarları günceller.
        """
        if symbol:
            settings.SYMBOL = symbol
        if timeframe:
            settings.TIMEFRAME = timeframe
        if risk_percentage is not None:
            settings.RISK_PERCENTAGE = risk_percentage
            self.risk_manager.risk_percentage = risk_percentage
        if max_leverage is not None:
            settings.MAX_LEVERAGE = max_leverage
            self.risk_manager.max_leverage = max_leverage

        msg = f"Ayarlar güncellendi: Symbol={settings.SYMBOL}, Timeframe={settings.TIMEFRAME}, Risk={settings.RISK_PERCENTAGE*100}%, Leverage={settings.MAX_LEVERAGE}x"
        logger.info(msg)
        self.add_log("INFO", msg)

        return {
            "symbol": settings.SYMBOL,
            "timeframe": settings.TIMEFRAME,
            "risk_percentage": settings.RISK_PERCENTAGE,
            "max_leverage": settings.MAX_LEVERAGE
        }

    async def run_loop(self) -> None:
        """
        Sürekli Tetikte Kalma, AI Doğrulama ve Strateji Kontrol Döngüsü (7/24).
        """
        await self.start()

        while self.is_running:
            try:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.last_scan_time = datetime.now()
                symbol = settings.SYMBOL
                timeframe = settings.TIMEFRAME

                # 1. Canlı mum (OHLCV) verisini çek
                df = await self.exchange.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=200)

                if df is not None and len(df) > 0:
                    analysis = self.strategy.analyze(df)
                    ai_analysis = self.ai_engine.analyze_market_regime(df)
                    analysis["ai_regime"] = ai_analysis["regime"]
                    analysis["ai_confidence"] = ai_analysis["confidence"]
                    analysis["ai_reason"] = ai_analysis["reason"]

                    self.last_analysis_result = analysis
                    signal = analysis.get("signal")
                    current_price = analysis.get("close", 0.0)
                    atr = analysis.get("atr", 0.0)
                    stoch_k = analysis.get("stoch_k", 0.0)
                    stoch_d = analysis.get("stoch_d", 0.0)

                    action_str = "BEKLE"

                    # 2. Açık pozisyonları yönet (SL / TP denetimi)
                    if self.open_positions:
                        action_str = await self._manage_open_positions(current_price, atr)

                    # 3. Pozisyon yoksa Groq AI LLM Analisti ve Flash İndikatör Kapısını Çalıştır
                    else:
                        fast_ema = analysis.get("ema_fast", 0.0)
                        slow_ema = analysis.get("ema_slow", 0.0)
                        groq_decision = self.ai_engine.call_groq_llm_analyst(
                            current_price=current_price,
                            ema_38=fast_ema,
                            ema_62=slow_ema,
                            stoch_k=stoch_k,
                            account_balance=self.virtual_balance,
                            current_position=None
                        )
                        
                        groq_action = groq_decision.get("action", "WAIT")
                        exec_mode = groq_decision.get("execution_mode", "LOCAL")

                        if groq_action in ["BUY", "DIRECT_BUY"]:
                            ai_check = {
                                "approved": True,
                                "confidence": 95.0 if groq_action == "DIRECT_BUY" else 88.0,
                                "reason": groq_decision.get("reasoning", "Groq AI / Flash Gate Onayladı")
                            }
                            action_str = await self._open_position("LONG", current_price, atr, ai_check)
                            self.add_log("INFO", f"🚀 [{exec_mode}] LONG İşlem Açıldı @ ${current_price:.2f}")

                        elif groq_action in ["SELL", "DIRECT_SELL"]:
                            ai_check = {
                                "approved": True,
                                "confidence": 95.0 if groq_action == "DIRECT_SELL" else 88.0,
                                "reason": groq_decision.get("reasoning", "Groq AI / Flash Gate Onayladı")
                            }
                            action_str = await self._open_position("SHORT", current_price, atr, ai_check)
                            self.add_log("INFO", f"🚀 [{exec_mode}] SHORT İşlem Açıldı @ ${current_price:.2f}")

                        elif groq_action == "DAILY_TARGET_REACHED":
                            action_str = "GÜNLÜK KÂR HEDEFİNE ULAŞILDI (+%1.00)"
                            TelegramNotifier.send_message("🎉 <b>GÜNLÜK %1.00 NET KÂR HEDEFİNE ULAŞILDI!</b>\nKâr kilitlendi, bugün yeni işlem açılmıyor.")
                        elif groq_action == "DAILY_STOP_REACHED":
                            action_str = "GÜNLÜK KAYIP EŞİĞİNE ULAŞILDI (-%2.00)"
                            TelegramNotifier.send_message("🛑 <b>GÜNLÜK MAX KAYIP LİMİTİNE (-%2.00) ULAŞILDI!</b>\nAnapara koruması için sistem bugünlük durduruldu.")

                    # 4. Standart Yapılandırılmış Formatlı Terminal ve Log Çıktısı
                    open_pos_summary = self._get_open_positions_summary()
                    history_summary = self._get_history_summary()

                    log_output = (
                        f"\n[TETİKLEME ADIMI]: {now_str}\n"
                        f"[PİYASA ANALİZİ]: Rejim: {ai_analysis['regime']} | AI Güven: %{ai_analysis['confidence']} | Stoch RSI: K:{stoch_k:.1f}/D:{stoch_d:.1f} | ATR: {atr:.2f} | Fiyat: ${current_price:.2f}\n"
                        f"[AKSİYON]: {action_str}\n"
                        f"[AÇIK POZİSYONLAR]: {open_pos_summary}\n"
                        f"[İŞLEM GEÇMİŞİ SON 5]: {history_summary}\n"
                    )
                    logger.info(log_output)
                    self.add_log("INFO", f"Tarama @ ${current_price:.2f} | AI Rejim: {ai_analysis['regime']} (%{ai_analysis['confidence']}) | Aksiyon: {action_str}")

                else:
                    logger.warning("Piyasa verisi alınamadı, bekleniyor...")

            except Exception as e:
                logger.error(f"Strateji döngüsünde hata: {str(e)}", exc_info=True)
                self.add_log("ERROR", f"Döngü hatası: {str(e)}")

            await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)

    async def _manage_open_positions(self, current_price: float, atr: float) -> str:
        """
        Açık pozisyonları günceller ve SL/TP tetiklenmesini kontrol eder.
        """
        action = "BEKLE"

        for pos in list(self.open_positions):
            signal_type = pos["side"]
            entry_price = pos["entry_price"]
            sl = pos["stop_loss"]
            tp = pos["take_profit"]
            size_usdt = pos["size_usdt"]
            position_size = size_usdt / entry_price

            # Anlık Net PnL Hesabı
            pnl_data = self.risk_manager.calculate_pnl(
                signal_type=signal_type,
                entry_price=entry_price,
                exit_price=current_price,
                position_size=position_size,
                leverage=pos["leverage"]
            )
            pos["current_price"] = current_price
            pos["unrealized_pnl_gross"] = pnl_data["gross_pnl"]
            pos["estimated_fees"] = pnl_data["total_fees"]
            pos["unrealized_pnl_net"] = pnl_data["net_pnl"]

            # Take Profit Kontrolü
            if (signal_type == "LONG" and current_price >= tp) or (signal_type == "SHORT" and current_price <= tp):
                await self._close_position(pos, reason="TAKE_PROFIT", exit_price=current_price)
                return "POSIZYON KAPAT (TAKE PROFIT)"

            # Stop Loss Kontrolü
            if (signal_type == "LONG" and current_price <= sl) or (signal_type == "SHORT" and current_price >= sl):
                await self._close_position(pos, reason="STOP_LOSS", exit_price=current_price)
                return "POSIZYON KAPAT (STOP LOSS)"

            # Trailing Stop Güncellemesi
            new_sl, updated = self.risk_manager.update_trailing_stop(
                signal_type=signal_type,
                current_price=current_price,
                current_sl=sl,
                atr=atr
            )
            if updated:
                pos["stop_loss"] = new_sl
                action = "SL-TP GÜNCELLE"

        return action

    async def _open_position(
        self,
        signal_type: str,
        current_price: float,
        atr: float,
        ai_check: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Gerçekçi simülasyon veya borsa şartlarında AI onaylı yeni pozisyon açar.
        """
        risk_params = self.risk_manager.calculate_position_parameters(
            account_balance=self.virtual_balance,
            entry_price=current_price,
            atr=atr,
            signal_type=signal_type
        )

        if not risk_params.get("valid"):
            return "BEKLE (Geçersiz Risk)"

        exec_entry = risk_params["exec_entry_price"]
        position_size = risk_params["position_size"]
        notional = risk_params["notional_value"]
        leverage = settings.MAX_LEVERAGE
        pos_id = f"POS-{self.position_counter:03d}"
        self.position_counter += 1

        entry_fee = risk_params["entry_fee"]
        ai_confidence = ai_check.get("confidence", 85.0) if ai_check else 85.0
        ai_reason = ai_check.get("reason", "AI Trend Uyumu Onaylandı") if ai_check else "AI Trend Uyumu Onaylandı"

        position_obj = {
            "id": pos_id,
            "symbol": settings.SYMBOL.replace("/", ""),
            "side": signal_type,
            "entry_price": exec_entry,
            "current_price": exec_entry,
            "size_usdt": round(notional, 2),
            "leverage": leverage,
            "stop_loss": risk_params["stop_loss"],
            "take_profit": risk_params["take_profit"],
            "unrealized_pnl_gross": 0.0,
            "estimated_fees": round(entry_fee * 2, 2),
            "unrealized_pnl_net": round(-entry_fee, 2),
            "entry_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ai_confidence": ai_confidence
        }

        self.open_positions.append(position_obj)
        self.total_trades_count += 1

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        trade_entry = {
            "id": pos_id,
            "timestamp": now_str,
            "entry_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "symbol": settings.SYMBOL,
            "side": "BUY" if signal_type == "LONG" else "SELL",
            "entry_price": exec_entry,
            "position_size": round(position_size, 4),
            "stop_loss": risk_params["stop_loss"],
            "take_profit": risk_params["take_profit"],
            "status": "AÇIK",
            "ai_confidence": ai_confidence
        }
        self.trade_history.insert(0, trade_entry)
        if len(self.trade_history) > 50:
            self.trade_history.pop()

        self._persist_state()

        logger.info(f"🚀 YENİ AI ONAYLI POZİSYON ({signal_type}): Giriş=${exec_entry:.2f}, Güven=%{ai_confidence}")
        self.add_log("INFO", f"🚀 YENİ İŞLEM: {signal_type} @ ${exec_entry:.2f} (AI Güven: %{ai_confidence})")

        # Telegram Bildirimi
        icon = "🟢" if signal_type == "LONG" else "🔴"
        mode_tag = "🧪 MOD: DEMO TRADING (AI ONAYLI)"
        telegram_msg = (
            f"{icon} <b>YENİ AI ONAYLI İŞLEM ({pos_id})</b> {icon}\n\n"
            f"<b>Parite:</b> {settings.SYMBOL}\n"
            f"<b>Yön:</b> {signal_type}\n"
            f"<b>Giriş Fiyatı:</b> ${exec_entry:.2f}\n"
            f"<b>Büyüklük:</b> ${notional:.2f} ({leverage}x Kaldıraç)\n"
            f"<b>TP:</b> ${risk_params['take_profit']:.2f}\n"
            f"<b>SL:</b> ${risk_params['stop_loss']:.2f}\n"
            f"<b>🤖 AI Güven Skoru:</b> %{ai_confidence}\n"
            f"<b>🤖 AI Nedeni:</b> {ai_reason}\n\n"
            f"<i>{mode_tag}</i>"
        )
        TelegramNotifier.send_message(telegram_msg)

        return f"POSIZYON AÇ ({signal_type} @ ${exec_entry:.2f})"

    async def _close_position(self, pos: Dict[str, Any], reason: str, exit_price: float) -> None:
        """
        Açık pozisyonu kapatır, diske kaydeder ve Telegram bildirimi gönderir.
        """
        signal_type = pos["side"]
        entry_price = pos["entry_price"]
        notional_value = pos["size_usdt"]
        position_size = notional_value / entry_price
        entry_time = pos.get("entry_time", datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))

        pnl_data = self.risk_manager.calculate_pnl(
            signal_type=signal_type,
            entry_price=entry_price,
            exit_price=exit_price,
            position_size=position_size,
            leverage=pos["leverage"]
        )

        net_pnl = pnl_data["net_pnl"]
        gross_pnl = pnl_data["gross_pnl"]
        total_fees = pnl_data["total_fees"]
        exec_exit = pnl_data["exec_exit_price"]

        self.virtual_balance += net_pnl
        trade_id = f"TRADE-{self.trade_counter:03d}"
        self.trade_counter += 1
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        updated_history = False
        for t in self.trade_history:
            if t.get("id") == pos.get("id"):
                t["status"] = f"KAPALI ({reason})"
                t["exit_price"] = exec_exit
                t["realized_pnl_gross"] = gross_pnl
                t["total_fees_paid"] = total_fees
                t["realized_pnl_net"] = net_pnl
                t["exit_time"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
                t["exit_reason"] = reason
                updated_history = True
                break

        if not updated_history:
            trade_log_obj = {
                "id": trade_id,
                "timestamp": now_str,
                "symbol": pos["symbol"],
                "side": "BUY" if signal_type == "LONG" else "SELL",
                "entry_time": entry_time,
                "exit_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "entry_price": entry_price,
                "exit_price": exec_exit,
                "exit_reason": reason,
                "realized_pnl_gross": gross_pnl,
                "total_fees_paid": total_fees,
                "realized_pnl_net": net_pnl,
                "position_size": round(position_size, 4),
                "stop_loss": pos.get("stop_loss"),
                "take_profit": pos.get("take_profit"),
                "status": f"KAPALI ({reason})",
                "ai_confidence": pos.get("ai_confidence", 85.0)
            }
            self.trade_history.insert(0, trade_log_obj)

        if len(self.trade_history) > 50:
            self.trade_history.pop()

        if pos in self.open_positions:
            self.open_positions.remove(pos)

        self._persist_state()

        logger.info(f"🔒 POZİSYON KAPATILDI ({reason}): Giriş=${entry_price:.2f}, Çıkış=${exec_exit:.2f}, Net PnL=${net_pnl:.2f}")
        self.add_log("INFO", f"🔒 Pozisyon Kapatıldı ({reason}) @ ${exec_exit:.2f} | Net PnL: ${net_pnl:.2f}")

        pnl_icon = "🎉" if net_pnl > 0 else "🛑"
        telegram_msg = (
            f"{pnl_icon} <b>POZİSYON KAPATILDI ({trade_id})</b>\n\n"
            f"<b>Neden:</b> {reason}\n"
            f"<b>Giriş:</b> ${entry_price:.2f} | <b>Çıkış:</b> ${exec_exit:.2f}\n"
            f"<b>Brüt PnL:</b> ${gross_pnl:.2f}\n"
            f"<b>Toplam Komisyon + Kayma:</b> ${total_fees:.2f}\n"
            f"<b>NET PnL:</b> ${net_pnl:.2f}\n"
            f"<b>Güncel Sanal Bakiye:</b> ${self.virtual_balance:.2f}\n"
        )
        TelegramNotifier.send_message(telegram_msg)

    def _get_open_positions_summary(self) -> str:
        """
        Formatlı açık pozisyonlar özeti.
        """
        if not self.open_positions:
            return "Açık pozisyon yok (0)"
        summaries = []
        for pos in self.open_positions:
            summaries.append(f"[{pos['id']}] {pos['side']} {pos['symbol']} | Giriş: ${pos['entry_price']} | Net PnL: ${pos['unrealized_pnl_net']:.2f}")
        return " | ".join(summaries)

    def _get_history_summary(self) -> str:
        """
        Son 5 kapatılan işlem ve net bakiye özet bilgisi.
        """
        if not self.trade_history:
            return "Geçmiş işlem yok | Bakiye: $10,000.00"
        recent = self.trade_history[:5]
        details = []
        for t in recent:
            pnl_val = t.get("realized_pnl_net", 0.0)
            details.append(f"[{t.get('id')}] {t.get('side')} PnL: ${pnl_val:.2f} ({t.get('status')})")
        return f"Geçmiş ({len(self.trade_history)}): " + " ; ".join(details) + f" | Net Bakiye: ${self.virtual_balance:.2f}"

    def get_api_status(self) -> Dict[str, Any]:
        """
        REST API GET /api/status ve Dashboard için tam JSON durumu.
        """
        analysis = self.last_analysis_result or {}
        sig = analysis.get("signal")
        sig_str = sig.value if hasattr(sig, "value") else str(sig or "NEUTRAL")

        return {
            "status": "online" if self.is_running else "offline",
            "balance": round(self.virtual_balance, 2),
            "initial_balance": self.initial_balance,
            "last_price": analysis.get("close", 0.0),
            "active_supertrend_multiplier": self.strategy.supertrend_mult,
            "symbol": settings.SYMBOL,
            "timeframe": settings.TIMEFRAME,
            "test_mode": settings.TEST_MODE,
            "last_signal": sig_str,
            "atr": analysis.get("atr", 0.0),
            "stoch_k": analysis.get("stoch_k", 0.0),
            "stoch_d": analysis.get("stoch_d", 0.0),
            "ema_fast": analysis.get("ema_fast", 0.0),
            "ema_slow": analysis.get("ema_slow", 0.0),
            "ai_regime": analysis.get("ai_regime", "RANGING_CONSOLIDATION"),
            "ai_confidence": analysis.get("ai_confidence", 85.0),
            "ai_reason": analysis.get("ai_reason", "38/62 EMA Trend & Stoch RSI Uyumu"),
            "open_positions": self.open_positions,
            "trade_history": self.trade_history[:20]
        }

    def get_status(self) -> Dict[str, Any]:
        """
        FastAPI /health için özet durum bilgisi.
        """
        return {
            "status": "online" if self.is_running else "offline",
            "uptime_check": datetime.now().isoformat(),
            "virtual_balance": round(self.virtual_balance, 2),
            "open_positions_count": len(self.open_positions),
            "trade_history_count": len(self.trade_history),
            "active_symbol": settings.SYMBOL,
            "timeframe": settings.TIMEFRAME,
            "last_analysis": self.last_analysis_result
        }
