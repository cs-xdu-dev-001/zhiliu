from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import create_app
from app.models import IntelligenceItem, Subscription, User


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with testing_session() as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seeded_user(db_session: Session) -> User:
    user = User(
        username="admin",
        password_hash=PasswordHash.recommended().hash("test-pass"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_client(client: TestClient, seeded_user: User) -> TestClient:
    response = client.post(
        "/api/auth/login",
        json={"username": seeded_user.username, "password": "test-pass"},
    )
    assert response.status_code == 204
    return client


@pytest.fixture
def subscription(db_session: Session) -> Subscription:
    record = Subscription(
        name="AI每日热点",
        kind="news",
        keywords_json='["AI Agent", "RAG"]',
        schedule="0 8 * * *",
        prompt="检索过去24小时重要新闻",
        enabled=True,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


@pytest.fixture
def seeded_item(db_session: Session, subscription: Subscription) -> IntelligenceItem:
    item = IntelligenceItem(
        subscription_id=subscription.id,
        kind="news",
        title="Agent框架发布新版本",
        summary="新版本改进了工具调用与上下文管理。",
        url="https://example.com/agent-release",
        source="Example Research",
        keywords_json='["Agent"]',
        reason="影响Agent开发工作流",
        importance=0.92,
        fingerprint="a" * 64,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item
