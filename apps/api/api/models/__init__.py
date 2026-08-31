"""
SQLAlchemy 2.0 models and database session management for CertForge.

Uses Neon PostgreSQL via psycopg2. Engine and session factory are created
lazily on first use so import-time failures don't break the app.
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from api.core.config import DATABASE_URL

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# Lazy engine initialization
_engine = None
_SessionFactory = None


def get_engine():
    """Get or create the SQLAlchemy engine (lazy singleton)."""
    global _engine
    if _engine is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")
        if DATABASE_URL.startswith("sqlite"):
            # SQLite, for local development and the E2E suite. Everything in
            # the Postgres branch below is a psycopg2 argument — `connect_timeout`
            # is rejected outright, and the pool sizing is meaningless against a
            # file. `check_same_thread=False` because uvicorn serves requests
            # from a thread pool and SQLite otherwise refuses the connection.
            #
            # This is why the unit suite builds its own engine and patches
            # get_db rather than using this one: until now the real engine
            # could not open a SQLite database at all.
            _engine = create_engine(
                DATABASE_URL, connect_args={"check_same_thread": False}
            )
        else:
            _engine = create_engine(
                DATABASE_URL,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
                connect_args={"connect_timeout": 5},
            )
        logger.info("Database engine created")
    return _engine


def get_session_factory() -> sessionmaker:
    """Get or create the session factory (lazy singleton)."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager yielding a database session with auto-commit/rollback."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Create all tables from model metadata. Used for dev/test setup."""
    Base.metadata.create_all(get_engine())
    logger.info("Database tables created")


# Import all models so they register with Base.metadata
from api.models.organization import Organization, OrgMember  # noqa: F401, E402
from api.models.template import Template  # noqa: F401, E402
from api.models.template_asset import TemplateAsset  # noqa: F401, E402
from api.models.credential import Credential, CredentialBatch  # noqa: F401, E402
from api.models.passport import Passport, PassportCredential  # noqa: F401, E402
from api.models.api_key import ApiKey, WebhookEndpoint  # noqa: F401, E402
from api.models.usage import UsageLedger  # noqa: F401, E402
