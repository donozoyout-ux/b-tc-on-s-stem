import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from config import settings
from core.bot import TradingBot
from optimizer.adaptive import AdaptiveOptimizer
from utils.logger import logger

# Global Bot ve Optimizer İstemcileri
bot = TradingBot()
optimizer = AdaptiveOptimizer(bot_instance=bot)
background_tasks_set = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Yaşam Döngüsü (Lifespan Context Manager):
    Sunucu başlatıldığında trading motorunu ve adaptif optimizasyonu arka planda başlatır.
    Kapanışta bağlantıları güvenli bir şekilde kapatır.
    """
    logger.info("🚀 FastAPI Sunucusu Başlatılıyor... 7/24 Trading ve Health-Check Modu Aktif.")

    # 1. Trading motorunu arka plan asyncio task olarak başlat
    bot_task = asyncio.create_task(bot.run_loop())
    background_tasks_set.add(bot_task)
    bot_task.add_done_callback(background_tasks_set.discard)

    # 2. Adaptif optimizasyon modülü aktifse başlat
    if settings.OPTIMIZER_ENABLED:
        opt_task = asyncio.create_task(optimizer.run_periodic_optimization())
        background_tasks_set.add(opt_task)
        opt_task.add_done_callback(background_tasks_set.discard)
        logger.info("🧠 Adaptif Optimizasyon Arka Plan Döngüsü Başlatıldı.")

    yield

    # Sunucu Kapanış İşlemleri
    logger.info("🛑 FastAPI Kapanıyor... Arka plan işlemleri durduruluyor.")
    await bot.stop()
    for task in background_tasks_set:
        task.cancel()


# FastAPI Uygulama Tanımı
app = FastAPI(
    title=settings.APP_NAME,
    description="7/24 Kesintisiz Uyanık Kalan, Adaptif Kripto Algoritmik Ticaret Botu (FastAPI + CCXT + Pandas-TA)",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """
    Ana endpoint: Servis bilgisi ve hızlı durum sunar.
    """
    return {
        "app": settings.APP_NAME,
        "status": "running",
        "symbol": settings.SYMBOL,
        "timeframe": settings.TIMEFRAME,
        "health_check_url": "/health",
        "docs_url": "/docs"
    }


@app.get("/health")
async def health_check():
    """
    UptimeRobot, Render ve Koyeb servislerinin 7/24 servisi uyanık tutması için çağırdığı Health Endpoint'i.
    HTTP 200 OK dönerek uygulamanın aktif ve uyanık kalmasını sağlar.
    """
    status_data = bot.get_status()
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "message": "Bot 7/24 aktif ve tarama yapıyor.",
            "bot_status": status_data
        }
    )


@app.get("/status")
async def get_bot_status():
    """
    Botun anlık durumunu, aktif pozisyonunu ve istatistiklerini veren detaylı endpoint.
    """
    return bot.get_status()


@app.post("/optimize")
async def trigger_manual_optimization(background_tasks: BackgroundTasks):
    """
    Manuel olarak adaptif optimizasyonu tetikleyen endpoint.
    Geçmiş mum verilerinde en yüksek Sharpe oranına sahip parametreleri bulur.
    """
    background_tasks.add_task(optimizer.optimize)
    return {
        "message": "Adaptif optimizasyon arka planda başlatıldı.",
        "status": "processing"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)
