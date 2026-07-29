import numpy as np
import pandas as pd
from typing import Dict, Any, List
from strategy.indicators import TechnicalIndicators


class BacktestEngine:
    """
    Stratejinin geçmiş mumlar üzerindeki başarımını ve Sharpe Oranını hesaplayan hızlı simülatör.
    """

    @staticmethod
    def evaluate_strategy(
        df: pd.DataFrame,
        ema_fast: int = 38,
        ema_slow: int = 62,
        ema_trend: int = 200,
        supertrend_len: int = 10,
        supertrend_mult: float = 1.6
    ) -> Dict[str, Any]:
        """
        Girdi parametreleri ile simülasyon koşturur ve Sharpe Oranı, Toplam Getiri ve Win-Rate üretir.
        """
        df_calc = TechnicalIndicators.calculate_all(
            df=df,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            ema_trend=ema_trend,
            supertrend_len=supertrend_len,
            supertrend_mult=supertrend_mult
        )

        if df_calc is None or len(df_calc) < 100:
            return {"sharpe_ratio": 0.0, "total_return": 0.0, "total_trades": 0}

        returns: List[float] = []
        in_position = False
        entry_price = 0.0
        position_type = None

        for i in range(1, len(df_calc)):
            curr = df_calc.iloc[i]
            prev = df_calc.iloc[i - 1]

            close = curr['close']
            fast_ema = curr['ema_fast']
            slow_ema = curr['ema_slow']
            trend_ema = curr['ema_trend']
            st_dir = curr['supertrend_direction']
            curr_k = curr['stoch_k']
            curr_d = curr['stoch_d']

            is_bull = (fast_ema > slow_ema) and (close > trend_ema) and (st_dir == 1) and (curr_k > curr_d)
            is_bear = (fast_ema < slow_ema) and (close < trend_ema) and (st_dir == -1) and (curr_k < curr_d)

            # Pozisyondan Çıkış Koşulları
            if in_position:
                if position_type == "LONG" and (st_dir == -1 or curr_k > 80):
                    ret = (close - entry_price) / entry_price
                    returns.append(ret)
                    in_position = False
                elif position_type == "SHORT" and (st_dir == 1 or curr_k < 20):
                    ret = (entry_price - close) / entry_price
                    returns.append(ret)
                    in_position = False

            # Yeni Pozisyona Giriş Koşulları
            if not in_position:
                if is_bull:
                    in_position = True
                    entry_price = close
                    position_type = "LONG"
                elif is_bear:
                    in_position = True
                    entry_price = close
                    position_type = "SHORT"

        if not returns:
            return {"sharpe_ratio": 0.0, "total_return": 0.0, "total_trades": 0}

        returns_arr = np.array(returns)
        mean_ret = np.mean(returns_arr)
        std_ret = np.std(returns_arr)

        # Sharpe Oranı Hesabı (Risk Serbest Oran = 0 varsayıldı)
        sharpe_ratio = float((mean_ret / (std_ret + 1e-8)) * np.sqrt(252)) if std_ret > 0 else 0.0
        total_return = float(np.sum(returns_arr))
        win_rate = float(np.sum(returns_arr > 0) / len(returns_arr))

        return {
            "supertrend_mult": supertrend_mult,
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "sharpe_ratio": round(sharpe_ratio, 3),
            "total_return_pct": round(total_return * 100, 2),
            "win_rate_pct": round(win_rate * 100, 1),
            "total_trades": len(returns)
        }
