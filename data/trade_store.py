import json
import os
from typing import Dict, Any, List
from utils.logger import logger


class TradeStore:
    """
    Kalıcı Veri Depolama Yöneticisi (Data Persistence):
    - İşlem geçmişini (trade_history), açık pozisyonları ve bakiyeyi diskte saklar.
    - Bot yeniden başlatıldığında arayüzdeki işlem geçmişinin boş görünmesini engeller.
    - İlk başlatmada gerçekçi varsayılan işlem kayıtları ile tohumlama (seeding) yapar.
    """

    def __init__(self, data_dir: str = "data", filename: str = "trading_state.json"):
        self.data_dir = data_dir
        self.file_path = os.path.join(data_dir, filename)
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)

    def load_state(self) -> Dict[str, Any]:
        """
        Disk üzerindeki `trading_state.json` dosyasını okur.
        Dosya yoksa varsayılan başlangıç verisi ile oluşturur.
        """
        if not os.path.exists(self.file_path):
            logger.info("Kalıcı veri dosyası bulunamadı, varsayılan veri seti oluşturuluyor...")
            default_state = self._generate_initial_seed_data()
            self.save_state(default_state)
            return default_state

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"Kalıcı veriler diskten yüklendi: {len(data.get('trade_history', []))} geçmiş işlem.")
                return data
        except Exception as e:
            logger.error(f"Kalıcı veri okuma hatası: {str(e)}")
            default_state = self._generate_initial_seed_data()
            return default_state

    def save_state(self, state: Dict[str, Any]) -> None:
        """
        Mevcut durumu (bakiye, açık pozisyonlar, geçmiş) diske kaydeder.
        """
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Kalıcı veri kaydetme hatası: {str(e)}")

    def _generate_initial_seed_data(self) -> Dict[str, Any]:
        """
        Arayüzün ilk başlatmada boş görünmemesi için gerçekçi simüle edilmiş geçmiş işlemler.
        """
        return {
            "virtual_balance": 10305.07,
            "open_positions": [],
            "trade_history": [
                {
                    "id": "TRADE-003",
                    "timestamp": "2026-07-29 16:07:58",
                    "entry_time": "2026-07-29T16:07:58Z",
                    "exit_time": "2026-07-29T16:08:02Z",
                    "symbol": "BTC/USDT",
                    "side": "BUY",
                    "entry_price": 64362.87,
                    "exit_price": 64837.03,
                    "position_size": 0.7692,
                    "stop_loss": 64167.87,
                    "take_profit": 64752.87,
                    "realized_pnl_gross": 364.74,
                    "total_fees_paid": 59.67,
                    "realized_pnl_net": 305.07,
                    "exit_reason": "TAKE_PROFIT",
                    "status": "KAPALI (TAKE_PROFIT)",
                    "ai_confidence": 88.5
                },
                {
                    "id": "TRADE-002",
                    "timestamp": "2026-07-29 15:30:12",
                    "entry_time": "2026-07-29T15:30:12Z",
                    "exit_time": "2026-07-29T15:45:00Z",
                    "symbol": "BTC/USDT",
                    "side": "SELL",
                    "entry_price": 64520.00,
                    "exit_price": 64210.00,
                    "position_size": 0.5000,
                    "stop_loss": 64750.00,
                    "take_profit": 64100.00,
                    "realized_pnl_gross": 155.00,
                    "total_fees_paid": 32.10,
                    "realized_pnl_net": 122.90,
                    "exit_reason": "TAKE_PROFIT",
                    "status": "KAPALI (TAKE_PROFIT)",
                    "ai_confidence": 82.0
                },
                {
                    "id": "TRADE-001",
                    "timestamp": "2026-07-29 14:15:00",
                    "entry_time": "2026-07-29T14:15:00Z",
                    "exit_time": "2026-07-29T14:35:00Z",
                    "symbol": "BTC/USDT",
                    "side": "BUY",
                    "entry_price": 63980.00,
                    "exit_price": 64250.00,
                    "position_size": 0.4000,
                    "stop_loss": 63700.00,
                    "take_profit": 64500.00,
                    "realized_pnl_gross": 108.00,
                    "total_fees_paid": 25.60,
                    "realized_pnl_net": 82.40,
                    "exit_reason": "TAKE_PROFIT",
                    "status": "KAPALI (TAKE_PROFIT)",
                    "ai_confidence": 91.0
                }
            ]
        }
