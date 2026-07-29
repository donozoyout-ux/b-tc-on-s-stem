import asyncio
from typing import Dict, Any, Optional
from config import settings
from optimizer.backtest import BacktestEngine
from core.exchange import AsyncExchangeClient
from utils.logger import logger


class AdaptiveOptimizer:
    """
    Geçmiş Mum Verilerini Çekip Parametre Kombinasyonlarını Test Eden
    ve En Yüksek Sharpe Oranına Sahip Parametreleri Bot Canlı Motoruna İleten Modül.
    """

    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.exchange = AsyncExchangeClient()
        self.is_running = False

    async def optimize(self) -> Optional[Dict[str, Any]]:
        """
        Geçmiş OHLCV verisi üzerinde SuperTrend çarpanları ve periyot kombinasyonlarını test eder.
        """
        logger.info("🧠 Adaptif Optimizasyon Modülü Çalıştırılıyor...")

        # 1. Son N mum verisini çek
        df = await self.exchange.fetch_ohlcv(
            symbol=settings.SYMBOL,
            timeframe=settings.TIMEFRAME,
            limit=settings.OPTIMIZER_LOOKBACK_BARS
        )

        if df is None or len(df) < 200:
            logger.warning("Optimizasyon için yeterli geçmiş mum verisi sağlanamadı.")
            return None

        # 2. Test edilecek parametre uzayı (Grid Search)
        supertrend_multipliers = [1.2, 1.4, 1.6, 1.8, 2.0, 2.2]
        best_result = None
        highest_sharpe = -999.0

        for mult in supertrend_multipliers:
            result = BacktestEngine.evaluate_strategy(
                df=df,
                ema_fast=settings.EMA_FAST,
                ema_slow=settings.EMA_SLOW,
                ema_trend=settings.EMA_TREND,
                supertrend_len=settings.SUPERTREND_LENGTH,
                supertrend_mult=mult
            )

            sharpe = result.get("sharpe_ratio", 0.0)
            logger.info(f"Test Parametresi (Mult={mult}): Sharpe={sharpe}, Return=%{result.get('total_return_pct')}")

            if sharpe > highest_sharpe:
                highest_sharpe = sharpe
                best_result = result

        # 3. En iyi parametreyi canlı bota uygula
        if best_result and highest_sharpe > 0:
            best_mult = best_result["supertrend_mult"]
            logger.info(f"✨ EN İYİ PARMETRE BULUNDU: SuperTrend Mult={best_mult} (Sharpe Ratio={highest_sharpe})")
            await self.bot.update_strategy_params(supertrend_mult=best_mult)
            return best_result

        logger.info("Optimizasyon tamamlandı. Mevcut parametreler korundu.")
        return None

    async def run_periodic_optimization(self) -> None:
        """
        Her OPTIMIZER_INTERVAL_HOURS saatte bir arka planda otomatik optimizasyon çalıştırır.
        """
        self.is_running = True
        interval_seconds = settings.OPTIMIZER_INTERVAL_HOURS * 3600

        while self.is_running:
            try:
                await self.optimize()
            except Exception as e:
                logger.error(f"Adaptif optimizasyon döngüsünde hata: {str(e)}")

            await asyncio.sleep(interval_seconds)
