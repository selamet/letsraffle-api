"""
Test configuration and fixtures
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models.database import Base
from app.models import get_db, User
from app.core.security import create_access_token


# Test database setup (in-memory SQLite)
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def test_db():
    """
    Create a fresh database for each test
    """
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db):
    """
    Create a test client with overridden database dependency
    """
    def override_get_db():
        try:
            yield test_db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture(scope="function", autouse=True)
def mock_celery_tasks(monkeypatch):
    """
    Mock all Celery task .delay() calls
    Auto-use: applied to all tests automatically
    """
    def mock_delay(*args, **kwargs):
        return None
    
    monkeypatch.setattr('app.tasks.draw.process_draw.delay', mock_delay)
    monkeypatch.setattr('app.tasks.email_tasks.send_password_reset_email_task.delay', mock_delay)


@pytest.fixture(scope="function")
def test_user(test_db):
    """
    Create a test user in the database
    """
    user = User(
        email="testuser@example.com",
        password=User.hash_password("TestPassword123!")
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_token(test_user):
    """
    Generate authentication token for test user
    """
    token = create_access_token(data={"sub": test_user.email})
    return token


@pytest.fixture(scope="function")
def auth_headers(auth_token):
    """
    Generate authorization headers for authenticated requests
    """
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="function")
def second_user(test_db):
    """
    Create a second test user for authorization tests
    """
    user = User(
        email="seconduser@example.com",
        password=User.hash_password("SecondPassword123!")
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture(scope="function")
def second_auth_token(second_user):
    """
    Generate authentication token for second user
    """
    token = create_access_token(data={"sub": second_user.email})
    return token


@pytest.fixture(scope="function")
def second_auth_headers(second_auth_token):
    """
    Generate authorization headers for second user
    """
    return {"Authorization": f"Bearer {second_auth_token}"}

