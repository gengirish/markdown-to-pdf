"""
One-shot release step for CertForge.

Runs as Fly's `release_command` — once per deploy, on a throwaway machine —
so that neither Alembic migrations nor the Procrastinate queue schema execute
on every cold start. That matters for scale-to-zero: with auto_start_machines
the API boots on demand, and DDL on every boot would both slow the wake path
and hold a Neon connection open longer than the request needs.
"""

import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("release")


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(here, "alembic.ini"))
    logger.info("Applying Alembic migrations…")
    command.upgrade(cfg, "head")
    logger.info("Alembic migrations applied.")


def _queue_schema_present() -> bool:
    """True once Procrastinate's tables exist in the target database."""
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute("SELECT to_regclass('public.procrastinate_jobs')").fetchone()
    return bool(row and row[0])


async def _apply_queue_schema() -> None:
    from api.core.worker import worker_app

    # apply_schema_async() executes procrastinate's schema.sql verbatim, and that
    # file uses bare CREATE TABLE — it is a first-install step, not idempotent.
    # Running it unguarded made every deploy after the first abort the release
    # command, which aborts the whole deploy.
    if _queue_schema_present():
        logger.info("Procrastinate schema already present — skipping.")
        return

    logger.info("Applying Procrastinate schema…")
    async with worker_app.open_async():
        await worker_app.schema_manager.apply_schema_async()
    logger.info("Procrastinate schema applied.")


def main() -> int:
    if not os.environ.get("DATABASE_URL"):
        logger.warning("DATABASE_URL not set — skipping release step.")
        return 0
    _run_migrations()
    asyncio.run(_apply_queue_schema())
    return 0


if __name__ == "__main__":
    sys.exit(main())
