"""Which database URLs may start the background worker.

Procrastinate's connector is psycopg. Pointed at anything but Postgres it does
not fail fast — it waits out a 30-second pool timeout inside the FastAPI
lifespan and then aborts application startup, so the API serves nothing at all.

The gate used to be `bool(DATABASE_URL)`, which meant a SQLite URL — what local
development and the E2E suite both use — took the API down on boot rather than
degrading. These pin the rule so it cannot quietly widen again.
"""

import importlib

import pytest


def worker_enabled_for(monkeypatch, url: str) -> bool:
    """Re-import the worker module under a given DATABASE_URL.

    WORKER_ENABLED is decided at import time, which is the only moment the
    answer matters — the lifespan reads it once on boot.
    """
    monkeypatch.setenv("DATABASE_URL", url)
    import api.core.worker as worker

    return importlib.reload(worker).WORKER_ENABLED


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pw@host/db",
        "postgres://user:pw@host/db",
        "postgresql+psycopg://user:pw@host/db",
    ],
)
def test_postgres_urls_enable_the_worker(monkeypatch, url):
    assert worker_enabled_for(monkeypatch, url) is True


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///test.sqlite",
        "sqlite+pysqlite:///:memory:",
        "mysql://user:pw@host/db",
    ],
)
def test_non_postgres_urls_leave_the_worker_off(monkeypatch, url):
    """Not merely unsupported — enabling it here aborts application startup."""
    assert worker_enabled_for(monkeypatch, url) is False


def test_no_database_url_leaves_the_worker_off(monkeypatch):
    assert worker_enabled_for(monkeypatch, "") is False


@pytest.fixture(autouse=True)
def _restore_worker_module():
    """Leave the module as the rest of the suite expects to find it.

    reload() mutates the imported module in place, so without this every test
    after these would see whichever URL ran last.
    """
    yield
    import api.core.worker

    importlib.reload(api.core.worker)
