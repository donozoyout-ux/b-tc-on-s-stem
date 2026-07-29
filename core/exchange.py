import asyncio
import ccxt.async_support as ccxt
import pandas as pd
from typing import Dict, Any, Optional, List
from config import settings
from utils.logger import logger


class AsyncExchangeClient:
    """
    CCXT Asenkron Borsa İstemcisi.
    Borsa bağlantısı, mum (OHLCV) verisi çekme, bakiye sorgulama ve emir iletimini yönetir.
    """

    def __init__(self):
        self.exchange_id = settings.EXCHANGE_ID
        self.api_key = settings.API_KEY
        self.secret_key = settings.SECRET_KEY
        self.test_mode = settings.TEST_MODE
        self.is_futures = settings.IS_FUTURES
        self.exchange: Optional[ccxt.Exchange] = None

    async def initialize(self) -> None:
        """
        Borsa bağlantısını başlatır ve yapılandırır.
        """
        try:
            exchange_class = getattr(ccxt, self.exchange_id, None)
            if not exchange_class:
                raise ValueError(f"Desteklenmeyen borsa: {self.exchange_id}")

            options = {
                "apiKey": self.api_key,
                "secret": self.secret_key,
                "enableRateLimit": True,
                "options": {}
            }

            if self.is_futures:
                options["options"]["defaultType"] = "future"

            self.exchange = exchange_class(options)

            if self.test_mode:
                self.exchange.set_sandbox_mode(True)
                logger.info("[BİLGİ] 🧪 SANAL PARA (Binance Futures Testnet) Modu Aktif")
            else:
                logger.warning("⚠️ GERÇEK HESAP MODU")

            await self.exchange.load_markets()
            logger.info("Borsa piyasa verileri başarıyla yüklendi.")
        except Exception as e:
            logger.error(f"Borsa başlatma hatası: {str(e)}")

    async def close(self) -> None:
        """
        Borsa bağlantısını güvenli şekilde kapatır.
        """
        if self.exchange:
            await self.exchange.close()
            logger.info("Borsa bağlantısı kapatıldı.")

    async def fetch_ohlcv(
        self,
        symbol: str = None,
        timeframe: str = None,
        limit: int = 200
    ) -> Optional[pd.DataFrame]:
        """
        Belirtilen parite ve zaman diliminde mum verilerini çekip Pandas DataFrame olarak döner.
        """
        symbol = symbol or settings.SYMBOL
        timeframe = timeframe or settings.TIMEFRAME

        if not self.exchange:
            await self.initialize()

        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not ohlcv:
                logger.warning(f"{symbol} için OHLCV verisi çekilemedi.")
                return None

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('datetime', inplace=True)
            
            # Numeric dönüşümleri
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)

            return df
        except Exception as e:
            logger.error(f"OHLCV verisi çekilirken hata oluştu ({symbol}): {str(e)}")
            return None

    async def fetch_balance(self) -> float:
        """
        Hesabın kullanılabilir USDT (veya quote cinsi) bakiyesini sorgular.
        """
        if not self.exchange:
            await self.initialize()

        try:
            if not self.api_key:
                # API Key girilmediyse simülasyon bakiyesi dön
                logger.warning("API Key bulunamadı. Simülasyon bakiyesi (10,000 USDT) kullanılıyor.")
                return 10000.0

            balance = await self.exchange.fetch_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0.0)
            return float(usdt_balance)
        except Exception as e:
            logger.error(f"Bakiye sorgulama hatası: {str(e)}")
            return 10000.0  # Fallback varsayılan simülasyon bakiyesi

    async def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Borsada piyasa veya limit emir oluşturur.
        """
        if not self.exchange:
            await self.initialize()

        params = params or {}
        try:
            if not self.api_key:
                logger.info(f"[SİMÜLASYON EMİR] {side.upper()} {amount} {symbol} @ {price or 'MARKET'}")
                return {
                    "id": "simulated_order_123",
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "price": price,
                    "status": "closed"
                }

            order = await self.exchange.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=amount,
                price=price,
                params=params
            )
            logger.info(f"Emir başarıyla oluşturuldu: ID={order.get('id')}, Side={side}, Amount={amount}")
            return order
        except Exception as e:
            logger.error(f"Emir oluşturma hatası ({side} {amount} {symbol}): {str(e)}")
            return None
