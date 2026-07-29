from typing import Dict, Any, Tuple, Optional
from utils.logger import logger


class RiskManager:
    """
    Risk ve Kasa Yönetimi Modülü:
    - Bakiye bazlı %1 - %2 sabit risk hesabı
    - Pozisyon büyüklüğü (Position Sizing) hesabı
    - ATR Tabanlı Takip Eden Stop-Loss ve Take-Profit seviyeleri
    """

    def __init__(
        self,
        risk_percentage: float = 0.015,
        max_leverage: int = 5,
        atr_multiplier_sl: float = 2.0,
        atr_multiplier_tp: float = 3.5
    ):
        self.risk_percentage = risk_percentage
        self.max_leverage = max_leverage
        self.atr_multiplier_sl = atr_multiplier_sl
        self.atr_multiplier_tp = atr_multiplier_tp

    def calculate_position_parameters(
        self,
        account_balance: float,
        entry_price: float,
        atr: float,
        signal_type: str
    ) -> Dict[str, Any]:
        """
        Giriş fiyatı ve ATR verisine dayanarak Stop-Loss, Take-Profit ve Pozisyon Miktarını hesaplar.
        """
        if account_balance <= 0 or entry_price <= 0 or atr <= 0:
            logger.error(f"Geçersiz risk girdisi: Bakiye={account_balance}, Fiyat={entry_price}, ATR={atr}")
            return {"valid": False}

        # 1. Riske edilecek miktar (USD/USDT cinsinden)
        risk_amount = account_balance * self.risk_percentage

        # 2. Stop-Loss ve Take-Profit Seviyeleri
        sl_distance = atr * self.atr_multiplier_sl
        tp_distance = atr * self.atr_multiplier_tp

        if signal_type == "LONG":
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
        elif signal_type == "SHORT":
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance
        else:
            return {"valid": False}

        # 3. Pozisyon Büyüklüğü (Miktar - birim cinsinden)
        # Risk = Pozisyon Miktarı * Stop Distance
        # Miktar = Risk / Stop Distance
        position_size = risk_amount / sl_distance
        
        # Toplam pozisyon değeri (Notional Value)
        notional_value = position_size * entry_price
        max_notional_value = account_balance * self.max_leverage

        if notional_value > max_notional_value:
            logger.warning(f"Maksimum kaldıraç sınırı aşıldı! Notional: {notional_value:.2f}, Max Allowed: {max_notional_value:.2f}")
            position_size = max_notional_value / entry_price
            notional_value = max_notional_value

        return {
            "valid": True,
            "signal_type": signal_type,
            "entry_price": entry_price,
            "stop_loss": round(stop_loss, 4),
            "take_profit": round(take_profit, 4),
            "position_size": round(position_size, 6),
            "risk_amount": round(risk_amount, 2),
            "notional_value": round(notional_value, 2),
            "risk_reward_ratio": round(tp_distance / sl_distance, 2)
        }

    def update_trailing_stop(
        self,
        signal_type: str,
        current_price: float,
        current_sl: float,
        atr: float
    ) -> Tuple[float, bool]:
        """
        ATR tabanlı Takip Eden Stop (Trailing Stop) güncellemesi yapar.
        Yeni SL daha avantajlı bir seviyeye ulaştıysa günceller.
        """
        if atr <= 0:
            return current_sl, False

        sl_distance = atr * self.atr_multiplier_sl
        updated = False
        new_sl = current_sl

        if signal_type == "LONG":
            calculated_sl = current_price - sl_distance
            if calculated_sl > current_sl:
                new_sl = round(calculated_sl, 4)
                updated = True
        elif signal_type == "SHORT":
            calculated_sl = current_price + sl_distance
            if calculated_sl < current_sl:
                new_sl = round(calculated_sl, 4)
                updated = True

        return new_sl, updated
