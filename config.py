import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, AliasChoices


class Settings(BaseSettings):
    """
    Kripto Algo-Trading Bot Konfigürasyon Ayarları.
    Çevre değişkenlerinden (.env) veya varsayılan değerlerden okunur.
    """

    # --- Uygulama Ayarları ---
    APP_NAME: str = "Kripton Trading Bot"
    DEBUG: bool = False
    PORT: int = 8000

    # --- Borsa Ayarları (CCXT) ---
    EXCHANGE_ID: str = Field(default="binanceusdm", description="Desteklenen CCXT borsası (binanceusdm, binance, bybit, okx)")
    API_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("API_KEY", "EXCHANGE_API_KEY"),
        description="Borsa API Key"
    )
    SECRET_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("SECRET_KEY", "EXCHANGE_SECRET_KEY"),
        description="Borsa API Secret"
    )
    TEST_MODE: bool = Field(
        default=True,
        description="True ise Testnet / Demo hesabı kullanılır (Varsayılan: True)"
    )
    IS_FUTURES: bool = Field(default=True, description="True ise Vadeli İşlemler (Futures), False ise Spot")

    # --- Telegram Bildirim Ayarları ---
    TELEGRAM_BOT_TOKEN: str = Field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""),
        description="Telegram Bot API Token"
    )
    TELEGRAM_CHAT_ID: str = Field(
        default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""),
        description="Telegram Chat ID"
    )

    # --- İşlem ve Parite Ayarları ---
    SYMBOL: str = Field(default="BTC/USDT", description="İşlem yapılacak sembol (örn: BTC/USDT)")
    TIMEFRAME: str = Field(default="5m", description="Mum zaman dilimi (1m, 5m, 15m, 1h, 4h)")
    POLL_INTERVAL_SECONDS: int = Field(default=60, description="Döngü tarama sıklığı (saniye)")

    # --- Strateji Parametreleri (Kripton Gezegeni Yöntemi) ---
    EMA_FAST: int = Field(default=38, description="Hızlı EMA periyodu")
    EMA_SLOW: int = Field(default=62, description="Yavaş EMA periyodu")
    EMA_TREND: int = Field(default=200, description="Ana Trend EMA periyodu")
    
    SUPERTREND_LENGTH: int = Field(default=10, description="SuperTrend periyodu")
    SUPERTREND_MULTIPLIER: float = Field(default=1.6, description="SuperTrend çarpanı")
    
    STOCH_RSI_K: int = Field(default=3, description="Stoch RSI %K düzeltme")
    STOCH_RSI_D: int = Field(default=3, description="Stoch RSI %D düzeltme")
    STOCH_RSI_RSI_LEN: int = Field(default=8, description="Stoch RSI - RSI periyodu")
    STOCH_RSI_STOCH_LEN: int = Field(default=10, description="Stoch RSI periyodu")
    STOCH_RSI_OVERSOLD: float = Field(default=50.0, description="Pullback Long tetiklenme eşiği (Stoch_K < 50)")
    STOCH_RSI_OVERBOUGHT: float = Field(default=50.0, description="Pullback Short tetiklenme eşiği (Stoch_K > 50)")

    # --- Risk ve Kasa Yönetimi ---
    RISK_PERCENTAGE: float = Field(default=0.02, description="İşlem başına maksimum bakiye riski (0.02 = %2.0)")
    MAX_LEVERAGE: int = Field(default=5, description="Kullanılacak kaldıraç oranı")
    ATR_PERIOD: int = Field(default=14, description="ATR periyodu")
    ATR_MULTIPLIER_SL: float = Field(default=1.5, description="ATR Stop-Loss çarpanı (1.5 * ATR)")
    ATR_MULTIPLIER_TP: float = Field(default=3.0, description="ATR Take-Profit çarpanı (3.0 * ATR - 1:2 R/R)")

    # --- Adaptif Optimizasyon Modülü ---
    OPTIMIZER_ENABLED: bool = Field(default=True, description="Adaptif arka plan optimizasyonu aktif mi?")
    OPTIMIZER_INTERVAL_HOURS: int = Field(default=24, description="Optimizasyon tarama sıklığı (saat)")
    OPTIMIZER_LOOKBACK_BARS: int = Field(default=1000, description="Backtest için çekilecek mum sayısı")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Global ayarlar nesnesi
settings = Settings()
