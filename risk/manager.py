from typing import Dict, Any, Tuple, Optional
from utils.logger import logger


class RiskManager:
    """
    Gerçekçi Risk, Kasa ve Paper Trading Simülasyon Yönetimi:
    - Bakiye bazlı %1 - %2 sabit risk hesabı (Pozisyon büyüklüğü)
    - ATR Tabanlı Takip Eden Stop-Loss ve Take-Profit seviyeleri
    - Gerçekçi komisyon (%0.05 Taker giriş/çıkış) ve kayma (%0.02 Slippage) hesabı
    - Net PnL formülü: Net PnL = Brüt PnL - (Giriş Komisyonu + Çıkış Komisyonu + Kayma Maliyeti)
    """

    def __init__(
        self,
        risk_percentage: float = 0.015,
        max_leverage: int = 5,
        atr_multiplier_sl: float = 1.5,
        atr_multiplier_tp: float = 3.0,
        taker_fee_rate: float = 0.0005,  # %0.05
        slippage_rate: float = 0.0002    # %0.02
    ):
        self.risk_percentage = risk_percentage
        self.max_leverage = max_leverage
        self.atr_multiplier_sl = atr_multiplier_sl
        self.atr_multiplier_tp = atr_multiplier_tp
        self.taker_fee_rate = taker_fee_rate
        self.slippage_rate = slippage_rate

    def calculate_position_parameters(
        self,
        account_balance: float,
        entry_price: float,
        atr: float,
        signal_type: str
    ) -> Dict[str, Any]:
        """
        Giriş fiyatı ve ATR verisine dayanarak Stop-Loss, Take-Profit ve Pozisyon Miktarını hesaplar.
        Kayma (Slippage) etkisi giriş fiyatına yansıtılır.
        """
        if account_balance <= 0 or entry_price <= 0 or atr <= 0:
            logger.error(f"Geçersiz risk girdisi: Bakiye={account_balance}, Fiyat={entry_price}, ATR={atr}")
            return {"valid": False}

        # Kayma yansıtılmış gerçekleşme fiyatı (Slippage)
        if signal_type == "LONG":
            exec_entry_price = entry_price * (1 + self.slippage_rate)
        else:
            exec_entry_price = entry_price * (1 - self.slippage_rate)

        # Riske edilecek miktar (USD/USDT cinsinden - maks %2)
        risk_amount = account_balance * self.risk_percentage

        # Stop-Loss ve Take-Profit Seviyeleri
        sl_distance = atr * self.atr_multiplier_sl
        tp_distance = atr * self.atr_multiplier_tp

        if signal_type == "LONG":
            stop_loss = exec_entry_price - sl_distance
            take_profit = exec_entry_price + tp_distance
        elif signal_type == "SHORT":
            stop_loss = exec_entry_price + sl_distance
            take_profit = exec_entry_price - tp_distance
        else:
            return {"valid": False}

        # Pozisyon Büyüklüğü (Miktar - birim cinsinden)
        position_size = risk_amount / sl_distance
        
        # Toplam pozisyon değeri (Notional Value)
        notional_value = position_size * exec_entry_price
        max_notional_value = account_balance * self.max_leverage

        if notional_value > max_notional_value:
            logger.warning(f"Maksimum kaldıraç sınırı aşıldı! Notional: {notional_value:.2f}, Max: {max_notional_value:.2f}")
            position_size = max_notional_value / exec_entry_price
            notional_value = max_notional_value

        # Giriş Komisyonu
        entry_fee = notional_value * self.taker_fee_rate

        return {
            "valid": True,
            "signal_type": signal_type,
            "raw_entry_price": round(entry_price, 2),
            "exec_entry_price": round(exec_entry_price, 2),
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "position_size": round(position_size, 4),
            "notional_value": round(notional_value, 2),
            "entry_fee": round(entry_fee, 4),
            "risk_amount": round(risk_amount, 2),
            "risk_reward_ratio": round(tp_distance / sl_distance, 2)
        }

    def calculate_pnl(
        self,
        signal_type: str,
        entry_price: float,
        exit_price: float,
        position_size: float,
        leverage: int = 5
    ) -> Dict[str, Any]:
        """
        Gerçekleşen veya anlık PnL durumunu komisyon (%0.05 giriş + %0.05 çıkış) ve kayma (%0.02) düşerek hesaplar.
        Net PnL = Brüt PnL - (Giriş Komisyonu + Çıkış Komisyonu + Kayma Maliyeti)
        """
        notional_entry = position_size * entry_price
        
        # Çıkış fiyatına kayma uygula
        if signal_type == "LONG":
            exec_exit_price = exit_price * (1 - self.slippage_rate)
            gross_pnl = (exec_exit_price - entry_price) * position_size
        else:
            exec_exit_price = exit_price * (1 + self.slippage_rate)
            gross_pnl = (entry_price - exec_exit_price) * position_size

        notional_exit = position_size * exec_exit_price
        
        # Komisyonlar ve Kayma Maliyetleri
        entry_fee = notional_entry * self.taker_fee_rate
        exit_fee = notional_exit * self.taker_fee_rate
        slippage_cost = (abs(exit_price - exec_exit_price) + abs(entry_price - entry_price)) * position_size
        total_fees = entry_fee + exit_fee + slippage_cost

        net_pnl = gross_pnl - total_fees

        return {
            "gross_pnl": round(gross_pnl, 2),
            "entry_fee": round(entry_fee, 2),
            "exit_fee": round(exit_fee, 2),
            "slippage_cost": round(slippage_cost, 2),
            "total_fees": round(total_fees, 2),
            "net_pnl": round(net_pnl, 2),
            "exec_exit_price": round(exec_exit_price, 2)
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
        """
        if atr <= 0:
            return current_sl, False

        sl_distance = atr * self.atr_multiplier_sl
        updated = False
        new_sl = current_sl

        if signal_type == "LONG":
            calculated_sl = current_price - sl_distance
            if calculated_sl > current_sl:
                new_sl = round(calculated_sl, 2)
                updated = True
        elif signal_type == "SHORT":
            calculated_sl = current_price + sl_distance
            if calculated_sl < current_sl:
                new_sl = round(calculated_sl, 2)
                updated = True

        return new_sl, updated
