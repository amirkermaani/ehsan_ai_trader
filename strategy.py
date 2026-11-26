import math

def ema(values, period):
    k = 2 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(value * k + out[-1] * (1 - k))
    return out

def rsi(values, period=14):
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr(candles, period=14):
    trs = []
    for i in range(1, len(candles)):
        high, low, prev_close = candles[i][2], candles[i][3], candles[i-1][4]
        trs.append(max(high-low, abs(high-prev_close), abs(low-prev_close)))
    return sum(trs[-period:]) / min(period, len(trs))

def analyze(candles, price, symbol, timeframe):
    if len(candles) < 60:
        return {"side": "WAIT"}
    closes = [c[4] for c in candles]
    e20, e50 = ema(closes, 20), ema(closes, 50)
    r = rsi(closes)
    a = atr(candles)
    macd_line = [x-y for x,y in zip(ema(closes,12), ema(closes,26))]
    signal_line = ema(macd_line, 9)
    side = "WAIT"
    reasons = []
    if e20[-1] > e50[-1] and price > e20[-1] and r >= 52 and macd_line[-1] > signal_line[-1]:
        side = "LONG"
        reasons = ["EMA20 بالای EMA50", "قیمت بالای EMA20", f"RSI={r:.1f}", "MACD صعودی"]
    elif e20[-1] < e50[-1] and price < e20[-1] and r <= 48 and macd_line[-1] < signal_line[-1]:
        side = "SHORT"
        reasons = ["EMA20 زیر EMA50", "قیمت زیر EMA20", f"RSI={r:.1f}", "MACD نزولی"]
    # ATR stop is set at 1.5 ATR; this is a volatility-based initial stop distance.
    stop_pct = (1.5 * a / price) * 100 if price else 0
    return {
        "side": side, "symbol": symbol, "timeframe": timeframe,
        "entry": price, "atr_stop_pct": stop_pct, "reasons": reasons
    }
