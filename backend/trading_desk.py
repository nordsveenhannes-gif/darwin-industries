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


def _open_paper_trade(conn, signal_id: int, asset_class: str, idea, notional_usd: float) -> bool:
    if idea.action.upper() != "BUY":
        return False
    if not idea.entry_price or not idea.stop_price or not idea.take_profit_price:
        return False
    if not (idea.stop_price < idea.entry_price < idea.take_profit_price):
        return False

    existing = conn.execute(
        "SELECT 1 FROM paper_trades WHERE asset_class=? AND status='OPEN' LIMIT 1",
        (asset_class,),
    ).fetchone()
    if existing:
        return False

    max_risk_pct = 0.06 if asset_class == "MEME" else 0.025
    risk_pct = (idea.entry_price - idea.stop_price) / idea.entry_price
    if risk_pct <= 0 or risk_pct > max_risk_pct:
        return False

    max_hold = getattr(idea, "max_hold_minutes", None)
    if asset_class == "STOCK":
        max_hold = 390

    conn.execute(
        """
        INSERT INTO paper_trades(
            signal_id, asset_class, symbol, side, notional_usd,
            entry_price, stop_price, target_price, max_hold_minutes,
            status, pnl_usd, stop_text, target_text, opened_at
        )
        VALUES (?, ?, ?, 'BUY', ?, ?, ?, ?, ?, 'OPEN', 0, ?, ?, ?)
        """,
        (
            signal_id,
            asset_class,
            idea.symbol,
            notional_usd,
            idea.entry_price,
            idea.stop_price,
            idea.take_profit_price,
            max_hold,
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
            pnl = row["notional_usd"] * ((price - row["entry_price"]) / row["entry_price"])
            conn.execute(
                """
                UPDATE paper_trades
                SET exit_price=?, status=?, pnl_usd=?, closed_at=?
                WHERE id=?
                """,
                (price, f"CLOSED_{reason}", pnl, now_iso(), row["id"]),
            )
            conn.commit()
            closed.append(
                f"{row['symbol']} {reason} at {price:.8f}; paper P&L {pnl:+.2f} USD"
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


def _moonshot_cycle(conn, model_budget: list[int], max_model_calls: int) -> None:
    _set_agent(conn, "Raptor", "WORKING", "Scanning Moonshot public market data for paper setups")
    try:
        trending = _http_json(MOONSHOT_TRENDING)
        tokens = trending if isinstance(trending, list) else trending.get("data", [])
        bundle = []
        prices = {}

        for token in list(tokens)[:6]:
            if not isinstance(token, dict):
                continue
            symbol, token_id, price = _token_identity(token)
            if not symbol:
                continue
            details = {"token": token}
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

        for line in _close_paper_trades(conn, "MEME", prices):
            print("Raptor paper exit:", line)

        if not bundle or model_budget[0] + 2 > max_model_calls:
            _set_agent(conn, "Raptor", "READY", "Moonshot scan complete; no setup review")
            return

        idea = Runner.run_sync(
            build_raptor(),
            "Choose at most one PAPER setup from these Moonshot market snapshots. "
            "Repeated support must be evidenced by local_price_history; if it is not, WAIT.\\n\\n"
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
            opened = _open_paper_trade(conn, signal_id, "MEME", idea, cap)

        _set_agent(
            conn,
            "Raptor",
            "READY",
            f"Moonshot paper decision: {idea.action} {idea.symbol}; "
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
            "If no setup is strong, WAIT.\\n\\n"
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
            opened = _open_paper_trade(conn, signal_id, "STOCK", idea, cap)

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

    print("\\n=== DARWIN TRADING DESK — PAPER MODE ===")
    print("Raptor: Moonshot public-data meme momentum scanner")
    print("Apex: intraday equities scanner (Alpaca paper data + owner watchlist)")
    print("Circuit: independent risk gate")
    print("REAL MONEY EXECUTION: DISABLED")
    print(f"Scan interval: {interval} minute(s)")
    print(f"Model-call guardrail: {max_model_calls}")
    print("Press Ctrl+C to stop safely.\\n")

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
        print("\\nTrading desk stopped by owner.")
    finally:
        _set_agent(conn, "Raptor", "OFF_SHIFT", "Paper trading desk stopped")
        _set_agent(conn, "Apex", "OFF_SHIFT", "Paper trading desk stopped")
        _set_agent(conn, "Circuit", "OFF_SHIFT", "Paper trading desk stopped")
        conn.close()


if __name__ == "__main__":
    main()
