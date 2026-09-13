from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / "runtime"
LOG_DIR = ROOT / "logs"
LOCK_PATH = RUNTIME_DIR / "shenanigans_workday.json"


PAPER_ENV = {
    "DARWIN_TRADING_MODE": "paper",
    "DARWIN_MEME_SIM_FEE_MODE": "dex_route",
    "DARWIN_MEME_PAPER_ACCOUNT_USD": "100",
    "DARWIN_MEME_PAPER_NOTIONAL_USD": "40",
    "DARWIN_MEME_PAPER_DAILY_STOP_USD": "6",
    "DARWIN_MEME_MAX_OPEN_TRADES": "3",
    "DARWIN_MEME_CANDIDATES": "10",
    "DARWIN_MEME_MIN_LIQUIDITY_USD": "15000",
    "DARWIN_MEME_SIM_ROUTE_FEE_BPS_PER_SIDE": "30",
    "DARWIN_MEME_SIM_NETWORK_FEE_USD_ROUND_TRIP": "0.02",
    "DARWIN_MEME_SIM_SLIPPAGE_BPS": "35",
}


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def workday_state() -> dict:
    if not LOCK_PATH.exists():
        return {"active": False}
    try:
        data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        pid = int(data.get("pid") or 0)
    except Exception:
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass
        return {"active": False}

    if not _pid_alive(pid):
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass
        return {"active": False}
    data["active"] = True
    return data


def _write_lock(pid: int, hours: float, log_path: Path) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(
        json.dumps(
            {
                "pid": pid,
                "hours": hours,
                "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "log": str(log_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def start_company_day_background(hours: float = 6.0) -> dict:
    current = workday_state()
    if current.get("active"):
        return {"started": False, "reason": "A workday is already running.", **current}

    hours = max(0.25, min(float(hours), 6.0))
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"shenanigans-workday-{stamp}.log"

    command = [
        sys.executable,
        "-m",
        "backend.company_day",
        "--worker",
        "--hours",
        str(hours),
    ]
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )

    log_handle = open(log_path, "a", encoding="utf-8", buffering=1)
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=os.environ.copy(),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=(os.name != "nt"),
        )
    finally:
        log_handle.close()

    _write_lock(process.pid, hours, log_path)
    return {
        "started": True,
        "active": True,
        "pid": process.pid,
        "hours": hours,
        "log": str(log_path),
    }


def _worker(hours: float) -> int:
    env = os.environ.copy()
    env.update(PAPER_ENV)

    worker_cmd = [
        sys.executable,
        "-m",
        "backend.workday",
        "--hours",
        str(hours),
        "--cycle-minutes",
        "60",
        "--max-model-calls",
        "50",
        "--prospects-per-cycle",
        "4",
    ]
    trading_cmd = [
        sys.executable,
        "-m",
        "backend.trading_desk",
        "--hours",
        str(hours),
        "--interval-minutes",
        "3",
        "--max-model-calls",
        "120",
    ]

    print("\n=== HOSKO'S SHADY SHENANIGANS — COMPANY DAY ===", flush=True)
    print(f"Target workday: {hours:g} hour(s)", flush=True)
    print("Worker agents + trading desk launched together.", flush=True)
    print("Trading remains PAPER ONLY.", flush=True)

    children: list[subprocess.Popen] = []
    try:
        children.append(subprocess.Popen(worker_cmd, cwd=ROOT, env=env))
        children.append(subprocess.Popen(trading_cmd, cwd=ROOT, env=env))

        while children:
            alive = []
            for child in children:
                if child.poll() is None:
                    alive.append(child)
            children = alive
            if children:
                time.sleep(2)
        return 0
    except KeyboardInterrupt:
        print("Company day interrupted; stopping child processes.", flush=True)
        for child in children:
            if child.poll() is None:
                child.terminate()
        return 130
    finally:
        try:
            if LOCK_PATH.exists():
                data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
                if int(data.get("pid") or 0) == os.getpid():
                    LOCK_PATH.unlink()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Hosko's Shady Shenanigans worker agents and paper trading desk together."
    )
    parser.add_argument("--hours", type=float, default=6.0)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--start", action="store_true")
    args = parser.parse_args()

    hours = max(0.25, min(float(args.hours), 6.0))
    if args.worker:
        raise SystemExit(_worker(hours))

    result = start_company_day_background(hours)
    if result.get("started"):
        print(f"Workday started. PID {result['pid']}.")
        print(f"Log: {result['log']}")
    else:
        print(result.get("reason", "Workday was not started."))


if __name__ == "__main__":
    main()
