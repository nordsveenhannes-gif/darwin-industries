from __future__ import annotations

import math
import os
import time
from statistics import median


STRESS_THRESHOLDS = {0: 75, 1: 68, 2: 62, 3: 58, 4: 55}


def required_score(stress_level: int, defensive_mode: bool = False) -> int:
    base = STRESS_THRESHOLDS[max(0, min(int(stress_level), 4))]
    return min(90, base + (8 if defensive_mode else 0))


def compute_stress_level(
    *,
    minutes_since_trade: float,
    active_market: bool,
    consecutive_losses: int,
    defensive_mode: bool,
) -> int:
    if not active_market or defensive_mode:
        return 0
    if minutes_since_trade < 30:
        level = 0
    elif minutes_since_trade < 60:
        level = 1
    elif minutes_since_trade < 120:
        level = 2
    elif minutes_since_trade < 180:
        level = 3
    else:
        level = 4

    # Missing opportunity can increase activity. Losses never do.
    if consecutive_losses >= 2:
        level = max(0, level - 1)
    return level


def _pct_change(a: float, b: float) -> float:
    if not a:
        return 0.0
    return (b / a - 1.0) * 100.0


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _recent_structure(candles: list[dict]) -> dict:
    if len(candles) < 12:
        return {
            "higher_highs": False,
            "higher_lows": False,
            "breakout": False,
            "reclaim": False,
            "support": None,
            "range_pct": 0.0,
            "momentum_5m_pct": 0.0,
            "momentum_15m_pct": 0.0,
            "volume_ratio": 0.0,
        }

    recent = candles[-30:]
    current = _safe_float(recent[-1].get("close"))
    highs = [_safe_float(c.get("high")) for c in recent]
    lows = [_safe_float(c.get("low")) for c in recent]
    closes = [_safe_float(c.get("close")) for c in recent]
    volumes = [_safe_float(c.get("volume")) for c in recent]

    prior_high = max(highs[-13:-1])
    recent_lows = lows[-8:-1]
    support = min(recent_lows) if recent_lows else min(lows[-12:-1])

    # Compare three rolling swing groups rather than demanding textbook-perfect structure.
    g1 = recent[-12:-8]
    g2 = recent[-8:-4]
    g3 = recent[-4:]
    h1 = max(_safe_float(c.get("high")) for c in g1)
    h2 = max(_safe_float(c.get("high")) for c in g2)
    h3 = max(_safe_float(c.get("high")) for c in g3)
    l1 = min(_safe_float(c.get("low")) for c in g1)
    l2 = min(_safe_float(c.get("low")) for c in g2)
    l3 = min(_safe_float(c.get("low")) for c in g3)

    higher_highs = h3 > h2 >= h1 * 0.995
    higher_lows = l3 > l2 >= l1 * 0.995
    breakout = current > prior_high * 1.0015

    prior_support = min(lows[-14:-4])
    swept = min(lows[-4:-1]) < prior_support * 0.998
    reclaim = swept and current > prior_support

    momentum_5m = _pct_change(closes[-6], current) if len(closes) >= 6 else 0.0
    momentum_15m = _pct_change(closes[-16], current) if len(closes) >= 16 else momentum_5m

    current_vol = sum(volumes[-5:]) / 5.0
    prior_slice = volumes[-20:-5]
    prior_vol = sum(prior_slice) / max(len(prior_slice), 1)
    volume_ratio = current_vol / prior_vol if prior_vol > 0 else 1.0

    low_30 = min(lows[-30:])
    high_30 = max(highs[-30:])
    range_pct = ((high_30 - low_30) / current * 100.0) if current > 0 else 0.0

    return {
        "higher_highs": higher_highs,
        "higher_lows": higher_lows,
        "breakout": breakout,
        "reclaim": reclaim,
        "support": support,
        "range_pct": round(range_pct, 3),
        "momentum_5m_pct": round(momentum_5m, 3),
        "momentum_15m_pct": round(momentum_15m, 3),
        "volume_ratio": round(volume_ratio, 3),
    }


def _fee_cost_per_side_usd(notional_usd: float) -> float:
    mode = os.getenv("DARWIN_MEME_SIM_FEE_MODE", "dex_route").strip().lower()
    if mode == "moonshot_app":
        if notional_usd <= 100:
            return max(0.99, notional_usd * 0.025)
        return notional_usd * 0.01

    try:
        bps = float(os.getenv("DARWIN_MEME_SIM_ROUTE_FEE_BPS_PER_SIDE", "30"))
    except ValueError:
        bps = 30.0
    return notional_usd * max(0.0, min(bps, 500.0)) / 10000.0


def execution_friction_pct(notional_usd: float, liquidity_usd: float) -> float:
    if notional_usd <= 0:
        return 100.0

    try:
        base_slippage_bps = float(os.getenv("DARWIN_MEME_SIM_SLIPPAGE_BPS", "35"))
    except ValueError:
        base_slippage_bps = 35.0

    # Impact proxy is intentionally conservative for the paper simulator.
    impact_bps = 0.0
    if liquidity_usd > 0:
        impact_bps = min(250.0, (notional_usd / liquidity_usd) * 10000.0 * 0.35)
    slippage_bps_per_side = max(0.0, min(base_slippage_bps + impact_bps, 500.0))

    fee_usd = _fee_cost_per_side_usd(notional_usd) * 2.0
    try:
        network_usd = float(os.getenv("DARWIN_MEME_SIM_NETWORK_FEE_USD_ROUND_TRIP", "0.02"))
    except ValueError:
        network_usd = 0.02

    fee_pct = (fee_usd + max(network_usd, 0.0)) / notional_usd * 100.0
    slip_pct = (slippage_bps_per_side * 2.0) / 100.0
    return round(fee_pct + slip_pct, 3)


def _age_bucket(age_minutes: float | None) -> str:
    if age_minutes is None:
        return "UNKNOWN"
    if age_minutes <= 15:
        return "ULTRA_NEW"
    if age_minutes <= 120:
        return "EARLY"
    if age_minutes <= 1440:
        return "MOMENTUM"
    if age_minutes <= 10080:
        return "ESTABLISHED_TREND"
    return "REVIVAL_OR_OLD"


def score_candidates(
    candidates: list[dict],
    *,
    stress_level: int,
    account_equity_usd: float,
    defensive_mode: bool,
    max_notional_usd: float,
) -> list[dict]:
    if not candidates:
        return []

    h1_changes = [_safe_float(c.get("price_change_h1")) for c in candidates]
    median_h1 = median(h1_changes) if h1_changes else 0.0
    threshold = required_score(stress_level, defensive_mode)

    scored = []
    now_ms = time.time() * 1000.0

    for raw in candidates:
        item = dict(raw)
        candles = item.get("ohlcv_1m") or []
        structure = _recent_structure(candles)

        liquidity = _safe_float(item.get("liquidity_usd"))
        price = _safe_float(item.get("price_usd"))
        buys_m5 = int(item.get("buys_m5") or 0)
        sells_m5 = int(item.get("sells_m5") or 0)
        buys_h1 = int(item.get("buys_h1") or 0)
        sells_h1 = int(item.get("sells_h1") or 0)
        tx_m5 = buys_m5 + sells_m5
        tx_h1 = buys_h1 + sells_h1

        volume_m5 = _safe_float(item.get("volume_m5"))
        volume_h1 = _safe_float(item.get("volume_h1"))
        prior_55_volume = max(volume_h1 - volume_m5, 0.0)
        volume_acceleration = (
            (volume_m5 / 5.0) / (prior_55_volume / 55.0)
            if prior_55_volume > 0 and volume_m5 > 0
            else structure["volume_ratio"]
        )

        prior_55_tx = max(tx_h1 - tx_m5, 0)
        transaction_acceleration = (
            (tx_m5 / 5.0) / (prior_55_tx / 55.0)
            if prior_55_tx > 0 and tx_m5 > 0
            else 1.0
        )
        buy_ratio = (buys_m5 + 1.0) / (sells_m5 + 1.0)

        created_at = item.get("pair_created_at")
        age_minutes = None
        if created_at:
            age_minutes = max(0.0, (now_ms - _safe_float(created_at)) / 60000.0)

        latest_ts = candles[-1].get("timestamp") if candles else None
        candle_age_min = (
            max(0.0, time.time() - _safe_float(latest_ts)) / 60.0
            if latest_ts
            else 999.0
        )

        hard_reasons = []
        if not item.get("token_address"):
            hard_reasons.append("missing contract address")
        if not item.get("pool_address"):
            hard_reasons.append("missing pool address")
        if price <= 0:
            hard_reasons.append("missing executable price")
        if liquidity < float(os.getenv("DARWIN_MEME_MIN_LIQUIDITY_USD", "15000")):
            hard_reasons.append("liquidity below paper hard gate")
        if sells_h1 < 3 and sells_m5 < 1:
            hard_reasons.append("no meaningful recent sell-side evidence")
        if len(candles) < 20:
            hard_reasons.append("insufficient 1-minute OHLCV history")
        if candle_age_min > 20:
            hard_reasons.append("OHLCV is stale")

        hard_gate_pass = not hard_reasons

        signals = []
        if volume_acceleration >= 1.25 and structure["momentum_5m_pct"] > 0:
            signals.append("volume_acceleration")
        if transaction_acceleration >= 1.25:
            signals.append("transaction_acceleration")
        if buy_ratio >= 1.15 and buys_m5 >= 3:
            signals.append("buy_pressure")
        if structure["higher_highs"] and structure["higher_lows"]:
            signals.append("hh_hl_structure")
        if structure["breakout"] and volume_acceleration >= 1.05:
            signals.append("breakout")
        if structure["reclaim"]:
            signals.append("liquidity_sweep_reclaim")
        if _safe_float(item.get("price_change_h1")) > median_h1 + 1.0:
            signals.append("relative_strength")

        security_score = 20 if hard_gate_pass else max(0, 20 - len(hard_reasons) * 6)
        liquidity_score = min(15.0, 4.0 + math.log10(max(liquidity, 1.0) / 10000.0 + 1.0) * 11.0)
        volume_score = min(15.0, max(0.0, (volume_acceleration - 0.8) * 12.0))
        transaction_score = min(10.0, max(0.0, (transaction_acceleration - 0.8) * 8.0))
        structure_score = (
            (8.0 if structure["higher_highs"] else 0.0)
            + (7.0 if structure["higher_lows"] else 0.0)
        )
        breakout_score = (
            (7.0 if structure["breakout"] else 0.0)
            + (7.0 if structure["reclaim"] else 0.0)
        )
        buy_score = min(8.0, max(0.0, (buy_ratio - 0.8) * 8.0))
        relative_score = min(
            5.0,
            max(0.0, (_safe_float(item.get("price_change_h1")) - median_h1) * 0.7),
        )

        score = int(
            round(
                min(
                    100.0,
                    security_score
                    + liquidity_score
                    + volume_score
                    + transaction_score
                    + structure_score
                    + breakout_score
                    + buy_score
                    + relative_score,
                )
            )
        )

        current = price
        support = structure["support"] or (current * 0.95)
        stop = max(support * 0.995, current * 0.92)
        if stop >= current:
            stop = current * 0.96
        stop_distance_pct = max(0.5, (current - stop) / current * 100.0)

        signal_count = len(signals)
        if signal_count == 2:
            mode = "PROBE"
        elif (
            structure["higher_highs"]
            and structure["higher_lows"]
            and structure["momentum_15m_pct"] > 2.0
            and volume_acceleration >= 1.15
        ):
            mode = "TREND_RUNNER"
        elif signal_count >= 3 and (structure["reclaim"] or structure["breakout"]):
            mode = "STRUCTURED_SCALP"
        else:
            mode = "MOMENTUM_SCALP"

        risk_pct_equity = 1.0
        if score >= 82:
            risk_pct_equity = 1.5
        elif score >= 72:
            risk_pct_equity = 1.25
        if mode == "PROBE":
            risk_pct_equity *= 0.45
        if stress_level >= 3 and mode != "PROBE":
            risk_pct_equity = min(1.5, risk_pct_equity + 0.25)
        if defensive_mode:
            risk_pct_equity *= 0.5
        risk_pct_equity = min(2.0, max(0.25, risk_pct_equity))

        allowed_risk_usd = max(account_equity_usd, 1.0) * risk_pct_equity / 100.0
        position_size = allowed_risk_usd / max(stop_distance_pct / 100.0, 0.005)
        position_size = min(max_notional_usd, max(1.0, position_size))

        friction_pct = execution_friction_pct(position_size, liquidity)
        expected_first_move = max(
            structure["momentum_5m_pct"] * 1.8,
            structure["momentum_15m_pct"] * 1.15,
            structure["range_pct"] * 0.35,
            abs(_safe_float(item.get("price_change_h1"))) * 0.55,
        )
        expected_first_move = max(0.0, round(expected_first_move, 3))

        friction_multiple = 2.0 if (
            score >= 82 and volume_acceleration >= 1.6 and transaction_acceleration >= 1.4
        ) else 3.0
        friction_pass = expected_first_move >= friction_pct * friction_multiple

        technical_pass = (
            hard_gate_pass
            and score >= threshold
            and signal_count >= 2
            and friction_pass
        )

        if mode == "MOMENTUM_SCALP":
            max_hold = 15
            reward_multiple = 1.25
        elif mode == "PROBE":
            max_hold = 12
            reward_multiple = 1.15
        elif mode == "STRUCTURED_SCALP":
            max_hold = 60
            reward_multiple = 2.0
        else:
            max_hold = 180
            reward_multiple = 2.5

        minimum_target_pct = max(friction_pct * friction_multiple, stop_distance_pct * reward_multiple)
        target = current * (1.0 + minimum_target_pct / 100.0)

        item.update(
            {
                "age_minutes": round(age_minutes, 1) if age_minutes is not None else None,
                "age_bucket": _age_bucket(age_minutes),
                "paper_tradeable": hard_gate_pass,
                "hard_gate_pass": hard_gate_pass,
                "hard_gate_reason": "PASS" if hard_gate_pass else "; ".join(hard_reasons),
                "live_safety_complete": False,
                "unverified_live_checks": [
                    "mint/freeze authority",
                    "holder concentration",
                    "creator/deployer allocation",
                    "bundled/sniper supply",
                    "connected-wallet risk",
                    "developer history",
                ],
                "signals": signals,
                "signal_count": signal_count,
                "setup_score": score,
                "required_score": threshold,
                "stress_level": stress_level,
                "defensive_mode": bool(defensive_mode),
                "suggested_mode": mode,
                "volume_acceleration": round(volume_acceleration, 3),
                "transaction_acceleration": round(transaction_acceleration, 3),
                "buy_ratio_m5": round(buy_ratio, 3),
                "structure": structure,
                "recommended_entry": current,
                "recommended_stop": stop,
                "recommended_target": target,
                "recommended_risk_pct": round(risk_pct_equity, 3),
                "max_position_usd": round(position_size, 2),
                "expected_round_trip_cost_pct": friction_pct,
                "expected_first_move_pct": expected_first_move,
                "friction_multiple_required": friction_multiple,
                "friction_pass": friction_pass,
                "technical_pass": technical_pass,
                "max_hold_minutes": max_hold,
            }
        )
        scored.append(item)

    return sorted(
        scored,
        key=lambda x: (
            bool(x.get("technical_pass")),
            int(x.get("setup_score") or 0),
            float(x.get("volume_acceleration") or 0),
            float(x.get("transaction_acceleration") or 0),
        ),
        reverse=True,
    )
