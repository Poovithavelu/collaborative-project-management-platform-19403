import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_happy_path(client: AsyncClient):
    resp = await client.post(
        "/auth/register",
        json={
            "email": f"alice_{uuid.uuid4().hex[:8]}@example.com",
            "password": "password123!",
            "full_name": "Alice",
            "org_name": "Alice Org",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user_id"]
    assert data["active_org_id"]


@pytest.mark.asyncio
async def test_register_duplicate_email_fails(client: AsyncClient):
    email = f"bob_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": email,
        "password": "password123!",
        "full_name": "Bob",
        "org_name": "Bob Org",
    }
    r1 = await client.post("/auth/register", json=payload)
    assert r1.status_code == 201

    r2 = await client.post("/auth/register", json=payload)
    assert r2.status_code in (400, 409)
    # The implementation returns 400
    assert r2.status_code == 400
    assert "Email already registered" in r2.text


@pytest.mark.asyncio
async def test_login_happy_path_and_me(client: AsyncClient):
    email = f"carol_{uuid.uuid4().hex[:8]}@example.com"
    password = "password123!"
    reg = await client.post(
        "/auth/register",
        json={"email": email, "password": password, "full_name": "Carol", "org_name": "Carol Org"},
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]

    # Login
    login = await client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    login_data = login.json()
    assert "access_token" in login_data
    assert login_data["user_id"]
    assert login_data["active_org_id"]

    # /auth/me
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    me_data = me.json()
    assert me_data["id"] == login_data["user_id"]
    assert me_data["email"] == email
    assert isinstance(me_data.get("memberships", []), list)


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    bad = await client.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
    assert bad.status_code == 400
    assert "Invalid credentials" in bad.text


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_switch_org_requires_membership(client: AsyncClient):
    # Register user1 with org1
    reg1 = await client.post(
        "/auth/register",
        json={"email": f"u1_{uuid.uuid4().hex[:8]}@example.com", "password": "password123!", "org_name": "Org1"},
    )
    assert reg1.status_code == 201
    token1 = reg1.json()["access_token"]

    # Register user2 with org2
    reg2 = await client.post(
        "/auth/register",
        json={"email": f"u2_{uuid.uuid4().hex[:8]}@example.com", "password": "password123!", "org_name": "Org2"},
    )
    assert reg2.status_code == 201
    org2_id = reg2.json()["active_org_id"]

    # user1 tries to switch to org2 -> forbidden
    switch = await client.post(
        "/auth/orgs/switch",
        headers={"Authorization": f"Bearer {token1}"},
        json={"org_id": org2_id},
    )
    assert switch.status_code == 403
    assert "Not a member" in switch.text
