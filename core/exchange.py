import asyncio
import aiohttp
from aiohttp.resolver import ThreadedResolver
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
    - İşlemler ve bakiye sorgulama için Demo Trading / Canlı borsa istemcisi
    - ThreadedResolver ile DNS çözümleme (aiodns sorunlarını bypass eder)
    - Binance Demo Trading (enable_demo_trading) desteği
    """

    def __init__(self):
        self.exchange_id = settings.EXCHANGE_ID
        self.api_key = settings.API_KEY
        self.secret_key = settings.SECRET_KEY
        self.test_mode = settings.TEST_MODE
        self.is_futures = settings.IS_FUTURES
        self.exchange: Optional[ccxt.Exchange] = None
        self.public_exchange: Optional[ccxt.Exchange] = None
        self._session: Optional[aiohttp.ClientSession] = None

    async def initialize(self) -> None:
        """
        Borsa bağlantılarını başlatır ve yapılandırır.
        Demo Trading modu (TEST_MODE=True) veya Canlı Hesap modunu kullanır.
        """
        try:
            exchange_class = getattr(ccxt, self.exchange_id, None) or ccxt.binanceusdm

            # ThreadedResolver ile DNS çözümleme (aiodns bypass)
            connector = aiohttp.TCPConnector(resolver=ThreadedResolver())
            self._session = aiohttp.ClientSession(connector=connector)

            # 1. Canlı Piyasa Verileri İstemcisi (OHLCV Kesintisiz Çekim İçin)
            self.public_exchange = ccxt.binance({
                "enableRateLimit": True,
                "session": self._session
            })

            # 2. İşlem ve Bakiye İstemcisi (Demo Trading veya Canlı)
            options = {
                "apiKey": self.api_key,
                "secret": self.secret_key,
                "enableRateLimit": True,
                "session": self._session,
                "options": {"defaultType": "future"} if self.is_futures else {}
            }
            self.exchange = exchange_class(options)

            if self.test_mode:
                # Binance Demo Trading API (eski sandbox yerine)
                if hasattr(self.exchange, 'enable_demo_trading'):
                    self.exchange.enable_demo_trading(True)
                    logger.info("[BILGI] DEMO TRADING Modu Aktif (Sanal Para / Gercek Altyapi)")
                else:
                    logger.warning("CCXT versiyonunda enable_demo_trading destegi yok, sandbox deneniyor...")
                    try:
                        self.exchange.set_sandbox_mode(True)
                    except Exception:
                        pass
                    logger.info("[BILGI] Sandbox/Testnet Modu Aktif")
            else:
                logger.warning("GERCEK HESAP MODU - Dikkatli olun!")

            # Demo Trading exchange icin piyasa yukle
            await self.exchange.load_markets()
            logger.info(f"Borsa istemcisi basariyla ilklendirildi. Piyasa sayisi: {len(self.exchange.markets)}")
        except Exception as e:
            logger.error(f"Borsa baslatma hatasi: {str(e)}")

    async def close(self) -> None:
        """
        Borsa bağlantılarını güvenli şekilde kapatır.
        """
        if self.exchange:
            await self.exchange.close()
        if self.public_exchange:
            await self.public_exchange.close()
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("Borsa baglantisi kapatildi.")

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

        # 1. Oncelikli Yontem: CCXT uzerinden dene
        try:
            ohlcv = await self.public_exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if ohlcv and len(ohlcv) > 0:
                return self._ohlcv_to_dataframe(ohlcv)
        except Exception:
            pass

        # 2. Yedek Kesintisiz Yontem: Binance Data API Aynasi
        try:
            formatted_symbol = symbol.replace("/", "").upper()
            url = "https://data-api.binance.vision/api/v3/klines"
            params = {
                "symbol": formatted_symbol,
                "interval": timeframe,
                "limit": limit
            }
            res = requests.get(url, params=params, timeout=10).json()
            if isinstance(res, list) and len(res) > 0:
                ohlcv = [[c[0], float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])] for c in res]
                return self._ohlcv_to_dataframe(ohlcv)
        except Exception as e:
            logger.error(f"Yedek OHLCV verisi cekilirken hata ({symbol}): {str(e)}")

        return None

    def _ohlcv_to_dataframe(self, ohlcv: list) -> pd.DataFrame:
        """
        OHLCV ham verisini Pandas DataFrame'e donusturur.
        """
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('datetime', inplace=True)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df

    async def fetch_balance(self) -> float:
        """
        Hesabin kullanilabilir USDT bakiyesini sorgular.
        """
        if not self.exchange:
            await self.initialize()

        try:
            if not self.api_key:
                return 10000.0

            balance = await self.exchange.fetch_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0.0)
            if float(usdt_balance) <= 0:
                return 10000.0
            return float(usdt_balance)
        except Exception as e:
            logger.debug(f"Bakiye sorgulama detayi: {str(e)}")
            return 10000.0

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
        Borsada piyasa veya limit emir olusturur.
        Demo Trading modunda Binance Demo API'sine gercek emir gonderir (sanal para ile).
        """
        if not self.exchange:
            await self.initialize()

        params = params or {}
        try:
            if not self.api_key:
                logger.info(f"[SIMULASYON EMIR] {side.upper()} {amount} {symbol} @ {price or 'MARKET'}")
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
            logger.info(f"Emir basariyla olusturuldu: ID={order.get('id')}, Side={side}, Amount={amount}")
            return order
        except Exception as e:
            logger.error(f"Emir olusturma hatasi ({side} {amount} {symbol}): {str(e)}")
            return None
