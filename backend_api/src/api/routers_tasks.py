from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Header, Body, Query

from .db import get_pool
from .schemas import Task, TaskCreate, TaskUpdate
from .security import decode_token

router = APIRouter(prefix="/tasks", tags=["Tasks"])


async def _get_current_user_payload(authorization: Optional[str] = Header(default=None)) -> dict:
    """Extract and validate user info from Bearer token."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload


async def _assert_project_in_org(conn, project_id: Optional[str], org_id: str) -> None:
    """Ensure the given project (if provided) belongs to the same org context."""
    if project_id is None:
        return
    exists = await conn.fetchval("select 1 from projects where id=$1 and org_id=$2", project_id, org_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Project not found in active organization")


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[Task],
    summary="List tasks",
    description="List tasks within the caller's active organization. Optionally filter by project_id and status.",
)
async def list_tasks(
    payload: dict = Depends(_get_current_user_payload),
    project_id: Optional[str] = Query(default=None, description="Filter tasks by project ID"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter tasks by status"),
) -> List[Task]:
    """Return tasks for the active organization; optional filters for project and status."""
    active_org_id = payload.get("active_org_id")
    if not active_org_id:
        raise HTTPException(status_code=400, detail="Active organization is not set")

    pool = await get_pool()
    async with pool.acquire() as conn:
        params = [active_org_id]
        where = ["org_id = $1"]
        if project_id:
            await _assert_project_in_org(conn, project_id, active_org_id)
            where.append(f"project_id = ${len(params) + 1}")
            params.append(project_id)
        if status_filter:
            where.append(f"status = ${len(params) + 1}")
            params.append(status_filter)
        where_clause = " and ".join(where)

        rows = await conn.fetch(
            f"""
            select id, org_id, project_id, title, description, status, assignee_id, created_by, created_at
            from tasks
            where {where_clause}
            order by created_at desc
            """,
            *params,
        )

    tasks: List[Task] = []
    for r in rows:
        tasks.append(
            Task(
                id=str(r["id"]),
                org_id=str(r["org_id"]),
                project_id=str(r["project_id"]) if r["project_id"] else None,
                title=r["title"],
                description=r["description"],
                status=r["status"],
                assignee_id=str(r["assignee_id"]) if r["assignee_id"] else None,
                created_by=str(r["created_by"]) if r["created_by"] else None,
                created_at=r["created_at"].isoformat(),
            )
        )
    return tasks


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=Task,
    status_code=201,
    summary="Create task",
    description="Create a new task within the active organization and a specified project.",
)
async def create_task(
    data: TaskCreate = Body(...),
    payload: dict = Depends(_get_current_user_payload),
) -> Task:
    """Create a new task in the active organization and specified project."""
    user_id = payload.get("user_id")
    active_org_id = payload.get("active_org_id")
    if not user_id or not active_org_id:
        raise HTTPException(status_code=400, detail="Missing user_id or active_org_id in token")

    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_project_in_org(conn, data.project_id, active_org_id)
        row = await conn.fetchrow(
            """
            insert into tasks (org_id, project_id, title, description, status, assignee_id, created_by)
            values ($1, $2, $3, $4, coalesce($5, 'todo'), $6, $7)
            returning id, org_id, project_id, title, description, status, assignee_id, created_by, created_at
            """,
            active_org_id,
            data.project_id,
            data.title,
            data.description,
            data.status,
            data.assignee_id,
            user_id,
        )
    return Task(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        project_id=str(row["project_id"]) if row["project_id"] else None,
        title=row["title"],
        description=row["description"],
        status=row["status"],
        assignee_id=str(row["assignee_id"]) if row["assignee_id"] else None,
        created_by=str(row["created_by"]) if row["created_by"] else None,
        created_at=row["created_at"].isoformat(),
    )


# PUBLIC_INTERFACE
@router.put(
    "/{task_id}",
    response_model=Task,
    summary="Update task",
    description="Update an existing task's fields within the active organization.",
)
async def update_task(
    task_id: str,
    data: TaskUpdate = Body(...),
    payload: dict = Depends(_get_current_user_payload),
) -> Task:
    """Update a task in the active organization; only provided fields are changed."""
    active_org_id = payload.get("active_org_id")
    if not active_org_id:
        raise HTTPException(status_code=400, detail="Active organization is not set")

    fields = []
    values = []
    if data.title is not None:
        fields.append("title = $%d" % (len(values) + 1))
        values.append(data.title)
    if data.description is not None:
        fields.append("description = $%d" % (len(values) + 1))
        values.append(data.description)
    if data.status is not None:
        fields.append("status = $%d" % (len(values) + 1))
        values.append(data.status)
    # Note: assignee can be set to None to unassign
    if data.assignee_id is not None:
        fields.append("assignee_id = $%d" % (len(values) + 1))
        values.append(data.assignee_id)

    if not fields:
        # Nothing to update; return current record if exists
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                select id, org_id, project_id, title, description, status, assignee_id, created_by, created_at
                from tasks
                where id = $1 and org_id = $2
                """,
                task_id,
                active_org_id,
            )
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return Task(
            id=str(row["id"]),
            org_id=str(row["org_id"]),
            project_id=str(row["project_id"]) if row["project_id"] else None,
            title=row["title"],
            description=row["description"],
            status=row["status"],
            assignee_id=str(row["assignee_id"]) if row["assignee_id"] else None,
            created_by=str(row["created_by"]) if row["created_by"] else None,
            created_at=row["created_at"].isoformat(),
        )

    set_clause = ", ".join(fields)

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            update tasks
            set {set_clause}
            where id = $%d and org_id = $%d
            returning id, org_id, project_id, title, description, status, assignee_id, created_by, created_at
            """ % (len(values) + 1, len(values) + 2),
            *values,
            task_id,
            active_org_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return Task(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        project_id=str(row["project_id"]) if row["project_id"] else None,
        title=row["title"],
        description=row["description"],
        status=row["status"],
        assignee_id=str(row["assignee_id"]) if row["assignee_id"] else None,
        created_by=str(row["created_by"]) if row["created_by"] else None,
        created_at=row["created_at"].isoformat(),
    )


# PUBLIC_INTERFACE
@router.delete(
    "/{task_id}",
    status_code=204,
    summary="Delete task",
    description="Delete a task within the active organization.",
)
async def delete_task(
    task_id: str,
    payload: dict = Depends(_get_current_user_payload),
) -> None:
    """Delete a task in the active organization."""
    active_org_id = payload.get("active_org_id")
    if not active_org_id:
        raise HTTPException(status_code=400, detail="Active organization is not set")

    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("delete from tasks where id=$1 and org_id=$2", task_id, active_org_id)
        # asyncpg returns 'DELETE <count>'
        if not result.endswith(" 1"):
            # If 0 rows deleted, treat as not found
            raise HTTPException(status_code=404, detail="Task not found")
    return None
