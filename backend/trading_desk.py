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
from backend.storage import connect, init_db, now_iso


MOONSHOT_TRENDING = "https://api.moonshot.cc/tokens/v1/trending/solana"
MOONSHOT_TRADES = "https://api.moonshot.cc/trades/v1/latest/solana/{token_id}"
ALPACA_DATA = "https://data.alpaca.markets"
DEXSCREENER_BOOSTS = "https://api.dexscreener.com/token-boosts/top/v1"
DEXSCREENER_TOKENS = "https://api.dexscreener.com/tokens/v1/solana/{addresses}"


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
        mode = os.getenv("DARWIN_MEME_SIM_FEE_MODE", "moonshot_app").strip().lower()
        if mode == "moonshot_app":
            if notional_usd <= 100:
                return max(0.99, notional_usd * 0.025)
            return notional_usd * 0.01
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


def _record_signal(conn, agent: str, asset_class: str, idea, risk_text: str = "") -> int:
    cur = conn.execute(
        """
        INSERT INTO trade_signals(
            agent, asset_class, symbol, action, confidence, thesis,
            status, risk_decision, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'PAPER_ONLY', ?, ?)
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
) -> bool:
    if idea.action.upper() != "BUY" or not market_price:
        return False
    if not idea.stop_price or not idea.take_profit_price:
        return False

    existing = conn.execute(
        "SELECT 1 FROM paper_trades WHERE asset_class=? AND status='OPEN' LIMIT 1",
        (asset_class,),
    ).fetchone()
    if existing:
        return False

    slippage_bps = _sim_slippage_bps(asset_class)
    entry_price = market_price * (1 + slippage_bps / 10000.0)
    if not (idea.stop_price < entry_price < idea.take_profit_price):
        return False

    max_risk_pct = 0.06 if asset_class == "MEME" else 0.025
    risk_pct = (entry_price - idea.stop_price) / entry_price
    if risk_pct <= 0 or risk_pct > max_risk_pct:
        return False

    max_hold = getattr(idea, "max_hold_minutes", None)
    if asset_class == "STOCK":
        max_hold = 390

    entry_fee = _sim_fee_usd(asset_class, notional_usd)

    conn.execute(
        """
        INSERT INTO paper_trades(
            signal_id, asset_class, symbol, side, notional_usd,
            entry_price, stop_price, target_price, max_hold_minutes,
            status, gross_pnl_usd, fees_usd, slippage_bps, pnl_usd,
            stop_text, target_text, opened_at
        )
        VALUES (?, ?, ?, 'BUY', ?, ?, ?, ?, ?, 'OPEN', 0, ?, ?, 0, ?, ?, ?)
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
        ),
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


def _risk_review(conn, asset_class: str, idea, max_notional: float, daily_stop: float):
    pnl = _daily_paper_pnl(conn, asset_class)
    if pnl <= -abs(daily_stop):
        return None, f"BLOCKED: daily paper loss stop reached ({pnl:+.2f} USD)."

    prompt = f"""
Review this PAPER-trade proposal.

Asset class: {asset_class}
Hard max notional USD: {max_notional:.2f}
Today's realized paper P&L USD: {pnl:.2f}
Daily paper loss stop USD: -{abs(daily_stop):.2f}

Proposal:
{idea.model_dump_json(indent=2)}

Approve only if the setup has explicit entry, stop, target, bounded size and exit.
This is simulation only; no live order may be placed.
"""
    decision = Runner.run_sync(build_circuit(), prompt).final_output
    if not isinstance(decision, RiskDecision):
        raise RuntimeError("Circuit returned an unexpected output.")
    text = decision.model_dump_json(indent=2)
    if not decision.approved or decision.max_notional_usd <= 0:
        return decision, text
    return decision, text


def _dexscreener_meme_candidates() -> list[dict]:
    """
    Fallback market feed when Moonshot's legacy api.moonshot.cc hostname is unavailable.
    Uses DEX Screener's public Solana endpoints and returns liquid, actively traded candidates.
    """
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
        if len(addresses) >= 20:
            break

    if not addresses:
        return []

    pairs = _http_json(
        DEXSCREENER_TOKENS.format(addresses=",".join(addresses))
    )
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
        liquidity = _number((pair.get("liquidity") or {}).get("usd")) or 0.0
        volume_h24 = _number((pair.get("volume") or {}).get("h24")) or 0.0
        txns_h1 = pair.get("txns") or {}
        h1 = txns_h1.get("h1") or {}
        activity = int(h1.get("buys") or 0) + int(h1.get("sells") or 0)

        if not address or not symbol or not price:
            continue
        # Avoid ultra-thin pools in the simulation.
        if liquidity < 10000 or volume_h24 < 10000:
            continue

        rank = liquidity + volume_h24 + activity * 100
        current = best_by_token.get(address)
        if current is None or rank > current["rank"]:
            best_by_token[address] = {
                "rank": rank,
                "symbol": symbol,
                "token_id": address,
                "price": price,
                "payload": pair,
                "liquidity_usd": liquidity,
                "volume_h24": volume_h24,
                "activity_h1": activity,
            }

    return sorted(
        best_by_token.values(),
        key=lambda x: x["rank"],
        reverse=True,
    )[:6]


def _meme_market_bundle(conn):
    """
    Prefer Moonshot's documented public API. If its hostname cannot be resolved or reached,
    automatically fall back to DEX Screener's public Solana market API.
    """
    bundle = []
    prices = {}
    source = "moonshot"

    try:
        trending = _http_json(MOONSHOT_TRENDING)
        tokens = trending if isinstance(trending, list) else trending.get("data", [])

        for token in list(tokens)[:6]:
            if not isinstance(token, dict):
                continue
            symbol, token_id, price = _token_identity(token)
            if not symbol:
                continue
            details = {"token": token, "market_source": "moonshot"}
            if token_id:
                try:
                    details["latest_trades"] = _http_json(
                        MOONSHOT_TRADES.format(token_id=token_id)
                    )
                except Exception as exc:
                    details["trades_error"] = str(exc)
            _snapshot(conn, "MEME", symbol, "moonshot", price, details)
            if price:
                prices[symbol] = price
            details["local_price_history"] = _history(conn, "MEME", symbol, 30)
            bundle.append(details)

        if bundle:
            return bundle, prices, source
    except Exception as exc:
        source = "dexscreener_fallback"
        print(
            "Moonshot market API unavailable; switching to DEX Screener Solana fallback:",
            exc,
        )

    for candidate in _dexscreener_meme_candidates():
        symbol = candidate["symbol"]
        price = candidate["price"]
        details = {
            "market_source": "dexscreener_fallback",
            "token_address": candidate["token_id"],
            "pair": candidate["payload"],
            "liquidity_usd": candidate["liquidity_usd"],
            "volume_h24": candidate["volume_h24"],
            "activity_h1": candidate["activity_h1"],
        }
        _snapshot(conn, "MEME", symbol, "dexscreener", price, details)
        prices[symbol] = price
        details["local_price_history"] = _history(conn, "MEME", symbol, 30)
        bundle.append(details)

    return bundle, prices, source


def _moonshot_cycle(conn, model_budget: list[int], max_model_calls: int) -> None:
    _set_agent(conn, "Raptor", "WORKING", "Scanning live Solana meme market data for paper setups")
    try:
        bundle, prices, market_source = _meme_market_bundle(conn)

        for line in _close_paper_trades(conn, "MEME", prices):
            print("Raptor paper exit:", line)

        if not bundle or model_budget[0] + 2 > max_model_calls:
            _set_agent(conn, "Raptor", "READY", "Moonshot scan complete; no setup review")
            return

        idea = Runner.run_sync(
            build_raptor(),
            "Choose at most one PAPER setup from these Moonshot market snapshots. "
            "Repeated support must be evidenced by local_price_history; if it is not, WAIT.\n\n"
            + json.dumps(bundle, ensure_ascii=False)[:80000],
        ).final_output
        model_budget[0] += 1
        if not isinstance(idea, MemeTradeIdea):
            raise RuntimeError("Raptor returned an unexpected output.")

        decision, risk_text = _risk_review(
            conn,
            "MEME",
            idea,
            max_notional=float(os.getenv("DARWIN_MEME_PAPER_NOTIONAL_USD", "10")),
            daily_stop=float(os.getenv("DARWIN_MEME_PAPER_DAILY_STOP_USD", "5")),
        )
        model_budget[0] += 1

        signal_id = _record_signal(conn, "Raptor", "MEME", idea, risk_text)
        opened = False
        if decision and decision.approved:
            cap = min(
                float(os.getenv("DARWIN_MEME_PAPER_NOTIONAL_USD", "10")),
                decision.max_notional_usd,
            )
            opened = _open_paper_trade(
                conn,
                signal_id,
                "MEME",
                idea,
                cap,
                prices.get(idea.symbol.upper()),
            )

        _set_agent(
            conn,
            "Raptor",
            "READY",
            f"Meme paper decision ({market_source}): {idea.action} {idea.symbol}; "
            + ("paper trade opened" if opened else "no paper trade opened"),
        )
    except Exception as exc:
        _set_agent(conn, "Raptor", "READY", f"Moonshot scan error: {str(exc)[:140]}")
        print("Raptor scan error:", exc)


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
    parser.add_argument("--interval-minutes", type=int, default=5)
    parser.add_argument("--max-model-calls", type=int, default=30)
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

    hours = max(0.25, min(args.hours, 12.0))
    interval = max(1, min(args.interval_minutes, 60))
    max_model_calls = max(2, min(args.max_model_calls, 120))

    conn = connect()
    init_db(conn)
    _set_agent(conn, "Raptor", "ON_SHIFT", "Paper-trading Moonshot momentum desk")
    _set_agent(conn, "Apex", "ON_SHIFT", "Paper-trading intraday equities desk")
    _set_agent(conn, "Circuit", "ON_SHIFT", "Independent paper-trading risk control")

    deadline = datetime.now() + timedelta(hours=hours)
    model_budget = [0]
    cycle = 0

    print("\n=== DARWIN TRADING DESK — PAPER MODE ===")
    print("Raptor: Moonshot public-data meme momentum scanner")
    print("Apex: intraday equities scanner (Alpaca paper data + owner watchlist)")
    print("Circuit: independent risk gate")
    print("REAL MONEY EXECUTION: DISABLED")
    print("Fake fills use observed prices plus configurable slippage and fees.")
    print(f"Scan interval: {interval} minute(s)")
    print(f"Model-call guardrail: {max_model_calls}")
    print("Press Ctrl+C to stop safely.\n")

    try:
        while datetime.now() < deadline:
            if model_budget[0] + 2 > max_model_calls:
                print(f"Model-call guardrail reached: {model_budget[0]}/{max_model_calls}.")
                break

            cycle += 1
            print(f"--- Trading scan {cycle} ---")
            _set_agent(conn, "Circuit", "WORKING", "Standing by to risk-review paper setups")
            _moonshot_cycle(conn, model_budget, max_model_calls)
            _stock_cycle(conn, model_budget, max_model_calls)
            _set_agent(conn, "Circuit", "READY", "Paper risk reviews complete")
            print(f"Model calls used: {model_budget[0]}/{max_model_calls}")

            if datetime.now() >= deadline:
                break
            time.sleep(
                min(
                    interval * 60,
                    max(1, int((deadline - datetime.now()).total_seconds())),
                )
            )
    except KeyboardInterrupt:
        print("\nTrading desk stopped by owner.")
    finally:
        _set_agent(conn, "Raptor", "OFF_SHIFT", "Paper trading desk stopped")
        _set_agent(conn, "Apex", "OFF_SHIFT", "Paper trading desk stopped")
        _set_agent(conn, "Circuit", "OFF_SHIFT", "Paper trading desk stopped")
        conn.close()


if __name__ == "__main__":
    main()
