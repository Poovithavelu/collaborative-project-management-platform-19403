import uuid
import pytest
from httpx import AsyncClient


async def _register_get_token(client: AsyncClient):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/auth/register",
        json={"email": email, "password": "password123!", "full_name": "T", "org_name": f"Org {uuid.uuid4().hex[:6]}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"], resp.json()["active_org_id"]


async def _create_project(client: AsyncClient, token: str, name: str = "P1"):
    resp = await client.post(
        "/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "description": "desc"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_list_tasks_requires_auth(client: AsyncClient):
    resp = await client.get("/tasks")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_list_update_delete_task_flow(client: AsyncClient):
    token, _ = await _register_get_token(client)
    project_id = await _create_project(client, token)

    # Create task
    create = await client.post(
        "/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"project_id": project_id, "title": "Task 1", "description": "Do it"},
    )
    assert create.status_code == 201, create.text
    task = create.json()
    assert task["status"] == "todo"

    # List tasks for project
    lst = await client.get(
        "/tasks",
        headers={"Authorization": f"Bearer {token}"},
        params={"project_id": project_id},
    )
    assert lst.status_code == 200
    items = lst.json()
    assert any(t["id"] == task["id"] for t in items)

    # Update task status
    upd = await client.put(
        f"/tasks/{task['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "in_progress"},
    )
    assert upd.status_code == 200
    assert upd.json()["status"] == "in_progress"

    # Delete
    delete = await client.delete(f"/tasks/{task['id']}", headers={"Authorization": f"Bearer {token}"})
    assert delete.status_code == 204

    # Delete again should 404
    delete2 = await client.delete(f"/tasks/{task['id']}", headers={"Authorization": f"Bearer {token}"})
    assert delete2.status_code == 404


@pytest.mark.asyncio
async def test_org_isolation_on_tasks(client: AsyncClient):
    # user1 + org1
    token1, _ = await _register_get_token(client)
    p1 = await _create_project(client, token1, name="Org1 Project")

    # user2 + org2
    token2, _ = await _register_get_token(client)
    await _create_project(client, token2, name="Org2 Project")

    # user1 creates a task in org1
    t1 = await client.post(
        "/tasks",
        headers={"Authorization": f"Bearer {token1}"},
        json={"project_id": p1, "title": "Secret Task", "description": "private"},
    )
    assert t1.status_code == 201
    task1_id = t1.json()["id"]

    # user2 cannot list it (their list shouldn't include task1)
    lst2 = await client.get("/tasks", headers={"Authorization": f"Bearer {token2}"})
    assert lst2.status_code == 200
    assert all(item["id"] != task1_id for item in lst2.json())

    # user2 cannot update/delete it
    upd2 = await client.put(
        f"/tasks/{task1_id}", headers={"Authorization": f"Bearer {token2}"}, json={"status": "done"}
    )
    assert upd2.status_code == 404
    del2 = await client.delete(f"/tasks/{task1_id}", headers={"Authorization": f"Bearer {token2}"})
    assert del2.status_code == 404

    # but user1 can still see it
    lst1 = await client.get("/tasks", headers={"Authorization": f"Bearer {token1}"})
    assert lst1.status_code == 200
    assert any(item["id"] == task1_id for item in lst1.json())


@pytest.mark.asyncio
async def test_reorder_tasks_basic_flow(client: AsyncClient):
    token, _ = await _register_get_token(client)
    project_id = await _create_project(client, token)

    # Create 3 tasks
    ids = []
    for i in range(3):
        r = await client.post(
            "/tasks",
            headers={"Authorization": f"Bearer {token}"},
            json={"project_id": project_id, "title": f"T{i+1}", "description": None},
        )
        assert r.status_code == 201
        ids.append(r.json()["id"])

    # Reorder: reverse order_index
    patches = [{"task_id": tid, "order_index": idx} for idx, tid in enumerate(reversed(ids), start=1)]
    rr = await client.post(
        "/tasks/reorder",
        headers={"Authorization": f"Bearer {token}"},
        json={"project_id": project_id, "patches": patches},
    )
    assert rr.status_code == 200, rr.text
    body = rr.json()
    assert "updated_count" in body
    assert body["updated_count"] == 3


@pytest.mark.asyncio
async def test_tasks_filters_and_validation(client: AsyncClient):
    token, _ = await _register_get_token(client)
    project_id = await _create_project(client, token)
    # Create some tasks with various statuses
    t1 = await client.post(
        "/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"project_id": project_id, "title": "A", "status": "todo"},
    )
    assert t1.status_code == 201
    t2 = await client.post(
        "/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"project_id": project_id, "title": "B", "status": "done"},
    )
    assert t2.status_code == 201

    # Filter by status
    lst_done = await client.get(
        "/tasks",
        headers={"Authorization": f"Bearer {token}"},
        params={"project_id": project_id, "status": "done"},
    )
    assert lst_done.status_code == 200
    assert all(item["status"] == "done" for item in lst_done.json())

    # Missing auth on create
    no_auth = await client.post(
        "/tasks",
        json={"project_id": project_id, "title": "X"},
    )
    assert no_auth.status_code == 401
