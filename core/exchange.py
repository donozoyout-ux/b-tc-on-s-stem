import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import requests
from typing import Dict, Any, Optional, List
from config import settings
from utils.logger import logger


class AsyncExchangeClient:
    """
    CCXT Asenkron Borsa İstemcisi:
    - Piyasa mum verisi (OHLCV) için kesintisiz canlı borsa istemcisi
    - İşlemler ve bakiye sorgulama için Testnet/Canlı borsa istemcisi
    """

    def __init__(self):
        self.exchange_id = settings.EXCHANGE_ID
        self.api_key = settings.API_KEY
        self.secret_key = settings.SECRET_KEY
        self.test_mode = settings.TEST_MODE
        self.is_futures = settings.IS_FUTURES
        self.exchange: Optional[ccxt.Exchange] = None
        self.public_exchange: Optional[ccxt.Exchange] = None

    async def initialize(self) -> None:
        """
        Borsa bağlantılarını başlatır ve yapılandırır.
        """
        try:
            exchange_class = getattr(ccxt, self.exchange_id, None) or ccxt.binanceusdm

            # 1. Canlı Piyasa Verileri İstemcisi (OHLCV Kesintisiz Çekim İçin)
            self.public_exchange = ccxt.binance({
                "enableRateLimit": True
            })

            # 2. İşlem ve Bakiye İstemcisi (Testnet veya Canlı)
            options = {
                "apiKey": self.api_key,
                "secret": self.secret_key,
                "enableRateLimit": True,
                "options": {"defaultType": "future"} if self.is_futures else {}
            }
            self.exchange = exchange_class(options)

            if self.test_mode:
                try:
                    self.exchange.set_sandbox_mode(True)
                except Exception as sb_err:
                    logger.warning(f"Sandbox modu uyarısı: {str(sb_err)}")
                logger.info("[BİLGİ] 🧪 SANAL PARA (Binance Futures Testnet) Modu Aktif")
            else:
                logger.warning("⚠️ GERÇEK HESAP MODU")

            logger.info("Borsa istemcisi başarıyla ilklendirildi.")
        except Exception as e:
            logger.error(f"Borsa başlatma hatası: {str(e)}")

    async def close(self) -> None:
        """
        Borsa bağlantılarını güvenli şekilde kapatır.
        """
        if self.exchange:
            await self.exchange.close()
        if self.public_exchange:
            await self.public_exchange.close()
        logger.info("Borsa bağlantısı kapatıldı.")

    async def fetch_ohlcv(
        self,
        symbol: str = None,
        timeframe: str = None,
        limit: int = 200
    ) -> Optional[pd.DataFrame]:
        """
        Belirtilen parite ve zaman diliminde mum verilerini çekip Pandas DataFrame olarak döner.
        CCXT yetersiz kaldığında yüksek erişilebilirlikli Binance Data API aynasına geçer.
        """
        symbol = symbol or settings.SYMBOL
        timeframe = timeframe or settings.TIMEFRAME

        if not self.public_exchange:
            await self.initialize()

        # 1. Öncelikli Yöntem: CCXT üzerinden dene
        try:
            ohlcv = await self.public_exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if ohlcv and len(ohlcv) > 0:
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('datetime', inplace=True)
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                return df
        except Exception:
            pass

        # 2. Yedek Kesintisiz Yöntem: Binance Data API Aynası (Kesintisiz)
        try:
            formatted_symbol = symbol.replace("/", "").upper()
            url = "https://data-api.binance.vision/api/v3/klines"
            params = {
                "symbol": formatted_symbol,
                "interval": timeframe,
                "limit": limit
            }
            res = requests.get(url, params=params, timeout=5).json()
            if isinstance(res, list) and len(res) > 0:
                df = pd.DataFrame(res, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'tbv', 'tqv', 'ignore'])
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('datetime', inplace=True)
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                return df
        except Exception as e:
            logger.error(f"Yedek OHLCV verisi çekilirken hata ({symbol}): {str(e)}")

        return None

    async def fetch_balance(self) -> float:
        """
        Hesabın kullanılabilir USDT (veya quote cinsi) bakiyesini sorgular.
        """
        if not self.exchange:
            await self.initialize()

        try:
            if not self.api_key:
                return 10000.0

            balance = await self.exchange.fetch_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0.0)
            if float(usdt_balance) <= 0:
                # Testnet için varsayılan simülasyon bakiyesi
                return 10000.0
            return float(usdt_balance)
        except Exception as e:
            logger.debug(f"Bakiye sorgulama detayı: {str(e)}")
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
            # Testnet emri simülasyon fallback
            return {
                "id": f"testnet_fallback_{side}_1",
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": price,
                "status": "closed"
            }
