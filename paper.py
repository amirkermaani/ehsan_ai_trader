import json
from pathlib import Path
from datetime import datetime, timezone

class PaperBook:
    def __init__(self, path, starting_balance):
        self.path = Path(path)
        self.data = {"balance": float(starting_balance), "signals": [], "trades": []}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text())
            except Exception:
                pass

    @property
    def balance(self):
        return float(self.data["balance"])

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2))

    def signals_today(self):
        today = datetime.now(timezone.utc).date().isoformat()
        return sum(1 for s in self.data["signals"] if s["date"] == today)

    def record_signal(self, symbol, timeframe, side, plan):
        self.data["signals"].append({
            "date": datetime.now(timezone.utc).date().isoformat(),
            "symbol": symbol, "timeframe": timeframe, "side": side,
            "risk": plan["risk_usd"], "notional": plan["notional"]
        })
        self.save()

    def close_trade(self, pnl):
        self.data["balance"] = max(0, self.balance + float(pnl))
        self.data["trades"].append({
            "date": datetime.now(timezone.utc).isoformat(), "pnl": float(pnl)
        })
        self.save()

    def stats(self):
        trades = self.data["trades"]
        return {
            "trades": len(trades),
            "wins": sum(1 for t in trades if t["pnl"] > 0),
            "losses": sum(1 for t in trades if t["pnl"] < 0),
            "pnl": sum(t["pnl"] for t in trades)
        }
