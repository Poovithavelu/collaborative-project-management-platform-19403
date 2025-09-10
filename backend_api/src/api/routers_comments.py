from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Body
from .authz import require_org_role
from .db import get_pool
from .schemas import CommentCreate, Comment

router = APIRouter(prefix="/comments", tags=["Comments"])


async def _assert_task_in_org(conn, task_id: str, org_id: str) -> str:
    pid = await conn.fetchval("select project_id from tasks where id=$1", task_id)
    if not pid:
        raise HTTPException(status_code=404, detail="Task not found")
    ok = await conn.fetchval("select 1 from projects where id=$1 and org_id=$2", pid, org_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not in this organization")
    return pid


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=Comment,
    summary="Create comment",
    description="Create a comment on a task. Requires member or higher.",
)
async def create_comment(
    data: CommentCreate = Body(...),
    ctx=Depends(require_org_role("member")),
) -> Comment:
    """Create a comment for a task in active org."""
    user_id, active_org_id, _role = ctx
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_task_in_org(conn, data.task_id, active_org_id)
        row = await conn.fetchrow(
            """
            insert into comments (task_id, body, created_by)
            values ($1, $2, $3)
            returning id, task_id, body, created_by
            """,
            data.task_id, data.body, user_id
        )
    return Comment(
        id=str(row["id"]),
        task_id=str(row["task_id"]),
        body=row["body"],
        created_by=str(row["created_by"]),
    )


# PUBLIC_INTERFACE
@router.get(
    "/by-task/{task_id}",
    response_model=List[Comment],
    summary="List comments for task",
    description="List comments for a given task in active org. Requires viewer or higher.",
)
async def list_comments(task_id: str, ctx=Depends(require_org_role("viewer"))) -> List[Comment]:
    """List comments for task."""
    _user_id, active_org_id, _role = ctx
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_task_in_org(conn, task_id, active_org_id)
        rows = await conn.fetch(
            "select id, task_id, body, created_by from comments where task_id=$1 order by created_at asc",
            task_id,
        )
    return [
        Comment(
            id=str(r["id"]),
            task_id=str(r["task_id"]),
            body=r["body"],
            created_by=str(r["created_by"]),
        )
        for r in rows
    ]
