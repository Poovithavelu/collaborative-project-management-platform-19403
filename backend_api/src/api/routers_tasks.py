from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from .authz import require_org_role
from .db import get_pool
from .schemas import TaskCreate, TaskUpdate, Task

router = APIRouter(prefix="/tasks", tags=["Tasks"])


async def _assert_project_in_org(conn, project_id: str, org_id: str) -> None:
    ok = await conn.fetchval("select 1 from projects where id=$1 and org_id=$2", project_id, org_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found in this organization")


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=Task,
    status_code=201,
    summary="Create task",
    description="Create a task within a project in the active organization. Requires member or higher.",
)
async def create_task(
    data: TaskCreate = Body(...),
    ctx=Depends(require_org_role("member")),
) -> Task:
    """Create task in a project."""
    user_id, active_org_id, _role = ctx
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_project_in_org(conn, data.project_id, active_org_id)
        row = await conn.fetchrow(
            """
            insert into tasks (project_id, title, description, assignee_id, status, priority, created_by)
            values ($1, $2, $3, $4, $5, $6, $7)
            returning id, project_id, title, description, assignee_id, status, priority, created_by
            """,
            data.project_id, data.title, data.description, data.assignee_id, data.status, data.priority, user_id
        )
    return Task(
        id=str(row["id"]),
        project_id=str(row["project_id"]),
        title=row["title"],
        description=row["description"],
        assignee_id=str(row["assignee_id"]) if row["assignee_id"] else None,
        status=row["status"],
        priority=row["priority"],
        created_by=str(row["created_by"]),
    )


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[Task],
    summary="List tasks",
    description="List tasks filtered by project_id in the active org.",
)
async def list_tasks(
    project_id: str = Query(..., description="Filter by project ID"),
    ctx=Depends(require_org_role("viewer")),
) -> List[Task]:
    """List tasks for a project in active org."""
    _user_id, active_org_id, _role = ctx
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_project_in_org(conn, project_id, active_org_id)
        rows = await conn.fetch(
            """
            select t.id, t.project_id, t.title, t.description, t.assignee_id, t.status, t.priority, t.created_by
            from tasks t
            where t.project_id=$1
            order by t.created_at desc
            """,
            project_id,
        )
    return [
        Task(
            id=str(r["id"]),
            project_id=str(r["project_id"]),
            title=r["title"],
            description=r["description"],
            assignee_id=str(r["assignee_id"]) if r["assignee_id"] else None,
            status=r["status"],
            priority=r["priority"],
            created_by=str(r["created_by"]),
        )
        for r in rows
    ]


# PUBLIC_INTERFACE
@router.patch(
    "/{task_id}",
    response_model=Task,
    summary="Update task",
    description="Update a task fields. Requires member or higher.",
)
async def update_task(
    task_id: str,
    data: TaskUpdate = Body(...),
    ctx=Depends(require_org_role("member")),
) -> Task:
    """Update a task in active org."""
    _user_id, active_org_id, _role = ctx
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Ensure the task belongs to a project in this org
        pid = await conn.fetchval("select project_id from tasks where id=$1", task_id)
        if not pid:
            raise HTTPException(status_code=404, detail="Task not found")
        await _assert_project_in_org(conn, pid, active_org_id)
        row = await conn.fetchrow(
            """
            update tasks set
              title = coalesce($1, title),
              description = coalesce($2, description),
              assignee_id = coalesce($3, assignee_id),
              status = coalesce($4, status),
              priority = coalesce($5, priority)
            where id=$6
            returning id, project_id, title, description, assignee_id, status, priority, created_by
            """,
            data.title, data.description, data.assignee_id, data.status, data.priority, task_id
        )
    return Task(
        id=str(row["id"]),
        project_id=str(row["project_id"]),
        title=row["title"],
        description=row["description"],
        assignee_id=str(row["assignee_id"]) if row["assignee_id"] else None,
        status=row["status"],
        priority=row["priority"],
        created_by=str(row["created_by"]),
    )


# PUBLIC_INTERFACE
@router.delete(
    "/{task_id}",
    status_code=204,
    summary="Delete task",
    description="Delete a task. Requires admin or owner.",
)
async def delete_task(task_id: str, ctx=Depends(require_org_role("admin"))) -> None:
    """Delete task."""
    _user_id, active_org_id, _role = ctx
    pool = await get_pool()
    async with pool.acquire() as conn:
        pid = await conn.fetchval("select project_id from tasks where id=$1", task_id)
        if not pid:
            raise HTTPException(status_code=404, detail="Task not found")
        await _assert_project_in_org(conn, pid, active_org_id)
        await conn.execute("delete from tasks where id=$1", task_id)
