import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from agents import Runner
from dotenv import load_dotenv

from backend.agents.apex import StockTradeIdea, build_apex
from backend.agents.circuit import RiskDecision, build_circuit
from backend.agents.raptor import MemeTradeIdea, build_raptor
from backend.meme_strategy import compute_stress_level, required_score, score_candidates
from backend.storage import connect, init_db, now_iso


MOONSHOT_TRENDING = "https://api.moonshot.cc/tokens/v1/trending/solana"
MOONSHOT_TRADES = "https://api.moonshot.cc/trades/v1/latest/solana/{token_id}"
ALPACA_DATA = "https://data.alpaca.markets"
DEXSCREENER_BOOSTS = "https://api.dexscreener.com/token-boosts/top/v1"
DEXSCREENER_TOKENS = "https://api.dexscreener.com/tokens/v1/solana/{addresses}"
GECKO_OHLCV = (
    "https://api.geckoterminal.com/api/v2/networks/solana/pools/"
    "{pool_address}/ohlcv/minute?aggregate=1&limit=120"
)


def _http_json(url: str, headers: dict[str, str] | None = None, timeout: int = 15):
    req = Request(url, headers=headers or {"User-Agent": "DarwinIndustries/1.0"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _number(value):
    try:
        number = float(value)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def _sim_slippage_bps(asset_class: str) -> float:
    name = "DARWIN_MEME_SIM_SLIPPAGE_BPS" if asset_class == "MEME" else "DARWIN_STOCK_SIM_SLIPPAGE_BPS"
    default = "50" if asset_class == "MEME" else "5"
    try:
        value = float(os.getenv(name, default))
    except ValueError:
        value = float(default)
    return max(0.0, min(value, 500.0))


def _sim_fee_usd(asset_class: str, notional_usd: float) -> float:
    if asset_class == "MEME":
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
    return 0.0


def _walk_find(obj, keys: set[str]):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in keys and value not in (None, ""):
                return value
        for value in obj.values():
            found = _walk_find(value, keys)
            if found not in (None, ""):
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _walk_find(value, keys)
            if found not in (None, ""):
                return found
    return None


def _token_identity(token: dict) -> tuple[str | None, str | None, float | None]:
    symbol = _walk_find(token, {"symbol", "tokensymbol"})
    token_id = _walk_find(
        token,
        {"mintaddress", "tokenaddress", "tokenid", "mint", "address", "pairaddress", "pairid"},
    )
    price = _number(
        _walk_find(token, {"priceusd", "usdprice", "currentpriceusd", "price"})
    )
    return (
        str(symbol).upper().strip() if symbol else None,
        str(token_id).strip() if token_id else None,
        price,
    )


def _set_agent(conn, agent: str, status: str, action: str) -> None:
    conn.execute(
        """
        UPDATE agent_state
        SET status=?, last_action=?, updated_at=?
        WHERE agent=?
        """,
        (status, action, now_iso(), agent),
    )
    conn.commit()


def _snapshot(conn, asset_class: str, symbol: str, source: str, price: float | None, payload) -> None:
    conn.execute(
        """
        INSERT INTO market_snapshots(asset_class, symbol, source, price, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            asset_class,
            symbol,
            source,
            price,
            json.dumps(payload, ensure_ascii=False)[:200000],
            now_iso(),
        ),
    )
    conn.commit()


def _history(conn, asset_class: str, symbol: str, limit: int = 40):
    rows = conn.execute(
        """
        SELECT price, created_at
        FROM market_snapshots
        WHERE asset_class=? AND symbol=? AND price IS NOT NULL
        ORDER BY id DESC
        LIMIT ?
        """,
        (asset_class, symbol, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def _map_open_meme_prices(open_rows, pairs) -> dict[str, float]:
    """Map stored open positions to the most liquid live DEX pair for their contract."""
    wanted: dict[str, list[str]] = {}
    for row in open_rows:
        token = str(row["token_address"] or "").strip()
        symbol = str(row["symbol"] or "").upper().strip()
        if token and symbol:
            wanted.setdefault(token, []).append(symbol)

    best: dict[str, tuple[float, float]] = {}
    for pair in pairs or []:
        if not isinstance(pair, dict):
            continue
        base = pair.get("baseToken") or {}
        token = str(base.get("address") or "").strip()
        if token not in wanted:
            continue
        price = _number(pair.get("priceUsd"))
        if not price:
            continue
        liquidity = _number((pair.get("liquidity") or {}).get("usd")) or 0.0
        current = best.get(token)
        if current is None or liquidity > current[0]:
            best[token] = (liquidity, price)

    prices: dict[str, float] = {}
    for token, symbols in wanted.items():
        chosen = best.get(token)
        if not chosen:
            continue
        for symbol in symbols:
            prices[symbol] = float(chosen[1])
    return prices


def _open_meme_prices(conn) -> dict[str, float]:
    """
    Refresh open positions independently of the rotating discovery universe.

    A token may disappear from the top-flow list after entry; stop/target/time exits still
    need a current observed price. This keeps open PAPER positions monitorable until closed.
    """
    rows = conn.execute(
        """
        SELECT DISTINCT symbol,token_address
        FROM paper_trades
        WHERE asset_class='MEME' AND status='OPEN'
          AND token_address IS NOT NULL AND token_address!=''
        """
    ).fetchall()
    if not rows:
        return {}

    addresses = []
    for row in rows:
        address = str(row["token_address"] or "").strip()
        if address and address not in addresses:
            addresses.append(address)

    prices: dict[str, float] = {}
    for start in range(0, len(addresses), 30):
        chunk = addresses[start : start + 30]
        try:
            pairs = _http_json(
                DEXSCREENER_TOKENS.format(addresses=",".join(chunk)),
                timeout=10,
            )
        except Exception as exc:
            print("Open-position price refresh failed:", exc)
            continue
        if isinstance(pairs, list):
            prices.update(_map_open_meme_prices(rows, pairs))
    return prices


def _record_signal(
    conn,
    agent: str,
    asset_class: str,
    idea,
    risk_text: str = "",
    *,
    session_id: int | None = None,
    market_source: str | None = None,
) -> int:
    signals = [
        getattr(idea, "signal_1", ""),
        getattr(idea, "signal_2", ""),
        getattr(idea, "optional_signal_3", ""),
    ]
    signals = [str(x) for x in signals if str(x).strip()]
    cur = conn.execute(
        """
        INSERT INTO trade_signals(
            agent, asset_class, symbol, action, confidence, thesis,
            status, risk_decision, created_at, session_id, token_address,
            trade_mode, setup_score, stress_level, signals_json,
            expected_round_trip_cost_pct, expected_first_move_pct, market_source
        )
        VALUES (?, ?, ?, ?, ?, ?, 'PAPER_ONLY', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            agent,
            asset_class,
            idea.symbol,
            idea.action.upper(),
            idea.confidence,
            idea.thesis,
            risk_text or None,
            now_iso(),
            session_id,
            getattr(idea, "token_address", None),
            getattr(idea, "trade_mode", None),
            getattr(idea, "setup_score", None),
            getattr(idea, "stress_level", None),
            json.dumps(signals, ensure_ascii=False),
            getattr(idea, "expected_round_trip_cost_pct", None),
            getattr(idea, "expected_first_move_pct", None),
            market_source,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _open_paper_trade(
    conn,
    signal_id: int,
    asset_class: str,
    idea,
    notional_usd: float,
    market_price: float | None,
    *,
    session_id: int | None = None,
) -> bool:
    if idea.action.upper() != "BUY" or not market_price:
        return False
    if not idea.stop_price or not idea.take_profit_price:
        return False

    duplicate = conn.execute(
        "SELECT 1 FROM paper_trades WHERE asset_class=? AND symbol=? AND status='OPEN' LIMIT 1",
        (asset_class, idea.symbol),
    ).fetchone()
    if duplicate:
        return False

    max_open = 1
    if asset_class == "MEME":
        try:
            max_open = int(os.getenv("DARWIN_MEME_MAX_OPEN_TRADES", "3"))
        except ValueError:
            max_open = 3
        max_open = max(1, min(max_open, 5))

    open_count = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM paper_trades WHERE asset_class=? AND status='OPEN'",
            (asset_class,),
        ).fetchone()["n"]
        or 0
    )
    if open_count >= max_open:
        return False

    slippage_bps = _sim_slippage_bps(asset_class)
    entry_price = market_price * (1 + slippage_bps / 10000.0)
    if not (idea.stop_price < entry_price < idea.take_profit_price):
        return False

    max_price_risk = 0.10 if asset_class == "MEME" else 0.025
    price_risk_fraction = (entry_price - idea.stop_price) / entry_price
    if price_risk_fraction <= 0 or price_risk_fraction > max_price_risk:
        return False

    max_hold = getattr(idea, "max_hold_minutes", None)
    if asset_class == "STOCK":
        max_hold = 390

    entry_fee = _sim_fee_usd(asset_class, notional_usd)
    initial_risk_usd = notional_usd * price_risk_fraction

    conn.execute(
        """
        INSERT INTO paper_trades(
            signal_id, asset_class, symbol, side, notional_usd,
            entry_price, stop_price, target_price, max_hold_minutes,
            status, gross_pnl_usd, fees_usd, slippage_bps, pnl_usd,
            stop_text, target_text, opened_at, session_id, token_address,
            trade_mode, setup_score, stress_level, risk_pct_equity, initial_risk_usd
        )
        VALUES (?, ?, ?, 'BUY', ?, ?, ?, ?, ?, 'OPEN', 0, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_id,
            asset_class,
            idea.symbol,
            notional_usd,
            entry_price,
            idea.stop_price,
            idea.take_profit_price,
            max_hold,
            entry_fee,
            slippage_bps,
            idea.invalidation,
            idea.take_profit_logic,
            now_iso(),
            session_id,
            getattr(idea, "token_address", None),
            getattr(idea, "trade_mode", None),
            getattr(idea, "setup_score", None),
            getattr(idea, "stress_level", None),
            getattr(idea, "risk_pct", None),
            initial_risk_usd,
        ),
    )
    if session_id is not None:
        conn.execute(
            "UPDATE trading_sessions SET last_trade_at=? WHERE id=?",
            (now_iso(), session_id),
        )
    conn.commit()
    return True


def _close_paper_trades(conn, asset_class: str, prices: dict[str, float]) -> list[str]:
    rows = conn.execute(
        "SELECT * FROM paper_trades WHERE asset_class=? AND status='OPEN'",
        (asset_class,),
    ).fetchall()
    closed = []
    now = datetime.now(timezone.utc)

    for row in rows:
        price = prices.get(row["symbol"])
        if not price:
            continue

        reason = None
        if row["stop_price"] and price <= row["stop_price"]:
            reason = "STOP"
        elif row["target_price"] and price >= row["target_price"]:
            reason = "TARGET"
        else:
            opened = datetime.fromisoformat(row["opened_at"])
            hold_minutes = (now - opened).total_seconds() / 60
            if row["max_hold_minutes"] and hold_minutes >= row["max_hold_minutes"]:
                reason = "TIME"

            if asset_class == "STOCK":
                ny = datetime.now(ZoneInfo("America/New_York"))
                if ny.weekday() < 5 and (ny.hour > 15 or (ny.hour == 15 and ny.minute >= 50)):
                    reason = "EOD"

        if reason:
            slippage_bps = float(row["slippage_bps"] or _sim_slippage_bps(asset_class))
            exit_price = price * (1 - slippage_bps / 10000.0)
            gross_pnl = row["notional_usd"] * (
                (exit_price - row["entry_price"]) / row["entry_price"]
            )
            total_fees = float(row["fees_usd"] or 0) + _sim_fee_usd(
                asset_class, row["notional_usd"]
            )
            pnl = gross_pnl - total_fees
            conn.execute(
                """
                UPDATE paper_trades
                SET exit_price=?, status=?, gross_pnl_usd=?, fees_usd=?,
                    pnl_usd=?, closed_at=?
                WHERE id=?
                """,
                (
                    exit_price,
                    f"CLOSED_{reason}",
                    gross_pnl,
                    total_fees,
                    pnl,
                    now_iso(),
                    row["id"],
                ),
            )
            conn.commit()
            closed.append(
                f"{row['symbol']} {reason} at {exit_price:.8f}; "
                f"gross {gross_pnl:+.2f}, costs {total_fees:.2f}, net {pnl:+.2f} USD"
            )
    return closed


def _daily_paper_pnl(conn, asset_class: str) -> float:
    start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
    row = conn.execute(
        """
        SELECT COALESCE(SUM(pnl_usd), 0) AS pnl
        FROM paper_trades
        WHERE asset_class=? AND closed_at>=?
        """,
        (asset_class, start),
    ).fetchone()
    return float(row["pnl"] or 0)


def _start_trading_session(conn, hours: float) -> int:
    try:
        equity = float(os.getenv("DARWIN_MEME_PAPER_ACCOUNT_USD", "100"))
    except ValueError:
        equity = 100.0
    equity = max(25.0, min(equity, 100000.0))
    cur = conn.execute(
        """
        INSERT INTO trading_sessions(
            started_at,target_hours,status,initial_equity_usd,cycles_completed,
            model_calls_used,stress_level,defensive_mode,note
        )
        VALUES (?,?,'RUNNING',?,0,0,0,0,?)
        """,
        (
            now_iso(),
            hours,
            equity,
            "Six-hour Darwin paper-trading qualification shift. No live execution.",
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _session_state(conn, session_id: int) -> dict:
    session = conn.execute(
        "SELECT * FROM trading_sessions WHERE id=?",
        (session_id,),
    ).fetchone()
    if not session:
        raise RuntimeError("Trading session does not exist.")

    closed = conn.execute(
        """
        SELECT pnl_usd,initial_risk_usd,closed_at
        FROM paper_trades
        WHERE session_id=? AND asset_class='MEME' AND status!='OPEN'
        ORDER BY id
        """,
        (session_id,),
    ).fetchall()

    realized = sum(float(row["pnl_usd"] or 0) for row in closed)
    initial_equity = float(session["initial_equity_usd"] or 100.0)
    one_r = max(initial_equity * 0.01, 0.01)
    realized_r = realized / one_r

    consecutive_losses = 0
    for row in reversed(closed):
        if float(row["pnl_usd"] or 0) < 0:
            consecutive_losses += 1
        else:
            break

    last_trade_at = session["last_trade_at"]
    if last_trade_at:
        last_dt = datetime.fromisoformat(last_trade_at)
    else:
        last_dt = datetime.fromisoformat(session["started_at"])
    minutes_since_trade = max(
        0.0,
        (datetime.now(timezone.utc) - last_dt).total_seconds() / 60.0,
    )

    defensive = consecutive_losses >= 3 or realized_r <= -4.0
    hard_loss_stop = realized_r <= -5.0

    return {
        "initial_equity_usd": initial_equity,
        "realized_pnl_usd": realized,
        "realized_r": realized_r,
        "consecutive_losses": consecutive_losses,
        "minutes_since_trade": minutes_since_trade,
        "defensive_mode": defensive,
        "hard_loss_stop": hard_loss_stop,
    }


def _update_session_runtime(
    conn,
    session_id: int,
    *,
    cycle: int,
    model_calls: int,
    stress_level: int,
    defensive_mode: bool,
) -> None:
    conn.execute(
        """
        UPDATE trading_sessions
        SET cycles_completed=?,model_calls_used=?,stress_level=?,defensive_mode=?
        WHERE id=?
        """,
        (
            cycle,
            model_calls,
            stress_level,
            1 if defensive_mode else 0,
            session_id,
        ),
    )
    conn.commit()


def _risk_review(
    conn,
    asset_class: str,
    idea,
    max_notional: float,
    daily_stop: float,
    *,
    session_state: dict | None = None,
):
    pnl = _daily_paper_pnl(conn, asset_class)
    if pnl <= -abs(daily_stop):
        return None, f"BLOCKED: daily paper loss stop reached ({pnl:+.2f} USD)."

    session_state = session_state or {}
    if session_state.get("hard_loss_stop"):
        return None, (
            "BLOCKED: session hard loss stop reached "
            f"({session_state.get('realized_r', 0):+.2f}R)."
        )

    prompt = f"""
Review this PAPER-trade proposal.

Asset class: {asset_class}
Hard max notional USD: {max_notional:.2f}
Today's realized paper P&L USD: {pnl:.2f}
Daily paper loss stop USD: -{abs(daily_stop):.2f}
Session realized R: {float(session_state.get('realized_r', 0)):.2f}
Consecutive session losses: {int(session_state.get('consecutive_losses', 0))}
Defensive mode: {bool(session_state.get('defensive_mode', False))}

Proposal:
{idea.model_dump_json(indent=2)}

Approve B-quality/probe setups when the proposal satisfies its deterministic score threshold,
two-signal minimum, friction rule, bounded account risk, and explicit exit.
Block ruin-risk, missing identity, oversized risk, broken friction, or hard-stop violations.
This is simulation only; no live order may be placed.
"""
    decision = Runner.run_sync(build_circuit(), prompt).final_output
    if not isinstance(decision, RiskDecision):
        raise RuntimeError("Circuit returned an unexpected output.")
    text = decision.model_dump_json(indent=2)
    if not decision.approved or decision.max_notional_usd <= 0:
        return decision, text
    return decision, text


def _gecko_ohlcv(pool_address: str) -> list[dict]:
    payload = _http_json(GECKO_OHLCV.format(pool_address=pool_address), timeout=8)
    rows = (
        ((payload.get("data") or {}).get("attributes") or {}).get("ohlcv_list")
        if isinstance(payload, dict)
        else None
    ) or []
    candles = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        try:
            candles.append(
                {
                    "timestamp": int(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
            )
        except (TypeError, ValueError):
            continue
    candles.sort(key=lambda x: x["timestamp"])
    return candles[-120:]


def _compact_meme_candidate(details: dict) -> dict:
    keys = [
        "symbol", "token_address", "pool_address", "price_usd", "liquidity_usd",
        "market_cap_usd", "fdv_usd", "age_minutes", "age_bucket", "buys_m5",
        "sells_m5", "buys_h1", "sells_h1", "volume_m5", "volume_h1", "volume_h24",
        "price_change_m5", "price_change_h1", "volume_acceleration",
        "transaction_acceleration", "buy_ratio_m5", "hard_gate_pass",
        "hard_gate_reason", "paper_tradeable", "live_safety_complete",
        "unverified_live_checks", "signals", "signal_count", "setup_score",
        "required_score", "stress_level", "defensive_mode", "suggested_mode",
        "recommended_entry", "recommended_stop", "recommended_target",
        "recommended_risk_pct", "max_position_usd", "expected_round_trip_cost_pct",
        "expected_first_move_pct", "friction_multiple_required", "friction_pass",
        "technical_pass", "max_hold_minutes", "structure",
    ]
    payload = {key: details.get(key) for key in keys}
    payload["ohlcv_1m"] = (details.get("ohlcv_1m") or [])[-45:]
    return payload


def _dexscreener_meme_candidates() -> list[dict]:
    """Continuously rerank new Solana flow instead of using a static watchlist."""
    boosts = _http_json(DEXSCREENER_BOOSTS)
    if not isinstance(boosts, list):
        return []

    addresses = []
    for item in boosts:
        if not isinstance(item, dict):
            continue
        if str(item.get("chainId", "")).lower() != "solana":
            continue
        address = str(item.get("tokenAddress", "")).strip()
        if address and address not in addresses:
            addresses.append(address)
        if len(addresses) >= 40:
            break

    if not addresses:
        return []

    pairs = _http_json(DEXSCREENER_TOKENS.format(addresses=",".join(addresses)))
    if not isinstance(pairs, list):
        return []

    best_by_token = {}
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        base = pair.get("baseToken") or {}
        address = str(base.get("address") or "").strip()
        symbol = str(base.get("symbol") or "").upper().strip()
        price = _number(pair.get("priceUsd"))
        pool_address = str(pair.get("pairAddress") or "").strip()
        liquidity = _number((pair.get("liquidity") or {}).get("usd")) or 0.0

        volume = pair.get("volume") or {}
        volume_m5 = _number(volume.get("m5")) or 0.0
        volume_h1 = _number(volume.get("h1")) or 0.0
        volume_h6 = _number(volume.get("h6")) or 0.0
        volume_h24 = _number(volume.get("h24")) or 0.0

        txns = pair.get("txns") or {}
        m5 = txns.get("m5") or {}
        h1 = txns.get("h1") or {}
        buys_m5 = int(m5.get("buys") or 0)
        sells_m5 = int(m5.get("sells") or 0)
        buys_h1 = int(h1.get("buys") or 0)
        sells_h1 = int(h1.get("sells") or 0)
        activity_h1 = buys_h1 + sells_h1

        price_change = pair.get("priceChange") or {}
        price_change_m5 = float(price_change.get("m5") or 0)
        price_change_h1 = float(price_change.get("h1") or 0)
        price_change_h6 = float(price_change.get("h6") or 0)

        if not address or not symbol or not price or not pool_address:
            continue
        if liquidity < 5000 or volume_h1 < 1000:
            continue

        discovery_rank = (
            volume_m5 * 12.0
            + volume_h1 * 1.5
            + activity_h1 * 120.0
            + liquidity * 0.35
            + abs(price_change_h1) * 800.0
        )
        current = best_by_token.get(address)
        if current is None or discovery_rank > current["discovery_rank"]:
            best_by_token[address] = {
                "discovery_rank": discovery_rank,
                "symbol": symbol,
                "token_id": address,
                "price": price,
                "pool_address": pool_address,
                "liquidity_usd": liquidity,
                "market_cap_usd": _number(pair.get("marketCap")),
                "fdv_usd": _number(pair.get("fdv")),
                "pair_created_at": pair.get("pairCreatedAt"),
                "volume_m5": volume_m5,
                "volume_h1": volume_h1,
                "volume_h6": volume_h6,
                "volume_h24": volume_h24,
                "buys_m5": buys_m5,
                "sells_m5": sells_m5,
                "buys_h1": buys_h1,
                "sells_h1": sells_h1,
                "activity_h1": activity_h1,
                "price_change_m5": price_change_m5,
                "price_change_h1": price_change_h1,
                "price_change_h6": price_change_h6,
            }

    try:
        candidate_limit = int(os.getenv("DARWIN_MEME_CANDIDATES", "10"))
    except ValueError:
        candidate_limit = 10
    candidate_limit = max(5, min(candidate_limit, 15))
    return sorted(
        best_by_token.values(),
        key=lambda x: x["discovery_rank"],
        reverse=True,
    )[:candidate_limit]


def _meme_market_bundle(conn, *, session_state: dict):
    raw_candidates = _dexscreener_meme_candidates()
    if not raw_candidates:
        return [], {}, "dexscreener+geckoterminal", 0

    active_candidates = [
        c for c in raw_candidates
        if float(c.get("liquidity_usd") or 0) >= 15000
        and int(c.get("activity_h1") or 0) >= 20
    ]
    stress_level = compute_stress_level(
        minutes_since_trade=float(session_state["minutes_since_trade"]),
        active_market=len(active_candidates) >= 2,
        consecutive_losses=int(session_state["consecutive_losses"]),
        defensive_mode=bool(session_state["defensive_mode"]),
    )

    try:
        max_notional = float(os.getenv("DARWIN_MEME_PAPER_NOTIONAL_USD", "40"))
    except ValueError:
        max_notional = 40.0
    max_notional = max(5.0, min(max_notional, 5000.0))

    hydrated = []
    prices = {}
    for candidate in raw_candidates:
        symbol = candidate["symbol"]
        price = candidate["price"]
        prices[symbol] = price
        try:
            candles = _gecko_ohlcv(candidate["pool_address"])
            ohlcv_error = None
        except Exception as exc:
            candles = []
            ohlcv_error = str(exc)[:300]

        hydrated.append(
            {
                "market_source": "dexscreener+geckoterminal",
                "symbol": symbol,
                "token_address": candidate["token_id"],
                "pool_address": candidate["pool_address"],
                "price_usd": price,
                "liquidity_usd": candidate["liquidity_usd"],
                "market_cap_usd": candidate.get("market_cap_usd"),
                "fdv_usd": candidate.get("fdv_usd"),
                "pair_created_at": candidate.get("pair_created_at"),
                "volume_m5": candidate.get("volume_m5", 0),
                "volume_h1": candidate.get("volume_h1", 0),
                "volume_h6": candidate.get("volume_h6", 0),
                "volume_h24": candidate.get("volume_h24", 0),
                "buys_m5": candidate.get("buys_m5", 0),
                "sells_m5": candidate.get("sells_m5", 0),
                "buys_h1": candidate.get("buys_h1", 0),
                "sells_h1": candidate.get("sells_h1", 0),
                "activity_h1": candidate.get("activity_h1", 0),
                "price_change_m5": candidate.get("price_change_m5", 0),
                "price_change_h1": candidate.get("price_change_h1", 0),
                "price_change_h6": candidate.get("price_change_h6", 0),
                "ohlcv_1m": candles,
                "ohlcv_error": ohlcv_error,
            }
        )

    scored = score_candidates(
        hydrated,
        stress_level=stress_level,
        account_equity_usd=float(session_state["initial_equity_usd"]),
        defensive_mode=bool(session_state["defensive_mode"]),
        max_notional_usd=max_notional,
    )

    for details in scored:
        _snapshot(
            conn,
            "MEME",
            str(details["symbol"]),
            "dexscreener+geckoterminal",
            float(details["price_usd"]),
            details,
        )
        details["local_price_history"] = _history(conn, "MEME", str(details["symbol"]), 40)

    return scored, prices, "dexscreener+geckoterminal", stress_level


def _moonshot_cycle(
    conn,
    model_budget: list[int],
    max_model_calls: int,
    *,
    session_id: int,
    session_state: dict,
) -> tuple[bool, int]:
    _set_agent(
        conn,
        "Raptor",
        "WORKING",
        "Reranking live Solana flow • adaptive stress • paper only",
    )
    try:
        bundle, prices, market_source, stress_level = _meme_market_bundle(
            conn,
            session_state=session_state,
        )

        # Open positions are monitored even when they drop out of the rotating discovery list.
        prices.update(_open_meme_prices(conn))

        for line in _close_paper_trades(conn, "MEME", prices):
            print("Raptor paper exit:", line)

        if not bundle:
            _set_agent(conn, "Raptor", "READY", "No tradeable Solana candidates in current flow")
            return False, stress_level

        open_rows = conn.execute(
            "SELECT symbol FROM paper_trades WHERE asset_class='MEME' AND status='OPEN'"
        ).fetchall()
        open_symbols = {str(row["symbol"]).upper() for row in open_rows}
        qualified = [
            item for item in bundle
            if item.get("technical_pass")
            and str(item.get("symbol") or "").upper() not in open_symbols
        ]

        threshold = required_score(stress_level, bool(session_state["defensive_mode"]))
        print(
            f"Raptor flow: {len(bundle)} ranked candidate(s); "
            f"{len(qualified)} meet stress-{stress_level} threshold (score >= {threshold})."
        )
        for item in bundle[:5]:
            state = "READY" if item["technical_pass"] else (
                item["hard_gate_reason"] if not item["hard_gate_pass"] else "WATCH"
            )
            print(
                f"  {item['symbol']}: score {item['setup_score']}/{item['required_score']} • "
                f"signals {item['signal_count']} • friction {item['expected_round_trip_cost_pct']:.2f}% • "
                f"move {item['expected_first_move_pct']:.2f}% • {state}"
            )

        if session_state.get("hard_loss_stop"):
            best = bundle[0]
            idea = MemeTradeIdea(
                symbol=str(best["symbol"]),
                token_address=str(best.get("token_address") or ""),
                action="WAIT",
                trade_mode="NONE",
                setup_score=int(best["setup_score"]),
                stress_level=stress_level,
                confidence=100,
                thesis="Session hard loss stop is active. Observation only.",
                signal_1="session_loss_stop",
                signal_2="no_new_risk",
                support_evidence="Trading is disabled for the rest of this session.",
                momentum_evidence="Market observation continues without new positions.",
                invalidation="No paper entry while hard loss stop is active.",
                expected_round_trip_cost_pct=float(best["expected_round_trip_cost_pct"]),
                expected_first_move_pct=float(best["expected_first_move_pct"]),
                risk_pct=0,
                position_size_usd=0,
                take_profit_logic="Not applicable.",
                runner_plan="Not applicable.",
                max_hold_minutes=15,
            )
            _record_signal(
                conn, "Raptor", "MEME", idea,
                "Circuit not called: session hard loss stop.",
                session_id=session_id, market_source=market_source,
            )
            _set_agent(conn, "Raptor", "READY", "Session loss stop active; observing only")
            return False, stress_level

        if not qualified:
            best = bundle[0]
            signals = list(best.get("signals") or [])
            idea = MemeTradeIdea(
                symbol=str(best["symbol"]),
                token_address=str(best.get("token_address") or ""),
                action="WAIT" if best.get("hard_gate_pass") else "REJECT",
                trade_mode="NONE",
                setup_score=int(best["setup_score"]),
                stress_level=stress_level,
                confidence=85,
                thesis=(
                    f"Best score {best['setup_score']} vs required {best['required_score']}; "
                    f"signals={signals}; friction pass={best['friction_pass']}."
                ),
                signal_1=signals[0] if len(signals) > 0 else "no_positive_signal",
                signal_2=signals[1] if len(signals) > 1 else "needs_second_signal",
                optional_signal_3=signals[2] if len(signals) > 2 else "",
                support_evidence=str((best.get("structure") or {}).get("support")),
                momentum_evidence=(
                    f"5m={best.get('price_change_m5')}%; h1={best.get('price_change_h1')}%; "
                    f"volume accel={best.get('volume_acceleration')}x; "
                    f"transaction accel={best.get('transaction_acceleration')}x"
                ),
                invalidation="No position opened.",
                expected_round_trip_cost_pct=float(best["expected_round_trip_cost_pct"]),
                expected_first_move_pct=float(best["expected_first_move_pct"]),
                risk_pct=0,
                position_size_usd=0,
                take_profit_logic="Not applicable while waiting.",
                runner_plan="Not applicable.",
                max_hold_minutes=15,
            )
            _record_signal(
                conn, "Raptor", "MEME", idea,
                "Circuit not called: adaptive technical threshold not met.",
                session_id=session_id, market_source=market_source,
            )
            _set_agent(
                conn, "Raptor", "READY",
                f"Watching {best['symbol']} • score {best['setup_score']}/{best['required_score']} • stress {stress_level}/4",
            )
            return False, stress_level

        if model_budget[0] + 2 > max_model_calls:
            _set_agent(conn, "Raptor", "READY", "Qualified setup found but model-call guardrail is exhausted")
            return False, stress_level

        model_view = [_compact_meme_candidate(item) for item in qualified[:3]]
        idea = Runner.run_sync(
            build_raptor(),
            (
                "Choose at most one PAPER trade from the ranked candidates below. "
                "They already passed deterministic hard gates, adaptive setup score, two-signal minimum, "
                "and execution-friction tests. BUY a valid opportunity unless you can name a concrete "
                "contradiction in the supplied data. Do not wait for perfection.\n\n"
                + json.dumps(model_view, ensure_ascii=False)[:65000]
            ),
        ).final_output
        model_budget[0] += 1
        if not isinstance(idea, MemeTradeIdea):
            raise RuntimeError("Raptor returned an unexpected output.")

        lookup = {str(item["symbol"]).upper(): item for item in qualified}
        chosen = lookup.get(str(idea.symbol).upper())
        if idea.action == "BUY" and not chosen:
            idea = idea.model_copy(
                update={
                    "action": "REJECT",
                    "trade_mode": "NONE",
                    "thesis": "Raptor selected a symbol outside Darwin's qualified candidate set.",
                    "risk_pct": 0,
                    "position_size_usd": 0,
                }
            )

        if chosen:
            signals = list(chosen.get("signals") or [])
            idea = idea.model_copy(
                update={
                    "token_address": chosen.get("token_address"),
                    "setup_score": int(chosen["setup_score"]),
                    "stress_level": stress_level,
                    "trade_mode": chosen["suggested_mode"] if idea.action == "BUY" else idea.trade_mode,
                    "entry_price": chosen["recommended_entry"] if idea.action == "BUY" else idea.entry_price,
                    "stop_price": chosen["recommended_stop"] if idea.action == "BUY" else idea.stop_price,
                    "take_profit_price": chosen["recommended_target"] if idea.action == "BUY" else idea.take_profit_price,
                    "expected_round_trip_cost_pct": chosen["expected_round_trip_cost_pct"],
                    "expected_first_move_pct": chosen["expected_first_move_pct"],
                    "risk_pct": chosen["recommended_risk_pct"] if idea.action == "BUY" else 0,
                    "position_size_usd": chosen["max_position_usd"] if idea.action == "BUY" else 0,
                    "max_hold_minutes": chosen["max_hold_minutes"] if idea.action == "BUY" else idea.max_hold_minutes,
                    "signal_1": signals[0] if len(signals) > 0 else idea.signal_1,
                    "signal_2": signals[1] if len(signals) > 1 else idea.signal_2,
                    "optional_signal_3": signals[2] if len(signals) > 2 else idea.optional_signal_3,
                }
            )

        print(
            f"Raptor decision: {idea.action} {idea.symbol} • {idea.trade_mode} • "
            f"score {idea.setup_score} • stress {idea.stress_level}/4"
        )

        if idea.action != "BUY" or not chosen:
            _record_signal(
                conn, "Raptor", "MEME", idea,
                "Circuit not called: no BUY proposal.",
                session_id=session_id, market_source=market_source,
            )
            _set_agent(
                conn, "Raptor", "READY",
                f"{idea.action} {idea.symbol} • score {idea.setup_score} • {idea.thesis[:90]}",
            )
            return False, stress_level

        try:
            absolute_max = float(os.getenv("DARWIN_MEME_PAPER_NOTIONAL_USD", "40"))
        except ValueError:
            absolute_max = 40.0

        decision, risk_text = _risk_review(
            conn,
            "MEME",
            idea,
            max_notional=min(absolute_max, float(chosen["max_position_usd"])),
            daily_stop=float(os.getenv("DARWIN_MEME_PAPER_DAILY_STOP_USD", "6")),
            session_state=session_state,
        )
        model_budget[0] += 1

        signal_id = _record_signal(
            conn, "Raptor", "MEME", idea, risk_text,
            session_id=session_id, market_source=market_source,
        )

        opened = False
        if decision and decision.approved:
            cap = min(
                absolute_max,
                float(chosen["max_position_usd"]),
                float(idea.position_size_usd),
                float(decision.max_notional_usd),
            )
            opened = _open_paper_trade(
                conn,
                signal_id,
                "MEME",
                idea,
                cap,
                prices.get(str(idea.symbol).upper()),
                session_id=session_id,
            )

        _set_agent(
            conn,
            "Raptor",
            "READY",
            (
                f"{idea.trade_mode} {idea.symbol} • score {idea.setup_score} • "
                + ("PAPER TRADE OPEN" if opened else "risk gate/no fill")
            ),
        )
        if opened:
            print(
                f"Raptor paper entry: {idea.symbol} • {idea.trade_mode} • "
                f"USD {min(float(idea.position_size_usd), float(decision.max_notional_usd)):.2f} notional • "
                f"risk {idea.risk_pct:.2f}% equity"
            )
        return opened, stress_level

    except Exception as exc:
        _set_agent(conn, "Raptor", "READY", f"Solana scan error: {str(exc)[:140]}")
        print("Raptor Solana scan error:", exc)
        return False, 0


def _alpaca_bars(symbols: list[str]):
    key = os.getenv("ALPACA_PAPER_API_KEY", "").strip()
    secret = os.getenv("ALPACA_PAPER_API_SECRET", "").strip()
    if not key or not secret:
        raise RuntimeError("Alpaca paper credentials are not configured.")

    start = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    query = urlencode(
        {
            "symbols": ",".join(symbols),
            "timeframe": "1Min",
            "start": start,
            "limit": 1000,
            "feed": "iex",
            "sort": "asc",
        }
    )
    return _http_json(
        f"{ALPACA_DATA}/v2/stocks/bars?{query}",
        headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "User-Agent": "DarwinIndustries/1.0",
        },
    )


def _stock_cycle(conn, model_budget: list[int], max_model_calls: int) -> None:
    watchlist = [
        s.strip().upper()
        for s in os.getenv("DARWIN_STOCK_WATCHLIST", "").split(",")
        if s.strip()
    ]
    if not watchlist:
        _set_agent(
            conn,
            "Apex",
            "WAITING_CONFIG",
            "Set DARWIN_STOCK_WATCHLIST and Alpaca paper credentials",
        )
        return

    _set_agent(conn, "Apex", "WORKING", "Scanning configured equities with Alpaca paper data")
    try:
        data = _alpaca_bars(watchlist[:15])
        bars_by_symbol = data.get("bars", {}) if isinstance(data, dict) else {}
        bundle = []
        prices = {}

        for symbol, bars in bars_by_symbol.items():
            if not bars:
                continue
            latest = bars[-1]
            price = _number(latest.get("c"))
            if price:
                prices[symbol] = price
            _snapshot(conn, "STOCK", symbol, "alpaca_iex", price, bars[-60:])
            bundle.append(
                {
                    "symbol": symbol,
                    "bars_1m": bars[-60:],
                    "local_price_history": _history(conn, "STOCK", symbol, 30),
                }
            )

        for line in _close_paper_trades(conn, "STOCK", prices):
            print("Apex paper exit:", line)

        if not bundle or model_budget[0] + 2 > max_model_calls:
            _set_agent(conn, "Apex", "READY", "Stock scan complete; no setup review")
            return

        idea = Runner.run_sync(
            build_apex(),
            "Choose at most one PAPER intraday setup from these live 1-minute bars. "
            "If no setup is strong, WAIT.\n\n"
            + json.dumps(bundle, ensure_ascii=False)[:80000],
        ).final_output
        model_budget[0] += 1
        if not isinstance(idea, StockTradeIdea):
            raise RuntimeError("Apex returned an unexpected output.")

        print(
            f"Apex decision: {idea.action} {idea.symbol} "
            f"(confidence {idea.confidence})"
        )

        if idea.action.upper() != "BUY":
            _record_signal(conn, "Apex", "STOCK", idea, "Circuit not called: no BUY proposal.")
            _set_agent(
                conn,
                "Apex",
                "READY",
                f"Equity paper decision: {idea.action} {idea.symbol}; no paper trade opened",
            )
            print("Circuit: skipped — no BUY proposal to risk-review.")
            return

        decision, risk_text = _risk_review(
            conn,
            "STOCK",
            idea,
            max_notional=float(os.getenv("DARWIN_STOCK_PAPER_NOTIONAL_USD", "100")),
            daily_stop=float(os.getenv("DARWIN_STOCK_PAPER_DAILY_STOP_USD", "20")),
        )
        model_budget[0] += 1

        signal_id = _record_signal(conn, "Apex", "STOCK", idea, risk_text)
        opened = False
        if decision and decision.approved:
            cap = min(
                float(os.getenv("DARWIN_STOCK_PAPER_NOTIONAL_USD", "100")),
                decision.max_notional_usd,
            )
            opened = _open_paper_trade(
                conn,
                signal_id,
                "STOCK",
                idea,
                cap,
                prices.get(idea.symbol.upper()),
            )

        _set_agent(
            conn,
            "Apex",
            "READY",
            f"Equity paper decision: {idea.action} {idea.symbol}; "
            + ("paper trade opened" if opened else "no paper trade opened"),
        )
    except Exception as exc:
        _set_agent(conn, "Apex", "READY", f"Stock scan error: {str(exc)[:140]}")
        print("Apex scan error:", exc)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Darwin's experimental trading desk in paper mode."
    )
    parser.add_argument("--hours", type=float, default=6.0)
    parser.add_argument("--interval-minutes", type=int, default=3)
    parser.add_argument("--max-model-calls", type=int, default=120)
    args = parser.parse_args()

    load_dotenv()
    mode = os.getenv("DARWIN_TRADING_MODE", "paper").strip().lower()
    if mode != "paper":
        raise SystemExit(
            "Darwin trading desk currently supports PAPER mode only. "
            "Live autonomous order execution is intentionally not implemented."
        )
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing from .env")

    hours = max(0.25, min(args.hours, 6.0))
    interval = max(1, min(args.interval_minutes, 60))
    max_model_calls = max(2, min(args.max_model_calls, 120))

    conn = connect()
    init_db(conn)
    session_id = _start_trading_session(conn, hours)
    _set_agent(conn, "Raptor", "ON_SHIFT", "Six-hour adaptive Solana paper-trading shift")
    _set_agent(conn, "Apex", "ON_SHIFT", "Paper-trading intraday equities desk")
    _set_agent(conn, "Circuit", "ON_SHIFT", "Independent paper-trading risk control")

    deadline = datetime.now() + timedelta(hours=hours)
    model_budget = [0]
    cycle = 0

    print("\n=== DARWIN TRADING DESK — PAPER MODE ===")
    print("Raptor: adaptive Solana flow trader (DEX Screener + 1m GeckoTerminal data)")
    print("Apex: intraday equities scanner (Alpaca paper data + owner watchlist)")
    print("Circuit: independent risk gate")
    print("REAL MONEY EXECUTION: DISABLED")
    print("Fake fills use observed prices plus configurable route fees/slippage.")
    print("Raptor uses hard paper tradeability gates + adaptive technical stress 0-4.")
    print("Shift length is capped at 6 hours; hitting the model budget does NOT stop market observation.")
    print(f"Scan interval: {interval} minute(s)")
    print(f"Model-call guardrail: {max_model_calls}")
    print("Press Ctrl+C to stop safely.\n")

    try:
        while datetime.now() < deadline:
            cycle += 1
            state = _session_state(conn, session_id)
            print(
                f"--- Trading scan {cycle} • session {state['realized_r']:+.2f}R "
                f"• losses {state['consecutive_losses']} ---"
            )

            _set_agent(conn, "Circuit", "WORKING", "Standing by to risk-review bounded paper setups")
            opened, stress_level = _moonshot_cycle(
                conn,
                model_budget,
                max_model_calls,
                session_id=session_id,
                session_state=state,
            )

            # Expose strategy stress separately from the simulated personality field.
            conn.execute(
                "UPDATE agent_state SET stress=?,updated_at=? WHERE agent='Raptor'",
                (min(100, stress_level * 20), now_iso()),
            )
            conn.commit()

            # Apex shares the six-hour desk shift. If its broker config is absent it simply sleeps.
            _stock_cycle(conn, model_budget, max_model_calls)
            _set_agent(conn, "Circuit", "READY", "Paper risk reviews complete")

            refreshed = _session_state(conn, session_id)
            _update_session_runtime(
                conn,
                session_id,
                cycle=cycle,
                model_calls=model_budget[0],
                stress_level=stress_level,
                defensive_mode=bool(refreshed["defensive_mode"]),
            )

            print(
                f"Model calls used: {model_budget[0]}/{max_model_calls} • "
                f"stress {stress_level}/4 • "
                f"defensive {'YES' if refreshed['defensive_mode'] else 'NO'} • "
                f"session {refreshed['realized_r']:+.2f}R"
            )
            if model_budget[0] >= max_model_calls:
                print("Model-call budget exhausted: deterministic scanning/exits continue; no new LLM reviews.")

            if datetime.now() >= deadline:
                break
            sleep_seconds = min(
                interval * 60,
                max(1, int((deadline - datetime.now()).total_seconds())),
            )
            next_scan = datetime.now() + timedelta(seconds=sleep_seconds)
            print(
                f"Next scan in about {sleep_seconds // 60} minute(s) "
                f"at {next_scan.strftime('%H:%M:%S')}.\n"
            )
            time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        print("\nTrading desk stopped by owner.")
    finally:
        conn.execute(
            "UPDATE trading_sessions SET status='COMPLETED',ended_at=?,model_calls_used=?,cycles_completed=? WHERE id=?",
            (now_iso(), model_budget[0], cycle, session_id),
        )
        conn.commit()
        _set_agent(conn, "Raptor", "OFF_SHIFT", "Six-hour paper trading shift stopped")
        _set_agent(conn, "Apex", "OFF_SHIFT", "Six-hour paper trading shift stopped")
        _set_agent(conn, "Circuit", "OFF_SHIFT", "Six-hour paper trading shift stopped")
        conn.close()


if __name__ == "__main__":
    main()
