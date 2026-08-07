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
    db = TestingSessionLocal()
    try:
        yield db
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
def client(setup_db):
    with TestClient(app) as c:
        yield c

@pytest.fixture
def mock_clerk():
    from api.core.auth import get_current_user, AuthenticatedUser
    
    def _get_current_user():
        return AuthenticatedUser(
            clerk_user_id="test_user_123",
            session_id="test_sess",
            email="test@intelliforge.tech"
        )
        
    app.dependency_overrides[get_current_user] = _get_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)
