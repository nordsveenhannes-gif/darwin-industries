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

        CREATE TABLE IF NOT EXISTS prospects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            created_at TEXT NOT NULL,
            market TEXT NOT NULL,
            category TEXT NOT NULL,
            business_name TEXT NOT NULL,
            website_url TEXT NOT NULL,
            city TEXT NOT NULL,
            observed_issue TEXT NOT NULL,
            why_fit TEXT NOT NULL,
            source_urls_json TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'RESEARCHED',
            UNIQUE(website_url)
        );

        CREATE TABLE IF NOT EXISTS work_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            status TEXT NOT NULL,
            target_hours REAL NOT NULL,
            cycles_completed INTEGER NOT NULL DEFAULT 0,
            model_call_budget INTEGER NOT NULL,
            estimated_calls_used INTEGER NOT NULL DEFAULT 0,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS outbound_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id INTEGER,
            provider TEXT NOT NULL,
            provider_message_id TEXT,
            from_email TEXT NOT NULL,
            to_email TEXT NOT NULL,
            subject TEXT NOT NULL,
            body_text TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            last_error TEXT,
            FOREIGN KEY(prospect_id) REFERENCES prospects(id)
        );

        CREATE TABLE IF NOT EXISTS suppressions (
            email TEXT PRIMARY KEY,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_state (
            agent TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'READY',
            last_action TEXT,
            confidence INTEGER NOT NULL DEFAULT 70,
            stress INTEGER NOT NULL DEFAULT 20,
            motivation INTEGER NOT NULL DEFAULT 80,
            job_security INTEGER NOT NULL DEFAULT 70,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS department_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            cycle INTEGER NOT NULL,
            agent TEXT NOT NULL,
            role TEXT NOT NULL,
            assignment TEXT NOT NULL,
            report TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES work_sessions(id)
        );

        CREATE TABLE IF NOT EXISTS customer_journeys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT NOT NULL,
            website_url TEXT NOT NULL,
            customer_email TEXT NOT NULL,
            status TEXT NOT NULL,
            observation TEXT,
            discovery_evidence TEXT,
            audit_text TEXT,
            audit_qa TEXT,
            outreach_subject TEXT,
            outreach_body TEXT,
            outreach_qa TEXT,
            email_status TEXT,
            provider_message_id TEXT,
            error_text TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS journey_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            journey_id INTEGER NOT NULL,
            agent TEXT NOT NULL,
            stage TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(journey_id) REFERENCES customer_journeys(id)
        );

        CREATE INDEX IF NOT EXISTS idx_journey_events
            ON journey_events(journey_id, id);

        CREATE INDEX IF NOT EXISTS idx_outbound_email_status
            ON outbound_emails(status, sent_at);

        CREATE INDEX IF NOT EXISTS idx_outbound_email_recipient
            ON outbound_emails(to_email, status);
        """
    )

    # Safe migrations for databases created by older Darwin builds.
    _ensure_column(conn, "tasks", "result_text", "TEXT")
    _ensure_column(conn, "tasks", "qa_report", "TEXT")
    _ensure_column(conn, "tasks", "last_error", "TEXT")
    _ensure_column(conn, "tasks", "updated_at", "TEXT")

    _ensure_column(conn, "prospects", "sales_score", "INTEGER")
    _ensure_column(conn, "prospects", "sales_reason", "TEXT")
    _ensure_column(conn, "prospects", "recommended_angle", "TEXT")
    _ensure_column(conn, "prospects", "audit_text", "TEXT")
    _ensure_column(conn, "prospects", "audit_qa", "TEXT")
    _ensure_column(conn, "prospects", "outreach_subject", "TEXT")
    _ensure_column(conn, "prospects", "outreach_body", "TEXT")
    _ensure_column(conn, "prospects", "outreach_qa", "TEXT")
    _ensure_column(conn, "prospects", "contact_email", "TEXT")
    _ensure_column(conn, "prospects", "contact_email_source", "TEXT")
    _ensure_column(conn, "prospects", "contact_email_kind", "TEXT")
    _ensure_column(conn, "prospects", "contact_confidence", "INTEGER")
    _ensure_column(conn, "prospects", "updated_at", "TEXT")

    roster = [
        ("Atlas", "CEO / Capital Allocation"),
        ("Mercury", "Sales"),
        ("Forge", "Product / Fulfillment"),
        ("Freya", "Freelance / Partnerships"),
        ("Nova", "Growth"),
        ("Satoshi", "Automation / Treasury Research"),
        ("Midas", "Digital Assets"),
        ("Oracle", "Research"),
        ("Ledger", "CFO / Risk"),
        ("Sentinel", "Operations / QA"),
    ]
    for agent, title in roster:
        conn.execute(
            """
            INSERT INTO agent_state(
                agent, title, status, last_action, confidence, stress,
                motivation, job_security, updated_at
            )
            VALUES (?, ?, 'READY', 'Waiting for workday', 70, 20, 80, 70, ?)
            ON CONFLICT(agent) DO UPDATE SET title=excluded.title
            """,
            (agent, title, now_iso()),
        )
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


def save_prospect(
    conn: sqlite3.Connection,
    run_id: int | None,
    market: str,
    category: str,
    business_name: str,
    website_url: str,
    city: str,
    observed_issue: str,
    why_fit: str,
    source_urls_json: str,
    confidence: int,
) -> bool:
    try:
        conn.execute(
            """
            INSERT INTO prospects(
                run_id, created_at, market, category, business_name,
                website_url, city, observed_issue, why_fit,
                source_urls_json, confidence, status, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RESEARCHED', ?)
            """,
            (
                run_id,
                now_iso(),
                market,
                category,
                business_name,
                website_url,
                city,
                observed_issue,
                why_fit,
                source_urls_json,
                confidence,
                now_iso(),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def latest_run_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        "SELECT id FROM runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row else None


def start_work_session(
    conn: sqlite3.Connection,
    target_hours: float,
    model_call_budget: int,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO work_sessions(
            started_at, status, target_hours, model_call_budget
        ) VALUES (?, 'RUNNING', ?, ?)
        """,
        (now_iso(), target_hours, model_call_budget),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_work_session(
    conn: sqlite3.Connection,
    session_id: int,
    cycles_completed: int,
    estimated_calls_used: int,
    status: str = "RUNNING",
    note: str | None = None,
    ended: bool = False,
) -> None:
    conn.execute(
        """
        UPDATE work_sessions
        SET cycles_completed=?,
            estimated_calls_used=?,
            status=?,
            note=?,
            ended_at=CASE WHEN ? THEN ? ELSE ended_at END
        WHERE id=?
        """,
        (
            cycles_completed,
            estimated_calls_used,
            status,
            note,
            1 if ended else 0,
            now_iso(),
            session_id,
        ),
    )
    conn.commit()
