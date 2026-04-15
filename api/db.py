"""
Database layer for IntelliForge Certificate Platform.
Uses Neon PostgreSQL via psycopg2.
"""

import os
import logging
import hashlib
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS courses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS certificates (
    id SERIAL PRIMARY KEY,
    certificate_id VARCHAR(50) NOT NULL,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    participant_name VARCHAR(255) NOT NULL,
    participant_email VARCHAR(255) DEFAULT '',
    course_name VARCHAR(255) NOT NULL,
    completion_date VARCHAR(50) NOT NULL,
    instructor_name VARCHAR(255) NOT NULL,
    issued_at TIMESTAMPTZ DEFAULT NOW(),
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMPTZ,
    client_ip VARCHAR(45)
);

CREATE INDEX IF NOT EXISTS idx_certificates_issued_at ON certificates(issued_at DESC);
CREATE INDEX IF NOT EXISTS idx_certificates_course ON certificates(course_name);
"""

SEED_COURSES = [
    ("AI Product Development Fundamentals", "Learn the fundamentals of building AI-powered products"),
    ("Building AI-Powered Applications", "Hands-on course building real AI applications"),
    ("Prompt Engineering & LLM Integration", "Master prompt engineering and LLM API integration"),
    ("Full-Stack AI Development", "End-to-end AI application development"),
    ("AI Product Design & UX", "Design thinking for AI products"),
    ("Digital Profile Creation", "Build your professional digital presence"),
    ("Deploying AI Solutions", "Deploy and scale AI models in production"),
    ("AI Code Reviewer Course", "Learn systematic AI-assisted code review"),
]


def _get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


@contextmanager
def get_db():
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema():
    """Create tables and seed initial courses if empty."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(SCHEMA_SQL)

        # Migration: add participant_email column if missing
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'certificates' AND column_name = 'participant_email'
        """)
        if not cur.fetchone():
            cur.execute("ALTER TABLE certificates ADD COLUMN participant_email VARCHAR(255) DEFAULT ''")
            logger.info("Migrated: added participant_email column to certificates")

        cur.execute("SELECT COUNT(*) as cnt FROM courses")
        row = cur.fetchone()
        if row["cnt"] == 0:
            for name, desc in SEED_COURSES:
                cur.execute(
                    "INSERT INTO courses (name, description) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
                    (name, desc),
                )
            logger.info(f"Seeded {len(SEED_COURSES)} courses")
        logger.info("Database schema initialized")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ── Courses ───────────────────────────────────────────────────────────

def get_courses(active_only: bool = True) -> list[dict]:
    with get_db() as conn:
        cur = conn.cursor()
        if active_only:
            cur.execute("SELECT id, name, description, active FROM courses WHERE active = TRUE ORDER BY id")
        else:
            cur.execute("SELECT id, name, description, active FROM courses ORDER BY id")
        return [dict(r) for r in cur.fetchall()]


def add_course(name: str, description: str = "") -> dict:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO courses (name, description) VALUES (%s, %s) RETURNING id, name, description, active",
            (name, description),
        )
        return dict(cur.fetchone())


def toggle_course(course_id: int, active: bool) -> dict | None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE courses SET active = %s WHERE id = %s RETURNING id, name, description, active",
            (active, course_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_active_course_names() -> list[str]:
    courses = get_courses(active_only=True)
    return [c["name"] for c in courses]


# ── Certificates ──────────────────────────────────────────────────────

def store_certificate(
    certificate_id: str,
    token: str,
    participant_name: str,
    course_name: str,
    completion_date: str,
    instructor_name: str,
    client_ip: str = "",
    participant_email: str = "",
) -> dict:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO certificates
               (certificate_id, token_hash, participant_name, participant_email,
                course_name, completion_date, instructor_name, client_ip)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id, certificate_id, participant_name, participant_email,
                         course_name, completion_date, instructor_name, issued_at, revoked""",
            (certificate_id, token_hash(token), participant_name, participant_email,
             course_name, completion_date, instructor_name, client_ip),
        )
        return dict(cur.fetchone())


def list_certificates(limit: int = 50, offset: int = 0, course: str | None = None) -> dict:
    with get_db() as conn:
        cur = conn.cursor()
        where = ""
        params: list = []
        if course:
            where = "WHERE course_name = %s"
            params.append(course)

        cur.execute(f"SELECT COUNT(*) as total FROM certificates {where}", params)
        total = cur.fetchone()["total"]

        cur.execute(
            f"""SELECT id, certificate_id, participant_name, participant_email,
                       course_name, completion_date, instructor_name, issued_at, revoked
                FROM certificates {where}
                ORDER BY issued_at DESC
                LIMIT %s OFFSET %s""",
            params + [limit, offset],
        )
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            if isinstance(r.get("issued_at"), datetime):
                r["issued_at"] = r["issued_at"].isoformat()
        return {"certificates": rows, "total": total, "limit": limit, "offset": offset}


def revoke_certificate(cert_db_id: int) -> dict | None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE certificates SET revoked = TRUE, revoked_at = NOW()
               WHERE id = %s AND revoked = FALSE
               RETURNING id, certificate_id, participant_name, revoked""",
            (cert_db_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_stats() -> dict:
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) as total FROM certificates")
        total = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) as cnt FROM certificates WHERE issued_at >= NOW() - INTERVAL '7 days'")
        this_week = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM certificates WHERE revoked = TRUE")
        revoked = cur.fetchone()["cnt"]

        cur.execute(
            """SELECT course_name, COUNT(*) as cnt
               FROM certificates GROUP BY course_name ORDER BY cnt DESC LIMIT 10"""
        )
        by_course = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """SELECT DATE(issued_at) as day, COUNT(*) as cnt
               FROM certificates WHERE issued_at >= NOW() - INTERVAL '30 days'
               GROUP BY DATE(issued_at) ORDER BY day"""
        )
        daily = [{"day": str(r["day"]), "count": r["cnt"]} for r in cur.fetchall()]

        return {
            "total_certificates": total,
            "this_week": this_week,
            "revoked": revoked,
            "by_course": by_course,
            "daily_trend": daily,
        }
