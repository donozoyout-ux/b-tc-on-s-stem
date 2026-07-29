import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from config import settings
from core.exchange import AsyncExchangeClient
from strategy.strategy import KriptonStrategy, SignalType
from risk.manager import RiskManager
from utils.logger import logger
from utils.telegram import TelegramNotifier


class TradingBot:
    """
    Ana Algoritmik Ticaret Motoru:
    - 7/24 Kesintisiz Asenkron Tarama Döngüsü
    - Sinyal Üretimi ve İşlem Yönetimi
    - Canlı Pozisyon ve Risk Takibi
    - Telegram Bildirim Entegrasyonu
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
            atr_multiplier_tp=settings.ATR_MULTIPLIER_TP
        )

        self.is_running: bool = False
        self.current_position: Optional[Dict[str, Any]] = None
        self.last_scan_time: Optional[datetime] = None
        self.last_analysis_result: Optional[Dict[str, Any]] = None
        self.total_trades: int = 0
        self.successful_trades: int = 0

    async def start(self) -> None:
        """
        Botu başlatır ve borsa bağlantısını sağlar.
        """
        logger.info("Kripton Trading Bot başlatılıyor...")
        await self.exchange.initialize()
        self.is_running = True

        # Telegram Başlangıç Bildirimi
        mode_str = "Sanal Para (Testnet)" if settings.TEST_MODE else "GERÇEK HESAP"
        TelegramNotifier.send_message(f"⚡ <b>Trading Bot {mode_str} modunda çalışmaya başladı!</b>")

    async def stop(self) -> None:
        """
        Botu güvenli şekilde durdurur.
        """
        logger.info("Kripton Trading Bot durduruluyor...")
        self.is_running = False
        await self.exchange.close()

    async def update_strategy_params(
        self,
        supertrend_mult: Optional[float] = None,
        ema_fast: Optional[int] = None,
        ema_slow: Optional[int] = None
    ) -> None:
        """
        Adaptif optimizasyon modülünden gelen güncellenmiş parametreleri canlı stratejiye uygular.
        """
        if supertrend_mult:
            self.strategy.supertrend_mult = supertrend_mult
        if ema_fast:
            self.strategy.ema_fast = ema_fast
        if ema_slow:
            self.strategy.ema_slow = ema_slow
        logger.info(f"Strateji parametreleri adaptif olarak güncellendi: SuperTrend Mult={self.strategy.supertrend_mult}")

    async def run_loop(self) -> None:
        """
        Arka planda kesintisiz 7/24 çalışan asenkron trading döngüsü.
        """
        await self.start()

        while self.is_running:
            try:
                self.last_scan_time = datetime.now()
                symbol = settings.SYMBOL
                timeframe = settings.TIMEFRAME

                # 1. Canlı mum (OHLCV) verisini çek
                df = await self.exchange.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=200)

                if df is not None and len(df) > 0:
                    # 2. Strateji analizi yap
                    analysis = self.strategy.analyze(df)
                    self.last_analysis_result = analysis
                    signal = analysis.get("signal")
                    current_price = analysis.get("close", 0.0)
                    atr = analysis.get("atr", 0.0)

                    logger.info(
                        f"[{self.last_scan_time.strftime('%H:%M:%S')}] {symbol} ({timeframe}) | "
                        f"Fiyat: {current_price:.2f} | Sinyal: {signal.value} | Açıklama: {analysis.get('reason')}"
                    )

                    # 3. Mevcut pozisyon varsa yönet (Trailing Stop / TP kontrolü)
                    if self.current_position:
                        await self._manage_active_position(current_price, atr)

                    # 4. Açık pozisyon yoksa ve yeni sinyal geldiyse pozisyon aç
                    elif signal in [SignalType.LONG, SignalType.SHORT]:
                        await self._open_new_position(signal.value, current_price, atr)

                else:
                    logger.warning("Mum verisi alınamadı, bir sonraki döngü bekleniyor...")

            except Exception as e:
                logger.error(f"Trading döngüsünde beklenmeyen hata: {str(e)}", exc_info=True)

            # Tarama sıklığı kadar bekle
            await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)

    async def _manage_active_position(self, current_price: float, atr: float) -> None:
        """
        Açık pozisyon için Trailing Stop Loss ve Kar Al kontrolü yapar.
        """
        pos = self.current_position
        signal_type = pos["signal_type"]
        entry_price = pos["entry_price"]
        sl = pos["stop_loss"]
        tp = pos["take_profit"]

        # Take Profit Kontrolü
        if (signal_type == "LONG" and current_price >= tp) or (signal_type == "SHORT" and current_price <= tp):
            logger.info(f"🎯 TAKE PROFIT TETİKLENDİ! Fiyat: {current_price}, TP: {tp}")
            await self._close_position(reason="TAKE_PROFIT", exit_price=current_price)
            return

        # Stop Loss Kontrolü
        if (signal_type == "LONG" and current_price <= sl) or (signal_type == "SHORT" and current_price >= sl):
            logger.info(f"🛑 STOP LOSS TETİKLENDİ! Fiyat: {current_price}, SL: {sl}")
            await self._close_position(reason="STOP_LOSS", exit_price=current_price)
            return

        # Trailing Stop Güncellemesi
        new_sl, updated = self.risk_manager.update_trailing_stop(
            signal_type=signal_type,
            current_price=current_price,
            current_sl=sl,
            atr=atr
        )

        if updated:
            logger.info(f"📈 Trailing Stop Loss Güncellendi: {sl} -> {new_sl}")
            self.current_position["stop_loss"] = new_sl

    async def _open_new_position(self, signal_type: str, current_price: float, atr: float) -> None:
        """
        Sinyale uygun olarak yeni pozisyon açar ve Telegram bildirimi gönderir.
        """
        balance = await self.exchange.fetch_balance()
        risk_params = self.risk_manager.calculate_position_parameters(
            account_balance=balance,
            entry_price=current_price,
            atr=atr,
            signal_type=signal_type
        )

        if not risk_params.get("valid"):
            logger.warning("Risk parametreleri doğrulanamadı, pozisyon açılmıyor.")
            return

        side = "buy" if signal_type == "LONG" else "sell"
        position_size = risk_params["position_size"]

        order = await self.exchange.create_order(
            symbol=settings.SYMBOL,
            order_type="market",
            side=side,
            amount=position_size
        )

        if order:
            self.current_position = {
                "signal_type": signal_type,
                "entry_price": current_price,
                "position_size": position_size,
                "stop_loss": risk_params["stop_loss"],
                "take_profit": risk_params["take_profit"],
                "entry_time": datetime.now().isoformat(),
                "order_id": order.get("id")
            }
            self.total_trades += 1
            logger.info(
                f"🚀 YENİ POZİSYON AÇILDI ({signal_type}): Giriş={current_price}, "
                f"Miktar={position_size}, SL={risk_params['stop_loss']}, TP={risk_params['take_profit']}"
            )

            # Telegram İşlem Bildirimi
            icon = "🟢" if signal_type == "LONG" else "🔴"
            direction_str = "BUY / LONG" if signal_type == "LONG" else "SELL / SHORT"
            mode_tag = "🧪 MOD: SANAL PARA (TESTNET)" if settings.TEST_MODE else "⚠️ MOD: GERÇEK HESAP"

            telegram_msg = (
                f"{icon} <b>YENİ İŞLEM AÇILDI</b> {icon}\n\n"
                f"<b>Parite:</b> {settings.SYMBOL}\n"
                f"<b>İşlem Yönü:</b> {direction_str}\n"
                f"<b>Giriş Fiyatı:</b> {current_price}\n"
                f"<b>Pozisyon Büyüklüğü:</b> {position_size}\n"
                f"<b>Take Profit (TP):</b> {risk_params['take_profit']}\n"
                f"<b>Stop Loss (SL):</b> {risk_params['stop_loss']}\n\n"
                f"<i>{mode_tag}</i>"
            )
            TelegramNotifier.send_message(telegram_msg)

    async def _close_position(self, reason: str, exit_price: float) -> None:
        """
        Açık pozisyonu kapatır, istatistikleri günceller ve Telegram bildirimi gönderir.
        """
        if not self.current_position:
            return

        pos = self.current_position
        signal_type = pos["signal_type"]
        entry_price = pos["entry_price"]
        side = "sell" if signal_type == "LONG" else "buy"
        amount = pos["position_size"]

        await self.exchange.create_order(
            symbol=settings.SYMBOL,
            order_type="market",
            side=side,
            amount=amount
        )

        # Kar/Zarar Hesabı
        pnl = (exit_price - entry_price) if signal_type == "LONG" else (entry_price - exit_price)
        if pnl > 0:
            self.successful_trades += 1

        logger.info(f"🔒 POZİSYON KAPATILDI ({reason}): Kapanış Fiyatı={exit_price}, Tahmini PnL={pnl:.4f}")

        # Telegram Pozisyon Kapanış Bildirimi
        pnl_icon = "🎉" if pnl > 0 else "🛑"
        mode_tag = "🧪 MOD: SANAL PARA (TESTNET)" if settings.TEST_MODE else "⚠️ MOD: GERÇEK HESAP"
        close_msg = (
            f"{pnl_icon} <b>POZİSYON KAPATILDI</b> ({reason})\n\n"
            f"<b>Parite:</b> {settings.SYMBOL}\n"
            f"<b>Kapanış Fiyatı:</b> {exit_price}\n"
            f"<b>Tahmini PnL:</b> {pnl:.4f}\n\n"
            f"<i>{mode_tag}</i>"
        )
        TelegramNotifier.send_message(close_msg)

        self.current_position = None

    def get_status(self) -> Dict[str, Any]:
        """
        FastAPI /health ve dashboard için botun anlık durumunu döndürür.
        """
        return {
            "status": "online" if self.is_running else "offline",
            "uptime_check": datetime.now().isoformat(),
            "last_scan_time": self.last_scan_time.isoformat() if self.last_scan_time else None,
            "active_symbol": settings.SYMBOL,
            "timeframe": settings.TIMEFRAME,
            "test_mode": settings.TEST_MODE,
            "active_position": self.current_position,
            "strategy_params": {
                "supertrend_multiplier": self.strategy.supertrend_mult,
                "supertrend_length": self.strategy.supertrend_len,
                "ema_fast": self.strategy.ema_fast,
                "ema_slow": self.strategy.ema_slow
            },
            "stats": {
                "total_trades": self.total_trades,
                "successful_trades": self.successful_trades,
                "win_rate": f"{(self.successful_trades / max(1, self.total_trades)) * 100:.1f}%"
            },
            "last_analysis": self.last_analysis_result
        }
