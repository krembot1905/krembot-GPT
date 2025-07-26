import json
import requests
import pandas as pd
import numpy as np
import os
from datetime import datetime

# === טעינת קובץ ההגדרות ===
def load_config():
    with open("config.json", "r", encoding="utf-8") as file:
        return json.load(file)

# === משיכת נתוני OHLCV מ-Binance ===
def fetch_binance_data(symbol="INJUSDT", interval="15m", limit=1000):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "num_trades", "taker_base_vol", "taker_quote_vol", "ignore"
        ])
        df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
        return df[["open_time", "open", "high", "low", "close", "volume"]]
    else:
        print("❌ שגיאה בשליפת נתונים:", response.text)
        return None

# === חישוב אינדיקטורים (EMA, RSI, MACD, ATR) ===
def add_indicators(df):
    df["EMA20"] = df["close"].ewm(span=20).mean()
    df["EMA50"] = df["close"].ewm(span=50).mean()

    # RSI
    delta = df["close"].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(window=14).mean()
    avg_loss = pd.Series(loss).rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    df["MACD"] = ema12 - ema26
    df["Signal"] = df["MACD"].ewm(span=9).mean()

    # ATR
    df["H-L"] = df["high"] - df["low"]
    df["H-PC"] = abs(df["high"] - df["close"].shift(1))
    df["L-PC"] = abs(df["low"] - df["close"].shift(1))
    df["TR"] = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    df["ATR"] = df["TR"].rolling(window=14).mean()

    return df

# === לוגיקת איתות BUY/SELL ===
def generate_signal(df):
    latest = df.iloc[-1]
    if latest["EMA20"] > latest["EMA50"] and latest["RSI"] > 50 and latest["MACD"] > latest["Signal"]:
        return "BUY"
    elif latest["EMA20"] < latest["EMA50"] and latest["RSI"] < 50 and latest["MACD"] < latest["Signal"]:
        return "SELL"
    return "HOLD"

# === שליחת איתות ל-WunderTrading ===
def send_signal_to_wunder(webhook_url, action, amount, symbol):
    payload = {
        "action": action.lower(),  # buy / sell
        "symbol": symbol,
        "amount": amount,
        "timestamp": datetime.utcnow().isoformat()
    }
    try:
        response = requests.post(webhook_url, json=payload)
        if response.status_code == 200:
            print(f"✅ אות {action} נשלח ל-WunderTrading ({symbol})")
        else:
            print(f"❌ שגיאה בשליחת איתות: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"❌ שגיאה בחיבור ל-WunderTrading: {e}")

# === שמירת לוגים ===
def save_trade_log(action, price, symbol, amount):
    log_file = "logs/krembot_logs.csv"
    log_exists = os.path.isfile(log_file)
    with open(log_file, "a", encoding="utf-8") as f:
        if not log_exists:
            f.write("timestamp,action,symbol,price,amount\n")
        f.write(f"{datetime.utcnow().isoformat()},{action},{symbol},{price},{amount}\n")

# === MAIN ===
def main():
    config = load_config()
    bot_name = config.get("bot_name", "krembot-GPT")
    symbol = config.get("symbol", "INJUSDT")
    timeframe = config.get("timeframe", "15m")
    trade_amount = config.get("trade_amount", 50)
    webhook_url = config.get("webhook_url")

    print(f"🚀 {bot_name} מוכן לפעולה! סוחר על {symbol} ({timeframe}) עם {trade_amount}$")

    df = fetch_binance_data(symbol, timeframe)
    if df is None:
        return

    df = add_indicators(df)
    signal = generate_signal(df)
    last_price = df["close"].iloc[-1]

    print(f"📊 האות הנוכחי: {signal} (מחיר: {last_price})")

    if signal in ["BUY", "SELL"]:
        send_signal_to_wunder(webhook_url, signal, trade_amount, symbol)
        save_trade_log(signal, last_price, symbol, trade_amount)

if __name__ == "__main__":
    main()
