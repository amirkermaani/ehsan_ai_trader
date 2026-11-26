def calculate_plan(entry, stop_pct, balance, risk_usd, max_risk_usd,
                   max_leverage, fee_rate, rr=2.0, side="LONG",
                   max_margin_usd=10.0):
    if entry <= 0 or stop_pct <= 0 or balance <= 0:
        return {"valid": False, "reason": "داده قیمت یا فاصله حد ضرر معتبر نیست."}

    risk = min(risk_usd, max_risk_usd, balance * 0.02)
    fee_fraction = fee_rate * 2
    stop_fraction = stop_pct / 100

    # Risk-first sizing, capped at the user's preferred $10 margin / $200 notional.
    desired_notional = risk / (stop_fraction + fee_fraction)
    notional_cap = min(max_leverage * max_margin_usd, balance * max_leverage)
    notional = min(desired_notional, notional_cap)

    if notional <= 0:
        return {"valid": False, "reason": "حجم محاسبه‌شده معتبر نیست."}

    fees = notional * fee_fraction
    gross_stop_loss = max(0.0, risk - fees)
    actual_stop_fraction = gross_stop_loss / notional
    actual_risk = gross_stop_loss + fees

    # To achieve a net reward:risk ratio after estimated round-trip fees:
    # gross target PnL = rr * total risk + fees.
    gross_target = rr * actual_risk + fees
    target_fraction = gross_target / notional

    side = side.upper()
    if side == "SHORT":
        stop = entry * (1 + actual_stop_fraction)
        target = entry * (1 - target_fraction)
    else:
        stop = entry * (1 - actual_stop_fraction)
        target = entry * (1 + target_fraction)

    margin = notional / max_leverage
    return {
        "valid": True,
        "risk_usd": actual_risk,
        "notional": notional,
        "margin": margin,
        "fees": fees,
        "stop": stop,
        "target": target,
        "rr": rr,
        "stop_pct": actual_stop_fraction * 100,
        "capped_by_margin": desired_notional > notional_cap
    }
