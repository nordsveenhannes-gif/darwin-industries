from agents import Runner

from backend.agents.atlas import build_atlas
from backend.agents.freya import build_freya
from backend.agents.ledger import build_ledger
from backend.agents.midas import build_midas
from backend.agents.nova import build_nova
from backend.agents.satoshi import build_satoshi
from backend.storage import now_iso, save_event


SUPPORT_ROSTER = [
    ("Atlas", "CEO / Capital Allocation", build_atlas),
    ("Ledger", "CFO / Risk", build_ledger),
    ("Nova", "Growth", build_nova),
    ("Freya", "Freelance / Partnerships", build_freya),
    ("Midas", "Digital Assets", build_midas),
    ("Satoshi", "Automation / Treasury Research", build_satoshi),
]


def company_snapshot(conn) -> str:
    pipeline = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status='RESEARCHED' THEN 1 ELSE 0 END) AS researched,
            SUM(CASE WHEN status='SCORED' THEN 1 ELSE 0 END) AS scored,
            SUM(CASE WHEN status='AUDITED' THEN 1 ELSE 0 END) AS audited,
            SUM(CASE WHEN status='DRAFT_READY' THEN 1 ELSE 0 END) AS draft_ready,
            SUM(CASE WHEN status='CONTACT_READY' THEN 1 ELSE 0 END) AS contact_ready,
            SUM(CASE WHEN status='OUTREACH_SENT' THEN 1 ELSE 0 END) AS sent
        FROM prospects
        """
    ).fetchone()

    top = conn.execute(
        """
        SELECT business_name, market, category, sales_score, status
        FROM prospects
        WHERE sales_score IS NOT NULL
        ORDER BY sales_score DESC, confidence DESC
        LIMIT 5
        """
    ).fetchall()

    email = conn.execute(
        """
        SELECT
            SUM(CASE WHEN status='SENT' THEN 1 ELSE 0 END) AS sent,
            SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed
        FROM outbound_emails
        """
    ).fetchone()

    top_text = "; ".join(
        f"{r['business_name']} ({r['category']}, {r['market']}, score {r['sales_score']}, {r['status']})"
        for r in top
    ) or "none yet"

    return (
        "Current offer: 48-Hour Local Website Lead Audit, $129 pilot.\n"
        f"Pipeline: total={pipeline['total'] or 0}, researched={pipeline['researched'] or 0}, "
        f"scored={pipeline['scored'] or 0}, audited={pipeline['audited'] or 0}, "
        f"draft_ready={pipeline['draft_ready'] or 0}, contact_ready={pipeline['contact_ready'] or 0}, "
        f"outreach_sent={pipeline['sent'] or 0}.\n"
        f"Email log: sent={email['sent'] or 0}, failed={email['failed'] or 0}.\n"
        f"Top prospects: {top_text}.\n"
        "Cash spending is disabled. Revenue must not be claimed unless verified from payments."
    )


def support_agent_for_cycle(cycle: int):
    # One support department model call per cycle. Across a normal six-cycle workday,
    # every support department gets a turn while the core revenue team works every cycle.
    return SUPPORT_ROSTER[(cycle - 1) % len(SUPPORT_ROSTER)]


def run_support_shift(conn, session_id: int, run_id: int | None, cycle: int) -> tuple[str, int]:
    agent_name, role, builder = support_agent_for_cycle(cycle)
    snapshot = company_snapshot(conn)

    assignment = (
        f"You are on department shift {cycle}. Review this compact live company snapshot "
        "and produce the highest-value work product for your role. Keep it concise and actionable.\n\n"
        + snapshot
    )

    conn.execute(
        """
        UPDATE agent_state
        SET status='WORKING', last_action=?, updated_at=?
        WHERE agent=?
        """,
        (f"Department shift {cycle}: {role}", now_iso(), agent_name),
    )
    conn.commit()

    try:
        report = Runner.run_sync(builder(), assignment).final_output
        report_text = str(report).strip()

        conn.execute(
            """
            INSERT INTO department_reports(
                session_id, cycle, agent, role, assignment, report, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'DONE', ?)
            """,
            (
                session_id,
                cycle,
                agent_name,
                role,
                assignment,
                report_text,
                now_iso(),
            ),
        )
        conn.execute(
            """
            UPDATE agent_state
            SET status='READY',
                last_action=?,
                confidence=MIN(100, confidence + 1),
                motivation=MIN(100, motivation + 1),
                stress=MAX(0, stress - 1),
                updated_at=?
            WHERE agent=?
            """,
            (f"Completed department shift {cycle}", now_iso(), agent_name),
        )
        conn.commit()

        if run_id is not None:
            save_event(
                conn,
                run_id,
                "DEPARTMENT_SHIFT_DONE",
                f"{agent_name} completed {role} shift for cycle {cycle}.",
            )
        return agent_name, 1

    except Exception:
        conn.execute(
            """
            UPDATE agent_state
            SET status='READY',
                last_action=?,
                confidence=MAX(0, confidence - 2),
                stress=MIN(100, stress + 3),
                updated_at=?
            WHERE agent=?
            """,
            (f"Department shift {cycle} failed", now_iso(), agent_name),
        )
        conn.commit()
        raise


def set_core_agent_action(conn, agent: str, action: str, status: str = "WORKING") -> None:
    conn.execute(
        """
        UPDATE agent_state
        SET status=?, last_action=?, updated_at=?
        WHERE agent=?
        """,
        (status, action, now_iso(), agent),
    )
    conn.commit()


def end_shift(conn) -> None:
    conn.execute(
        """
        UPDATE agent_state
        SET status='OFF_SHIFT', last_action='Workday ended', updated_at=?
        """,
        (now_iso(),),
    )
    conn.commit()
