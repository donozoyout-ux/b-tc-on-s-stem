import os
import sys
import time
import json
import requests
import numpy as np
import pandas as pd
from datetime import datetime

# Windows konsolunda emoji/Unicode desteği
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# .env dosyasından yükle (python-dotenv varsa kullan)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- KRIPTON ALGO-TRADER KONFİGÜRASYONU ---
SYMBOL = "BTCUSDT"
TIMEFRAME = "5m"
INTERVAL_SECONDS = 300  # 5 Dakika
STATE_FILE = "state.json"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Parametreler
LEVERAGE = 5
POS_SIZE_RATIO = 0.20  # Kasanın %20'si
TAKER_FEE_PCT = 0.05   # Giriş %0.05 + Çıkış %0.05 = %0.10 Toplam
SLIPPAGE_PCT = 0.02    # Kayma %0.02
TOTAL_COST_PCT = 0.10  # Komisyon + Kayma %0.10

TP_PCT = 0.012  # +%1.20 Brüt Take Profit (~+%1.00 Net)
SL_PCT = 0.006  # -%0.60 Brüt Stop Loss

DAILY_TARGET_PCT = 1.0  # Günlük Net +%1.0 Kâr Hedefi
DAILY_STOP_PCT = -2.0   # Günlük Max -%2.0 Kayıp Eşiği


def load_state() -> dict:
    """state.json dosyasından güncel durumu okur ve gün değişimini kontrol eder."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}
    else:
        state = {}

    # Varsayılan Yapı
    state.setdefault("initial_balance", 10000.0)
    state.setdefault("current_balance", 10000.0)
    state.setdefault("today_date", today_str)
    state.setdefault("today_pnl_usdt", 0.0)
    state.setdefault("today_pnl_pct", 0.0)
    state.setdefault("active_position", None)
    state.setdefault("trade_history", [])

    # Gün Değişimi Kontrolü (Midnight Reset)
    if state["today_date"] != today_str:
        state["today_date"] = today_str
        state["today_pnl_usdt"] = 0.0
        state["today_pnl_pct"] = 0.0
        print(f"🔄 YENİ GÜN SIFIRLAMASI ({today_str}): Günlük PnL sıfırlandı.")
        save_state(state)

    return state


def save_state(state: dict) -> None:
    """Güncellenmiş durumu state.json dosyasına yazar."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_binance_klines(symbol: str = "BTCUSDT", interval: str = "5m", limit: int = 100) -> pd.DataFrame:
    """Binance Public API üzerinden canlı mum (OHLCV) verisi çeker."""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"Binance API hatası! HTTP {resp.status_code}: {resp.text}")

    data = resp.json()
    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades_count", "taker_buy_volume",
        "taker_buy_quote_volume", "ignore"
    ])
    
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["open"] = df["open"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """EMA 38, EMA 62 ve Stochastic RSI (%K) indikatörlerini hesaplar."""
    df = df.copy()

    # EMA 38 & EMA 62
    df["ema_38"] = df["close"].ewm(span=38, adjust=False).mean()
    df["ema_62"] = df["close"].ewm(span=62, adjust=False).mean()

    # RSI (14)
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))

    # Stochastic RSI (14, 14, 3)
    stoch_min = rsi.rolling(window=14).min()
    stoch_max = rsi.rolling(window=14).max()
    stoch_raw = 100 * (rsi - stoch_min) / (stoch_max - stoch_min + 1e-10)
    df["stoch_k"] = stoch_raw.rolling(window=3).mean()

    return df


def call_groq_ai_analyst(market_context: dict) -> dict:
    """Groq Cloud API (Llama 3.3 70B) ile otonom analiz ve JSON karar üretir."""
    system_prompt = (
        "You are KRIPTON ALGO-TRADER, an autonomous algorithmic execution engine for 5m BTCUSDT Futures.\n"
        "Your sole goal is +1.00% daily net profit scalping.\n\n"
        "STRATEGY RULES (5m timeframe):\n"
        "1. BUY (LONG): EMA_38 > EMA_62 (Uptrend) AND Stoch_K < 45 (Pullback Region).\n"
        "   Take Profit: Entry * 1.012 (+1.20%). Stop Loss: Entry * 0.994 (-0.60%).\n"
        "2. SELL (SHORT): EMA_38 < EMA_62 (Downtrend) AND Stoch_K > 55 (Rebound Region).\n"
        "   Take Profit: Entry * 0.988 (-1.20%). Stop Loss: Entry * 1.006 (+0.60%).\n"
        "3. WAIT: If market is flat, crossing, or conditions not met -> action: 'WAIT'.\n\n"
        "DAILY SAFEGUARDS:\n"
        "- If today_pnl_pct >= 1.00% -> output action: 'DAILY_TARGET_REACHED'\n"
        "- If today_pnl_pct <= -2.00% -> output action: 'DAILY_STOP_REACHED'\n\n"
        "OUTPUT FORMAT: You MUST respond ONLY with valid raw JSON matching:\n"
        "{\n"
        '  "action": "BUY" | "SELL" | "WAIT" | "CLOSE" | "DAILY_TARGET_REACHED" | "DAILY_STOP_REACHED",\n'
        '  "reasoning": "Short Turkish explanation of technical triggers.",\n'
        '  "trade_details": {\n'
        '    "symbol": "BTCUSDT",\n'
        '    "side": "LONG" | "SHORT" | "NONE",\n'
        '    "entry_price": 0.0,\n'
        '    "stop_loss": 0.0,\n'
        '    "take_profit": 0.0,\n'
        '    "position_size_usdt": 2000.0\n'
        '  }\n'
        "}"
    )

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Live Market Context: {json.dumps(market_context)}"}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }

    try:
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=8)
        if resp.status_code == 200:
            res_content = resp.json()["choices"][0]["message"]["content"]
            decision = json.loads(res_content)
            decision["ai_status"] = "GROQ_LLM_SUCCESS"
            return decision
    except Exception as e:
        print(f"⚠️ Groq API Bağlantı Uyarısı ({str(e)}), yerel motor devreye giriyor.")

    # Yerel Fallback Motoru
    return evaluate_local_rules(market_context)


def evaluate_local_rules(ctx: dict) -> dict:
    """Groq API erişilemezse çalışacak deterministik kural motoru."""
    price = ctx["current_price"]
    ema_38 = ctx["ema_38"]
    ema_62 = ctx["ema_62"]
    stoch_k = ctx["stoch_k"]
    pnl_pct = ctx.get("today_pnl_pct", 0.0)

    if pnl_pct >= DAILY_TARGET_PCT:
        return {
            "action": "DAILY_TARGET_REACHED",
            "reasoning": f"Günlük +%{DAILY_TARGET_PCT} net kâr hedefine ulaşıldı. Kâr kilitlendi.",
            "trade_details": {"symbol": SYMBOL, "side": "NONE", "entry_price": 0.0, "stop_loss": 0.0, "take_profit": 0.0, "position_size_usdt": 0.0},
            "ai_status": "LOCAL_FALLBACK"
        }

    if pnl_pct <= DAILY_STOP_PCT:
        return {
            "action": "DAILY_STOP_REACHED",
            "reasoning": f"Günlük -%{abs(DAILY_STOP_PCT)} max kayıp eşiğine ulaşıldı. Sistem durduruldu.",
            "trade_details": {"symbol": SYMBOL, "side": "NONE", "entry_price": 0.0, "stop_loss": 0.0, "take_profit": 0.0, "position_size_usdt": 0.0},
            "ai_status": "LOCAL_FALLBACK"
        }

    if ema_38 > ema_62 and stoch_k < 45.0:
        entry = round(price * 1.0002, 2)
        return {
            "action": "BUY",
            "reasoning": f"BUY (LONG): EMA_38 (${ema_38:.2f}) > EMA_62 (${ema_62:.2f}) & Stoch_K ({stoch_k:.1f} < 45).",
            "trade_details": {
                "symbol": SYMBOL,
                "side": "LONG",
                "entry_price": entry,
                "stop_loss": round(entry * (1 - SL_PCT), 2),
                "take_profit": round(entry * (1 + TP_PCT), 2),
                "position_size_usdt": round(ctx["current_balance"] * POS_SIZE_RATIO * LEVERAGE, 2)
            },
            "ai_status": "LOCAL_FALLBACK"
        }

    if ema_38 < ema_62 and stoch_k > 55.0:
        entry = round(price * 0.9998, 2)
        return {
            "action": "SELL",
            "reasoning": f"SELL (SHORT): EMA_38 (${ema_38:.2f}) < EMA_62 (${ema_62:.2f}) & Stoch_K ({stoch_k:.1f} > 55).",
            "trade_details": {
                "symbol": SYMBOL,
                "side": "SHORT",
                "entry_price": entry,
                "stop_loss": round(entry * (1 + SL_PCT), 2),
                "take_profit": round(entry * (1 - TP_PCT), 2),
                "position_size_usdt": round(ctx["current_balance"] * POS_SIZE_RATIO * LEVERAGE, 2)
            },
            "ai_status": "LOCAL_FALLBACK"
        }

    return {
        "action": "WAIT",
        "reasoning": "Sinyaller nötr veya Stoch_K 45-55 arasında. Bekleniyor.",
        "trade_details": {"symbol": SYMBOL, "side": "NONE", "entry_price": 0.0, "stop_loss": 0.0, "take_profit": 0.0, "position_size_usdt": 0.0},
        "ai_status": "LOCAL_FALLBACK"
    }


def run_execution_cycle() -> dict:
    """Tek bir tarama ve işlem yürütme turu çalıştırır."""
    state = load_state()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Borsa Verisi Çek & İndikatör Hesapla
    df_raw = fetch_binance_klines(symbol=SYMBOL, interval=TIMEFRAME, limit=100)
    df = calculate_indicators(df_raw)
    
    last_row = df.iloc[-1]
    curr_price = float(last_row["close"])
    ema_38 = float(last_row["ema_38"])
    ema_62 = float(last_row["ema_62"])
    stoch_k = float(last_row["stoch_k"])

    print(f"\n==================================================")
    print(f"⏰ [KRIPTON ALGO-TRADER RUNNER]: {now_str}")
    print(f"📈 Piyasa: BTCUSDT ${curr_price:,.2f} | EMA38: ${ema_38:,.2f} | EMA62: ${ema_62:,.2f} | Stoch_K: {stoch_k:.1f}")
    print(f"💰 Bakiye: ${state['current_balance']:,.2f} | Bugün PnL: %{state['today_pnl_pct']:+.2f} (${state['today_pnl_usdt']:+.2f})")

    # 2. Mevcut Açık Pozisyon Denetimi
    active_pos = state.get("active_position")
    if active_pos is not None:
        side = active_pos["side"]
        entry_price = active_pos["entry_price"]
        sl = active_pos["stop_loss"]
        tp = active_pos["take_profit"]
        size_usdt = active_pos["position_size_usdt"]

        sl_hit = (side == "LONG" and curr_price <= sl) or (side == "SHORT" and curr_price >= sl)
        tp_hit = (side == "LONG" and curr_price >= tp) or (side == "SHORT" and curr_price <= tp)

        if sl_hit or tp_hit:
            close_reason = "TAKE_PROFIT" if tp_hit else "STOP_LOSS"
            exec_exit = curr_price * (1 - SLIPPAGE_PCT/100) if side == "LONG" else curr_price * (1 + SLIPPAGE_PCT/100)

            # Brüt & Net PnL Hesabı
            if side == "LONG":
                gross_pnl = (exec_exit - entry_price) / entry_price * size_usdt
            else:
                gross_pnl = (entry_price - exec_exit) / entry_price * size_usdt

            fees = size_usdt * (TAKER_FEE_PCT / 100) * 2
            net_pnl = gross_pnl - fees
            pnl_pct = (net_pnl / state["initial_balance"]) * 100

            state["current_balance"] += net_pnl
            state["today_pnl_usdt"] += net_pnl
            state["today_pnl_pct"] += pnl_pct
            state["active_position"] = None

            trade_log = {
                "id": f"TRADE-{len(state['trade_history'])+1:03d}",
                "symbol": SYMBOL,
                "side": side,
                "entry_price": entry_price,
                "exit_price": round(exec_exit, 2),
                "reason": close_reason,
                "net_pnl_usdt": round(net_pnl, 2),
                "timestamp": now_str
            }
            state["trade_history"].insert(0, trade_log)
            save_state(state)

            icon = "🎉" if net_pnl > 0 else "🛑"
            print(f"{icon} POZİSYON KAPATILDI ({close_reason}): Net PnL: ${net_pnl:+.2f} (Bakiye: ${state['current_balance']:,.2f})")
            return {"action": "CLOSE", "net_pnl": net_pnl}
        else:
            print(f"🔒 AÇIK POZİSYON KORUNUYOR: {side} @ ${entry_price:,.2f} (SL: ${sl:,.2f}, TP: ${tp:,.2f})")
            return {"action": "WAIT", "message": "Position Open"}

    # 3. Yeni İşlem Taraması (Groq AI LLM + Strateji)
    market_context = {
        "symbol": SYMBOL,
        "current_price": curr_price,
        "ema_38": ema_38,
        "ema_62": ema_62,
        "stoch_k": stoch_k,
        "account_balance": state["current_balance"],
        "today_pnl_pct": state["today_pnl_pct"],
        "active_position": None
    }

    decision = call_groq_ai_analyst(market_context)
    action = decision.get("action", "WAIT")
    reasoning = decision.get("reasoning", "Koşullar nötr.")
    ai_status = decision.get("ai_status", "UNKNOWN")

    print(f"🤖 Groq AI Kararı [{ai_status}]: {action} -> {reasoning}")

    if action in ["BUY", "SELL"]:
        details = decision.get("trade_details", {})
        side = "LONG" if action == "BUY" else "SHORT"
        entry_price = details.get("entry_price") or (curr_price * (1 + SLIPPAGE_PCT/100) if side == "LONG" else curr_price * (1 - SLIPPAGE_PCT/100))
        
        pos_size = round(state["current_balance"] * POS_SIZE_RATIO * LEVERAGE, 2)
        sl_val = details.get("stop_loss") or (round(entry_price * (1 - SL_PCT), 2) if side == "LONG" else round(entry_price * (1 + SL_PCT), 2))
        tp_val = details.get("take_profit") or (round(entry_price * (1 + TP_PCT), 2) if side == "LONG" else round(entry_price * (1 - TP_PCT), 2))

        new_pos = {
            "symbol": SYMBOL,
            "side": side,
            "entry_price": round(entry_price, 2),
            "position_size_usdt": pos_size,
            "stop_loss": sl_val,
            "take_profit": tp_val,
            "entry_time": now_str
        }

        state["active_position"] = new_pos
        save_state(state)
        print(f"🚀 YENİ İŞLEM AÇILDI: {side} @ ${entry_price:,.2f} | Büyüklük: ${pos_size:,.2f} (SL: ${sl_val:,.2f}, TP: ${tp_val:,.2f})")

    elif action == "DAILY_TARGET_REACHED":
        print(f"🎉 GÜNLÜK NET %1 KÂR HEDEFİNE ULAŞILDI! Bugünün PnL'i: %{state['today_pnl_pct']:+.2f}. İşlemler kilitlendi.")
    elif action == "DAILY_STOP_REACHED":
        print(f"🛑 GÜNLÜK MAX KAYIP EŞİĞİNE (-%2) ULAŞILDI! Bugünün PnL'i: %{state['today_pnl_pct']:+.2f}. Sistem durduruldu.")

    return decision


def main():
    print("=" * 60)
    print("🚀 KRIPTON ALGO-TRADER OTONOM RUNNER BAŞLATILDI")
    print(f"📌 Parite: {SYMBOL} (5m) | Groq Model: {GROQ_MODEL}")
    print(f"🎯 Hedef: Günlük +%1.0 Net Kâr | Stop: -%2.0 Net Kayıp")
    print("=" * 60)

    # CLI komut parametreleri denetimi
    if len(sys.argv) > 1 and sys.argv[1] in ["--once", "--single-run"]:
        run_execution_cycle()
        print("\n✅ Tek tur çalıştırma tamamlandı.")
        return

    # 5 Dakikalık Döngü
    while True:
        try:
            run_execution_cycle()
        except Exception as e:
            print(f"❌ Döngü Hatası: {str(e)}")
        
        print(f"\n⏳ Bir sonraki tarama için {INTERVAL_SECONDS} saniye bekleniyor...")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
