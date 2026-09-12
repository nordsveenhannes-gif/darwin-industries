import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path(os.getenv("DARWIN_DB_PATH", "data/darwin.db"))


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
    columns = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if name not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            opportunity TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PLANNING'
        );

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            agent TEXT NOT NULL,
            report TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES runs(id)
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            owner TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'READY',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 2,
            cash_budget_usd REAL NOT NULL DEFAULT 0,
            external_action INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES runs(id)
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            event_type TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )

    # Safe migrations for databases created by older Darwin builds.
    _ensure_column(conn, "tasks", "result_text", "TEXT")
    _ensure_column(conn, "tasks", "qa_report", "TEXT")
    _ensure_column(conn, "tasks", "last_error", "TEXT")
    _ensure_column(conn, "tasks", "updated_at", "TEXT")
    conn.commit()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_run(conn: sqlite3.Connection, opportunity: str) -> int:
    cur = conn.execute(
        "INSERT INTO runs(created_at, opportunity, status) VALUES (?, ?, ?)",
        (now_iso(), opportunity, "PLANNING"),
    )
    conn.commit()
    return int(cur.lastrowid)


def save_report(conn: sqlite3.Connection, run_id: int, agent: str, report: str) -> None:
    conn.execute(
        "INSERT INTO reports(run_id, agent, report, created_at) VALUES (?, ?, ?, ?)",
        (run_id, agent, report, now_iso()),
    )
    conn.commit()


def save_event(conn: sqlite3.Connection, run_id: int, event_type: str, detail: str) -> None:
    conn.execute(
        "INSERT INTO events(run_id, event_type, detail, created_at) VALUES (?, ?, ?, ?)",
        (run_id, event_type, detail, now_iso()),
    )
    conn.commit()


def set_run_status(conn: sqlite3.Connection, run_id: int, status: str) -> None:
    conn.execute("UPDATE runs SET status=? WHERE id=?", (status, run_id))
    conn.commit()


def latest_report(conn: sqlite3.Connection, run_id: int, agent: str) -> str:
    row = conn.execute(
        """
        SELECT report FROM reports
        WHERE run_id=? AND agent=?
        ORDER BY id DESC LIMIT 1
        """,
        (run_id, agent),
    ).fetchone()
    return row["report"] if row else ""


def seed_validation_tasks(conn: sqlite3.Connection, run_id: int) -> None:
    tasks = [
        ("Forge", "Build website-audit template and QA checklist", 0, 0),
        ("Forge", "Produce one internal sample audit", 0, 0),
        ("Mercury", "Define 20-prospect qualification criteria", 0, 0),
        ("Mercury", "Draft personalized outreach template for later approval", 0, 0),
        ("Ledger", "Create pilot economics and revenue-verification checklist", 0, 0),
        ("Sentinel", "Review experiment scope before any external action", 0, 0),
    ]

    existing = conn.execute(
        "SELECT COUNT(*) AS n FROM tasks WHERE run_id=?", (run_id,)
    ).fetchone()["n"]

    if existing:
        return

    for owner, title, cash_budget, external_action in tasks:
        conn.execute(
            """
            INSERT INTO tasks(
                run_id, owner, title, status, attempts, max_attempts,
                cash_budget_usd, external_action, created_at, updated_at
            )
            VALUES (?, ?, ?, 'READY', 0, 2, ?, ?, ?, ?)
            """,
            (
                run_id,
                owner,
                title,
                cash_budget,
                external_action,
                now_iso(),
                now_iso(),
            ),
        )
    conn.commit()


def claim_next_internal_task(conn: sqlite3.Connection, run_id: int):
    task = conn.execute(
        """
        SELECT * FROM tasks
        WHERE run_id=?
          AND status='READY'
          AND external_action=0
          AND cash_budget_usd=0
        ORDER BY id
        LIMIT 1
        """,
        (run_id,),
    ).fetchone()

    if not task:
        return None

    conn.execute(
        """
        UPDATE tasks
        SET status='IN_PROGRESS',
            attempts=attempts+1,
            updated_at=?
        WHERE id=?
        """,
        (now_iso(), task["id"]),
    )
    conn.commit()
    return conn.execute("SELECT * FROM tasks WHERE id=?", (task["id"],)).fetchone()


def complete_task(
    conn: sqlite3.Connection,
    task_id: int,
    result_text: str,
    qa_report: str,
) -> None:
    conn.execute(
        """
        UPDATE tasks
        SET status='DONE',
            result_text=?,
            qa_report=?,
            last_error=NULL,
            updated_at=?
        WHERE id=?
        """,
        (result_text, qa_report, now_iso(), task_id),
    )
    conn.commit()


def fail_or_retry_task(
    conn: sqlite3.Connection,
    task_id: int,
    result_text: str,
    qa_report: str,
    error: str = "",
) -> str:
    task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    next_status = "BLOCKED" if task["attempts"] >= task["max_attempts"] else "READY"

    conn.execute(
        """
        UPDATE tasks
        SET status=?,
            result_text=?,
            qa_report=?,
            last_error=?,
            updated_at=?
        WHERE id=?
        """,
        (
            next_status,
            result_text,
            qa_report,
            error or None,
            now_iso(),
            task_id,
        ),
    )
    conn.commit()
    return next_status


def refresh_run_status(conn: sqlite3.Connection, run_id: int) -> str:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM tasks WHERE run_id=? GROUP BY status",
        (run_id,),
    ).fetchall()
    counts = {row["status"]: row["n"] for row in rows}

    if counts.get("BLOCKED", 0):
        status = "INTERNAL_BLOCKED"
    elif counts.get("READY", 0) or counts.get("IN_PROGRESS", 0):
        status = "WORKING_INTERNAL"
    elif counts.get("DONE", 0):
        status = "INTERNAL_COMPLETE"
    else:
        status = "READY_INTERNAL"

    set_run_status(conn, run_id, status)
    return status
