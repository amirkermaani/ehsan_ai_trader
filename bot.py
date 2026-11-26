import os
import asyncio
import logging
from datetime import datetime, timezone, date
from typing import Optional

import ccxt
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from strategy import analyze
from risk import calculate_plan
from paper import PaperBook

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ehsan-ai-trader")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
EXCHANGE_ID = os.getenv("EXCHANGE_ID", "binance").strip()
DEFAULT_SYMBOLS = [s.strip().upper() for s in os.getenv(
    "SYMBOLS", "BTC/USDT,ETH/USDT,SOL/USDT"
).split(",") if s.strip()]
TIMEFRAMES = [s.strip() for s in os.getenv("TIMEFRAMES", "1h,4h,1d").split(",") if s.strip()]
STARTING_BALANCE = float(os.getenv("PAPER_BALANCE", "100"))
RISK_USD = float(os.getenv("RISK_USD", "1"))
MAX_RISK_USD = float(os.getenv("MAX_RISK_USD", "2"))
MAX_SIGNALS_DAY = int(os.getenv("MAX_SIGNALS_DAY", "2"))
MAX_LEVERAGE = float(os.getenv("MAX_LEVERAGE", "20"))
FEE_RATE = float(os.getenv("FEE_RATE", "0.0005"))  # assumed 0.05% per side
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "900"))

exchange_class = getattr(ccxt, EXCHANGE_ID, None)
if exchange_class is None:
    raise RuntimeError(f"Unsupported CCXT exchange id: {EXCHANGE_ID}")
exchange = exchange_class({"enableRateLimit": True, "options": {"defaultType": "swap"}})
book = PaperBook("paper_book.json", STARTING_BALANCE)

def fmt(x: float) -> str:
    return f"{x:,.6g}"

async def fetch_signal(symbol: str, timeframe: str):
    def _fetch():
        candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=160)
        ticker = exchange.fetch_ticker(symbol)
        return candles, ticker
    candles, ticker = await asyncio.to_thread(_fetch)
    price = float(ticker.get("last") or candles[-1][4])
    return analyze(candles, price, symbol, timeframe)

def signal_message(sig, plan):
    direction = "لانگ (خرید)" if sig["side"] == "LONG" else "شورت (فروش)"
    return (
        f"📡 Ehsan AI Trader | سیگنال آزمایشی\n\n"
        f"بازار: {sig['symbol']} | تایم‌فریم: {sig['timeframe']}\n"
        f"جهت: {direction}\n"
        f"قیمت مرجع: {fmt(sig['entry'])}\n"
        f"حد ضرر: {fmt(plan['stop'])}\n"
        f"هدف ۱: {fmt(plan['target'])}\n"
        f"نسبت سود به زیان: 1:{plan['rr']:.1f}\n\n"
        f"ریسک بودجه‌شده: ${plan['risk_usd']:.2f}\n"
        f"حجم اسمی پیشنهادی: ${plan['notional']:.2f}\n"
        f"مارجین تخمینی در اهرم {MAX_LEVERAGE:g}x: ${plan['margin']:.2f}\n"
        f"کارمزد تخمینی رفت‌وبرگشت: ${plan['fees']:.2f}\n\n"
        f"دلایل: {', '.join(sig['reasons'])}\n"
        f"⚠️ فقط هشدار آموزشی؛ سفارش واقعی ارسال نمی‌شود. سیگنال تضمین سود نیست."
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! من Ehsan AI Trader هستم. نسخه اول فقط داده عمومی بازار را می‌خواند، "
        "سیگنال آزمایشی می‌سازد و هیچ سفارش واقعی ارسال نمی‌کند.\n\n"
        "/scan BTC/USDT — تحلیل یک نماد\n"
        "/scanall — بررسی نمادهای تنظیم‌شده\n"
        "/status — موجودی و آمار دفتر آزمایشی\n"
        "/paperwin 1 — ثبت نتیجه برد آزمایشی\n"
        "/paperloss 1 — ثبت نتیجه باخت آزمایشی\n"
        "/help — راهنما"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def scan_symbol(update, symbol: str):
    sent = 0
    errors = []
    for timeframe in TIMEFRAMES:
        try:
            sig = await fetch_signal(symbol, timeframe)
            if sig["side"] == "WAIT":
                continue
            plan = calculate_plan(
                entry=sig["entry"], stop_pct=sig["atr_stop_pct"],
                balance=book.balance, risk_usd=RISK_USD,
                max_risk_usd=MAX_RISK_USD, max_leverage=MAX_LEVERAGE,
                fee_rate=FEE_RATE, rr=2.0, side=sig["side"], max_margin_usd=10.0
            )
            if not plan["valid"]:
                errors.append(plan["reason"])
                continue
            if book.signals_today() >= MAX_SIGNALS_DAY:
                errors.append("سقف دو سیگنال روزانه پر شده است.")
                break
            await update.message.reply_text(signal_message(sig, plan))
            book.record_signal(symbol, timeframe, sig["side"], plan)
            sent += 1
        except Exception as e:
            log.exception("scan failed")
            errors.append(f"{timeframe}: {str(e)[:160]}")
    if sent == 0:
        msg = "در این بررسی سیگنال واجد شرایط پیدا نشد."
        if errors:
            msg += "\n" + "\n".join(errors[:3])
        await update.message.reply_text(msg)

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("نمونه: /scan BTC/USDT")
        return
    await scan_symbol(update, context.args[0].upper())

async def scanall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for symbol in DEFAULT_SYMBOLS:
        if book.signals_today() >= MAX_SIGNALS_DAY:
            break
        await scan_symbol(update, symbol)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = book.stats()
    await update.message.reply_text(
        f"📒 دفتر آزمایشی\n"
        f"موجودی: ${book.balance:.2f}\n"
        f"سیگنال‌های امروز: {book.signals_today()}/{MAX_SIGNALS_DAY}\n"
        f"معاملات ثبت‌شده: {stats['trades']}\n"
        f"برد: {stats['wins']} | باخت: {stats['losses']}\n"
        f"سود/زیان تحقق‌یافته: ${stats['pnl']:.2f}\n"
        f"حالت: PAPER ONLY — بدون سفارش واقعی"
    )

async def paper_result(update: Update, context: ContextTypes.DEFAULT_TYPE, won: bool):
    if not context.args:
        await update.message.reply_text("مبلغ نتیجه را وارد کن؛ مثال: /paperwin 1")
        return
    try:
        amount = abs(float(context.args[0]))
        if amount <= 0:
            raise ValueError()
        if won:
            book.close_trade(amount)
        else:
            book.close_trade(-amount)
        await update.message.reply_text(f"نتیجه آزمایشی ثبت شد. موجودی جدید: ${book.balance:.2f}")
    except Exception:
        await update.message.reply_text("عدد نامعتبر است.")

async def paperwin_cmd(update, context):
    await paper_result(update, context, True)

async def paperloss_cmd(update, context):
    await paper_result(update, context, False)

async def scheduled_scan(app: Application):
    while True:
        try:
            class Dummy:
                async def reply_text(self, text):
                    for chat_id in app.bot_data.get("subscribers", set()):
                        await app.bot.send_message(chat_id=chat_id, text=text)
            for symbol in DEFAULT_SYMBOLS:
                if book.signals_today() >= MAX_SIGNALS_DAY:
                    break
                for timeframe in TIMEFRAMES:
                    sig = await fetch_signal(symbol, timeframe)
                    if sig["side"] == "WAIT":
                        continue
                    plan = calculate_plan(sig["entry"], sig["atr_stop_pct"], book.balance,
                                          RISK_USD, MAX_RISK_USD, MAX_LEVERAGE, FEE_RATE,
                                          2.0, side=sig["side"], max_margin_usd=10.0)
                    if plan["valid"] and book.signals_today() < MAX_SIGNALS_DAY:
                        for chat_id in app.bot_data.get("subscribers", set()):
                            await app.bot.send_message(chat_id=chat_id, text=signal_message(sig, plan))
                        book.record_signal(symbol, timeframe, sig["side"], plan)
        except Exception:
            log.exception("scheduled scan error")
        await asyncio.sleep(POLL_SECONDS)

async def post_init(app: Application):
    app.bot_data["subscribers"] = set()
    # Start-command users are added by the handler below.

async def subscribe_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    app = context.application
    app.bot_data.setdefault("subscribers", set()).add(update.effective_chat.id)
    await start(update, context)

def main():
    if not TOKEN:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env before running.")
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", subscribe_start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("scanall", scanall_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("paperwin", paperwin_cmd))
    app.add_handler(CommandHandler("paperloss", paperloss_cmd))
    async def background(application):
        application.create_task(scheduled_scan(application))
    app.post_init = background
    log.info("Starting Ehsan AI Trader in paper-only mode")
    app.run_polling()

if __name__ == "__main__":
    main()
