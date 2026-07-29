import asyncio
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from config import settings
from core.bot import TradingBot
from optimizer.adaptive import AdaptiveOptimizer
from utils.logger import logger

# Global Bot ve Optimizer İstemcileri
bot = TradingBot()
optimizer = AdaptiveOptimizer(bot_instance=bot)
background_tasks_set = set()


class SettingsUpdateModel(BaseModel):
    symbol: Optional[str] = Field(None, description="Parite (örn: BTC/USDT)")
    timeframe: Optional[str] = Field(None, description="Zaman dilimi (örn: 15m)")
    risk_percentage: Optional[float] = Field(None, description="İşlem başına risk (örn: 0.015)")
    max_leverage: Optional[int] = Field(None, description="Maksimum kaldıraç")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Yaşam Döngüsü (Lifespan Context Manager):
    Sunucu başlatıldığında trading motorunu ve adaptif optimizasyonu arka planda başlatır.
    Kapanışta bağlantıları güvenli bir şekilde kapatır.
    """
    logger.info("🚀 FastAPI Sunucusu Başlatılıyor... 7/24 Trading, Dashboard ve Health-Check Modu Aktif.")

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
    description="7/24 Kesintisiz Uyanık Kalan, Web Dashboard Destekli Adaptif Kripto Algoritmik Ticaret Botu",
    version="1.0.0",
    lifespan=lifespan
)

# Statik Dosyaları Bağlama
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """
    Ana endpoint: Web Dashboard arayüzünü (static/index.html) döndürür.
    """
    return FileResponse("static/index.html")


@app.get("/health")
async def health_check():
    """
    UptimeRobot, Render ve Koyeb servislerinin 7/24 servisi uyanık tutması için çağırdığı Health Endpoint'i.
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


# --- REST API ENDPOINT'LERİ (DASHBOARD VE DİŞ İSTEMCİLER İÇİN) ---

@app.get("/api/status")
async def api_status():
    """
    Dashboard için botun anlık durumu, bakiyesi, son fiyatı, aktif parametreleri ve indikatör değerlerini döner.
    """
    return bot.get_api_status()


@app.get("/api/trades")
async def api_trades():
    """
    Botun ürettiği son 20 sinyal/işlem geçmişini ve canlı terminal loglarını döner.
    """
    return {
        "trades": bot.trade_history[:20],
        "logs": bot.logs
    }


@app.post("/api/bot/start")
async def start_bot():
    """
    Arka plandaki bot döngüsünü başlatır.
    """
    if not bot.is_running:
        bot_task = asyncio.create_task(bot.run_loop())
        background_tasks_set.add(bot_task)
        bot_task.add_done_callback(background_tasks_set.discard)
        bot.add_log("INFO", "Bot manuel olarak başlatıldı.")
        return {"status": "success", "message": "Bot başlatıldı."}
    return {"status": "already_running", "message": "Bot zaten çalışıyor."}


@app.post("/api/bot/stop")
async def stop_bot():
    """
    Arka plandaki bot döngüsünü durdurur.
    """
    if bot.is_running:
        await bot.stop()
        bot.add_log("WARN", "Bot manuel olarak durduruldu.")
        return {"status": "success", "message": "Bot durduruldu."}
    return {"status": "already_stopped", "message": "Bot zaten durmuş durumda."}


@app.post("/api/settings")
async def update_settings(payload: SettingsUpdateModel):
    """
    Risk, kaldıraç, parite ve timeframe parametrelerini canlı olarak günceller.
    """
    updated = bot.update_settings(
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        risk_percentage=payload.risk_percentage,
        max_leverage=payload.max_leverage
    )
    return {
        "status": "success",
        "message": "Ayarlar başarıyla güncellendi.",
        "settings": updated
    }


@app.post("/optimize")
async def trigger_manual_optimization(background_tasks: BackgroundTasks):
    """
    Manuel olarak adaptif optimizasyonu tetikleyen endpoint.
    """
    background_tasks.add_task(optimizer.optimize)
    return {
        "message": "Adaptif optimizasyon arka planda başlatıldı.",
        "status": "processing"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)
