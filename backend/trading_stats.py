import math

from dotenv import load_dotenv

from backend.storage import connect, init_db


TRADERS = [
    ("Raptor", "MEME"),
    ("Apex", "STOCK"),
]


def _profit_factor(gross_profit: float, gross_loss: float):
    if gross_loss > 0:
        return gross_profit / gross_loss
    if gross_profit > 0:
        return None
    return 0.0


def trader_stats(conn, agent: str, asset_class: str) -> dict:
    signals = conn.execute(
        """
        SELECT
            COUNT(*) AS signals,
            SUM(CASE WHEN UPPER(action)='BUY' THEN 1 ELSE 0 END) AS buy_signals,
            SUM(CASE WHEN UPPER(action)!='BUY' THEN 1 ELSE 0 END) AS wait_signals
        FROM trade_signals
        WHERE agent=? AND asset_class=?
        """,
        (agent, asset_class),
    ).fetchone()

    trades = conn.execute(
        """
        SELECT
            COUNT(*) AS trades,
            SUM(CASE WHEN pt.status='OPEN' THEN 1 ELSE 0 END) AS open_trades,
            SUM(CASE WHEN pt.status!='OPEN' THEN 1 ELSE 0 END) AS closed_trades,
            SUM(CASE WHEN pt.status!='OPEN' AND COALESCE(pt.pnl_usd,0)>0 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN pt.status!='OPEN' AND COALESCE(pt.pnl_usd,0)<0 THEN 1 ELSE 0 END) AS losses,
            COALESCE(SUM(CASE WHEN pt.status!='OPEN' THEN pt.pnl_usd ELSE 0 END),0) AS net_pnl,
            COALESCE(SUM(CASE WHEN pt.status!='OPEN' THEN pt.gross_pnl_usd ELSE 0 END),0) AS gross_pnl,
            COALESCE(SUM(CASE WHEN pt.status!='OPEN' THEN pt.fees_usd ELSE 0 END),0) AS fees,
            COALESCE(SUM(CASE WHEN pt.status!='OPEN' AND pt.pnl_usd>0 THEN pt.pnl_usd ELSE 0 END),0) AS gross_profit,
            ABS(COALESCE(SUM(CASE WHEN pt.status!='OPEN' AND pt.pnl_usd<0 THEN pt.pnl_usd ELSE 0 END),0)) AS gross_loss,
            COALESCE(AVG(CASE WHEN pt.status!='OPEN' THEN pt.pnl_usd END),0) AS avg_trade,
            COALESCE(MAX(CASE WHEN pt.status!='OPEN' THEN pt.pnl_usd END),0) AS best_trade,
            COALESCE(MIN(CASE WHEN pt.status!='OPEN' THEN pt.pnl_usd END),0) AS worst_trade
        FROM paper_trades pt
        JOIN trade_signals ts ON ts.id=pt.signal_id
        WHERE ts.agent=? AND pt.asset_class=?
        """,
        (agent, asset_class),
    ).fetchone()

    closed = int(trades["closed_trades"] or 0)
    wins = int(trades["wins"] or 0)
    gross_profit = float(trades["gross_profit"] or 0)
    gross_loss = float(trades["gross_loss"] or 0)
    profit_factor = _profit_factor(gross_profit, gross_loss)

    pnl_rows = conn.execute(
        """
        SELECT COALESCE(pt.pnl_usd, 0) AS pnl,
               COALESCE(pt.initial_risk_usd, 0) AS initial_risk_usd,
               COALESCE(pt.trade_mode, ts.trade_mode, 'UNKNOWN') AS trade_mode,
               COALESCE(pt.stress_level, ts.stress_level, 0) AS stress_level
        FROM paper_trades pt
        JOIN trade_signals ts ON ts.id=pt.signal_id
        WHERE ts.agent=? AND pt.asset_class=? AND pt.status!='OPEN'
        ORDER BY COALESCE(pt.closed_at, pt.opened_at), pt.id
        """,
        (agent, asset_class),
    ).fetchall()
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    r_values = []
    mode_totals = {}
    stress_totals = {}
    for row in pnl_rows:
        pnl = float(row["pnl"] or 0)
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

        risk = float(row["initial_risk_usd"] or 0)
        if risk > 0:
            r_value = pnl / risk
            r_values.append(r_value)
            mode = str(row["trade_mode"] or "UNKNOWN")
            bucket = mode_totals.setdefault(mode, {"trades": 0, "r_sum": 0.0})
            bucket["trades"] += 1
            bucket["r_sum"] += r_value
            stress = int(row["stress_level"] or 0)
            sb = stress_totals.setdefault(stress, {"trades": 0, "r_sum": 0.0})
            sb["trades"] += 1
            sb["r_sum"] += r_value

    expectancy_r = (sum(r_values) / len(r_values)) if r_values else 0.0
    mode_expectancy = {
        mode: {
            "trades": data["trades"],
            "expectancy_r": data["r_sum"] / data["trades"],
        }
        for mode, data in mode_totals.items()
        if data["trades"]
    }
    stress_expectancy = {
        str(level): {
            "trades": data["trades"],
            "expectancy_r": data["r_sum"] / data["trades"],
        }
        for level, data in stress_totals.items()
        if data["trades"]
    }

    sample_ready = closed >= 20
    promising = (
        sample_ready
        and float(trades["net_pnl"] or 0) > 0
        and profit_factor is not None
        and profit_factor >= 1.20
    )

    return {
        "agent": agent,
        "asset_class": asset_class,
        "signals": int(signals["signals"] or 0),
        "buy_signals": int(signals["buy_signals"] or 0),
        "wait_signals": int(signals["wait_signals"] or 0),
        "trades": int(trades["trades"] or 0),
        "open_trades": int(trades["open_trades"] or 0),
        "closed_trades": closed,
        "wins": wins,
        "losses": int(trades["losses"] or 0),
        "win_rate": (wins / closed * 100.0) if closed else 0.0,
        "net_pnl": float(trades["net_pnl"] or 0),
        "gross_pnl": float(trades["gross_pnl"] or 0),
        "fees": float(trades["fees"] or 0),
        "avg_trade": float(trades["avg_trade"] or 0),
        "best_trade": float(trades["best_trade"] or 0),
        "worst_trade": float(trades["worst_trade"] or 0),
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "expectancy_r": expectancy_r,
        "mode_expectancy": mode_expectancy,
        "stress_expectancy": stress_expectancy,
        "adaptation_review_due": closed > 0 and closed % 25 == 0,
        "sample_ready": sample_ready,
        "paper_verdict": (
            "PROMISING" if promising else "UNPROVEN" if sample_ready else "INSUFFICIENT_SAMPLE"
        ),
    }


def all_trader_stats(conn) -> list[dict]:
    return [trader_stats(conn, agent, asset_class) for agent, asset_class in TRADERS]


def main() -> None:
    load_dotenv()
    conn = connect()
    init_db(conn)

    print("\n=== DARWIN TRADER SCOREBOARD ===")
    print("Simulation statistics only. No real-money P&L is included.\n")

    for stats in all_trader_stats(conn):
        pf = stats["profit_factor"]
        pf_text = "inf" if pf is None else f"{pf:.2f}"
        print(f"{stats['agent']} — {stats['asset_class']}")
        print(
            f"  signals={stats['signals']} | BUY={stats['buy_signals']} | "
            f"WAIT={stats['wait_signals']}"
        )
        print(
            f"  closed={stats['closed_trades']} | open={stats['open_trades']} | "
            f"wins={stats['wins']} | losses={stats['losses']} | "
            f"win rate={stats['win_rate']:.1f}%"
        )
        print(
            f"  net P&L=$" + f"{stats['net_pnl']:+.2f}" + " | gross=$"
            + f"{stats['gross_pnl']:+.2f}" + " | fees=$"
            + f"{stats['fees']:.2f}" + f" | profit factor={pf_text}"
        )
        print(
            f"  max drawdown=$" + f"{stats['max_drawdown']:.2f}"
            + f" | expectancy={stats['expectancy_r']:+.2f}R"
            + f" | verdict={stats['paper_verdict']}"
        )
        print(
            f"  avg=$" + f"{stats['avg_trade']:+.2f}" + " | best=$"
            + f"{stats['best_trade']:+.2f}" + " | worst=$"
            + f"{stats['worst_trade']:+.2f}\n"
        )

    conn.close()


if __name__ == "__main__":
    main()
