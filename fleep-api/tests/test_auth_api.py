import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from core.database import get_db
from main import app


@pytest_asyncio.fixture
async def client(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_register_and_login_roundtrip(client):
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "correct-horse-battery", "display_name": "Alice"},
    )
    assert register_resp.status_code == 201, register_resp.text
    body = register_resp.json()
    assert body["email"] == "alice@example.com"
    assert "hashed_password" not in body  # response schema must not leak the hash

    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": "correct-horse-battery"}
    )
    assert login_resp.status_code == 200, login_resp.text
    tokens = login_resp.json()
    assert tokens["token_type"] == "bearer"
    assert len(tokens["access_token"]) > 20


@pytest.mark.asyncio
async def test_login_wrong_password_rejected(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "correct-horse-battery", "display_name": "Bob"},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": "bob@example.com", "password": "wrong-password"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_registration_conflicts(client):
    payload = {"email": "carol@example.com", "password": "correct-horse-battery", "display_name": "Carol"}
    first = await client.post("/api/v1/auth/register", json=payload)
    second = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_transactions_require_auth(client):
    resp = await client.get("/api/v1/transactions")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_and_fetch_transaction(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "dave@example.com", "password": "correct-horse-battery", "display_name": "Dave"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": "dave@example.com", "password": "correct-horse-battery"}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/v1/transactions",
        json={"kind": "deposit", "idempotency_key": "test-key-1", "amount": 42.5, "currency": "USD"},
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    tx = create_resp.json()
    assert tx["status"] == "pending"

    list_resp = await client.get("/api/v1/transactions", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    detail_resp = await client.get(f"/api/v1/transactions/{tx['id']}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == tx["id"]


@pytest.mark.asyncio
async def test_invalid_transition_returns_409(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "erin@example.com", "password": "correct-horse-battery", "display_name": "Erin"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": "erin@example.com", "password": "correct-horse-battery"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    create_resp = await client.post(
        "/api/v1/transactions",
        json={"kind": "deposit", "idempotency_key": "test-key-2"},
        headers=headers,
    )
    tx_id = create_resp.json()["id"]

    bad_transition = await client.post(
        f"/api/v1/transactions/{tx_id}/transition",
        json={"to_status": "completed"},  # pending -> completed is illegal
        headers=headers,
    )
    assert bad_transition.status_code == 409
