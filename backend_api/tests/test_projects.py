import uuid
import pytest
from httpx import AsyncClient


async def _register_get_token(client: AsyncClient):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/auth/register",
        json={"email": email, "password": "password123!", "full_name": "X", "org_name": f"Org {uuid.uuid4().hex[:6]}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_list_projects_requires_auth(client: AsyncClient):
    resp = await client.get("/projects")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_and_list_projects_happy_path(client: AsyncClient):
    token = await _register_get_token(client)

    # Create
    create = await client.post(
        "/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Project A", "description": "First"},
    )
    assert create.status_code == 201, create.text
    proj = create.json()
    assert proj["name"] == "Project A"
    assert proj["description"] == "First"
    assert proj["id"]

    # List
    lst = await client.get("/projects", headers={"Authorization": f"Bearer {token}"})
    assert lst.status_code == 200, lst.text
    items = lst.json()
    assert any(p["id"] == proj["id"] for p in items)


@pytest.mark.asyncio
async def test_update_project_and_org_isolation(client: AsyncClient):
    token1 = await _register_get_token(client)
    token2 = await _register_get_token(client)

    # User1 creates project
    p1 = await client.post(
        "/projects",
        headers={"Authorization": f"Bearer {token1}"},
        json={"name": "Org1 Project", "description": "desc"},
    )
    assert p1.status_code == 201
    proj_id = p1.json()["id"]

    # User2 attempts to update user1 project -> should 404 (not found in their org)
    upd_forbidden = await client.put(
        f"/projects/{proj_id}",
        headers={"Authorization": f"Bearer {token2}"},
        json={"name": "Hacked"},
    )
    assert upd_forbidden.status_code == 404

    # User1 updates their project
    upd = await client.put(
        f"/projects/{proj_id}",
        headers={"Authorization": f"Bearer {token1}"},
        json={"name": "Updated Name"},
    )
    assert upd.status_code == 200
    assert upd.json()["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_update_project_no_changes_returns_current(client: AsyncClient):
    token = await _register_get_token(client)
    created = await client.post(
        "/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "NoChange", "description": "D"},
    )
    assert created.status_code == 201
    proj_id = created.json()["id"]

    # Send empty body to trigger "no fields" path returning current record
    resp = await client.put(f"/projects/{proj_id}", headers={"Authorization": f"Bearer {token}"}, json={})
    assert resp.status_code == 200
    assert resp.json()["id"] == proj_id
