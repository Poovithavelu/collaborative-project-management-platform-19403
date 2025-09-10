from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Header, Body, Query

from .db import get_pool
from .schemas import Comment, CommentCreate
from .security import decode_token

router = APIRouter(prefix="/comments", tags=["Comments"])


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


async def _assert_task_in_org(conn, task_id: str, org_id: str) -> None:
    """Ensure the given task belongs to the same org context."""
    exists = await conn.fetchval("select 1 from tasks where id=$1 and org_id=$2", task_id, org_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Task not found in active organization")


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[Comment],
    summary="List comments by task",
    description="List comments for a given task_id within the caller's active organization.",
)
async def list_comments(
    payload: dict = Depends(_get_current_user_payload),
    task_id: str = Query(..., description="Task ID to list comments for"),
) -> List[Comment]:
    """Return comments for the specified task within the active org context."""
    active_org_id = payload.get("active_org_id")
    if not active_org_id:
        raise HTTPException(status_code=400, detail="Active organization is not set")

    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_task_in_org(conn, task_id, active_org_id)
        rows = await conn.fetch(
            """
            select id, org_id, task_id, author_id, content, created_at
            from comments
            where org_id=$1 and task_id=$2
            order by created_at asc
            """,
            active_org_id, task_id
        )

    comments: List[Comment] = []
    for r in rows:
        comments.append(
            Comment(
                id=str(r["id"]),
                org_id=str(r["org_id"]),
                task_id=str(r["task_id"]),
                author_id=str(r["author_id"]) if r["author_id"] else None,
                content=r["content"],
                created_at=r["created_at"].isoformat(),
            )
        )
    return comments


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=Comment,
    status_code=201,
    summary="Create comment",
    description="Create a new comment on a task within the active organization. Uses JWT user_id as author_id.",
)
async def create_comment(
    data: CommentCreate = Body(...),
    payload: dict = Depends(_get_current_user_payload),
) -> Comment:
    """Create a new comment on a task in the active organization."""
    user_id = payload.get("user_id")
    active_org_id = payload.get("active_org_id")
    if not user_id or not active_org_id:
        raise HTTPException(status_code=400, detail="Missing user_id or active_org_id in token")

    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_task_in_org(conn, data.task_id, active_org_id)
        row = await conn.fetchrow(
            """
            insert into comments (org_id, task_id, author_id, content)
            values ($1, $2, $3, $4)
            returning id, org_id, task_id, author_id, content, created_at
            """,
            active_org_id, data.task_id, user_id, data.content
        )

    return Comment(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        task_id=str(row["task_id"]),
        author_id=str(row["author_id"]) if row["author_id"] else None,
        content=row["content"],
        created_at=row["created_at"].isoformat(),
    )
