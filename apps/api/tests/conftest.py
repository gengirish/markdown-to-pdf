import os
import pytest
import contextlib
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DB_PATH = "test_db.sqlite"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from api.models import Base
from api.index import app

@contextlib.asynccontextmanager
async def mock_lifespan(app):
    yield
app.router.lifespan_context = mock_lifespan

test_engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@contextlib.contextmanager
def override_get_db():
    """Mirror api.models.get_db, including its commit-on-success behaviour.

    Routes rely on the context manager committing for them (none of them call
    session.commit()), so a yield-only stand-in silently discards every write.
    """
    db = TestingSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@pytest.fixture(scope="session", autouse=True)
def setup_db():
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass
            
    Base.metadata.create_all(bind=test_engine)
    
    patchers = [
        patch("api.routes.orgs.get_db", override_get_db),
        patch("api.routes.studio.get_db", override_get_db),
        patch("api.routes.templates.get_db", override_get_db),
        patch("api.routes.verify.get_db", override_get_db),
        patch("api.routes.developers.get_db", override_get_db),
        patch("api.routes.passports.get_db", override_get_db),
        patch("api.routes.billing.get_db", override_get_db),
        patch("api.routes.webhooks_clerk.get_db", override_get_db),
        # require_org_role imports get_db from api.models at call time.
        patch("api.models.get_db", override_get_db),
    ]
    for p in patchers:
        p.start()
        
    yield
    
    for p in patchers:
        p.stop()
        
    Base.metadata.drop_all(bind=test_engine)
    
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass

@pytest.fixture
def db_session():
    """Direct session against the test database, for arranging fixture rows."""
    with TestingSessionLocal() as session:
        yield session


@pytest.fixture
def client(setup_db):
    with TestClient(app) as c:
        yield c

@pytest.fixture
def mock_clerk():
    """Stand in for a signed-in human on both auth dependencies.

    Routes reachable by machines depend on resolve_principal rather than
    get_current_user, so overriding only the latter leaves them answering 401
    and the test looks like an authorisation bug instead of a missing stub.
    """
    from api.core.auth import get_current_user, AuthenticatedUser
    from api.core.principal import Principal, require_user, resolve_principal

    def _get_current_user():
        # Keep in sync with the AuthenticatedUser dataclass — it has no
        # session_id field, and passing one raises TypeError.
        return AuthenticatedUser(clerk_user_id="test_user_123")

    def _resolve_principal():
        return Principal(kind="user", clerk_user_id="test_user_123")

    overrides = {
        get_current_user: _get_current_user,
        resolve_principal: _resolve_principal,
        require_user: _resolve_principal,
    }
    app.dependency_overrides.update(overrides)
    yield
    for dep in overrides:
        app.dependency_overrides.pop(dep, None)
