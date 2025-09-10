from typing import Optional
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Header, UploadFile, File, Form
from .db import get_pool
from .security import decode_token
from .schemas import Attachment

router = APIRouter(prefix="/uploads", tags=["Uploads"])

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")


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


async def _ensure_membership(conn, user_id: str, org_id: str) -> None:
    """Ensure the user is a member of the organization."""
    exists = await conn.fetchval("select 1 from memberships where user_id=$1 and org_id=$2", user_id, org_id)
    if not exists:
        raise HTTPException(status_code=403, detail="Not a member of the active organization")


async def _assert_project_in_org(conn, project_id: str, org_id: str) -> None:
    exists = await conn.fetchval("select 1 from projects where id=$1 and org_id=$2", project_id, org_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Project not found in active organization")


async def _assert_task_in_org(conn, task_id: str, org_id: str) -> None:
    exists = await conn.fetchval("select 1 from tasks where id=$1 and org_id=$2", task_id, org_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Task not found in active organization")


def _ensure_upload_dir() -> None:
    """Create upload directory if missing."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)


# PUBLIC_INTERFACE
@router.post(
    "/project",
    response_model=Attachment,
    summary="Upload file to project",
    description="Accepts multipart form-data (file) to upload and attach to a project. Stores the file locally and records metadata.",
)
async def upload_to_project(
    payload: dict = Depends(_get_current_user_payload),
    project_id: str = Form(..., description="Project ID to attach file to"),
    file: UploadFile = File(..., description="File to upload"),
) -> Attachment:
    """Upload a file and attach it to a project within the caller's active organization."""
    user_id = payload.get("user_id")
    active_org_id = payload.get("active_org_id")
    if not user_id or not active_org_id:
        raise HTTPException(status_code=400, detail="Missing user_id or active_org_id in token")

    _ensure_upload_dir()

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_membership(conn, user_id, active_org_id)
            await _assert_project_in_org(conn, project_id, active_org_id)

            # Save file to disk with a unique name under uploads/
            ext = os.path.splitext(file.filename or "")[1]
            file_id = str(uuid.uuid4())
            stored_name = f"{file_id}{ext}"
            storage_path = os.path.join(UPLOAD_DIR, stored_name)

            size_bytes = 0
            with open(storage_path, "wb") as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    out.write(chunk)

            row = await conn.fetchrow(
                """
                insert into attachments (org_id, project_id, task_id, uploader_id, filename, content_type, size_bytes, storage_path)
                values ($1, $2, $3, $4, $5, $6, $7, $8)
                returning id, org_id, project_id, task_id, uploader_id, filename, content_type, size_bytes, storage_path, created_at
                """,
                active_org_id, project_id, None, user_id, file.filename, file.content_type, size_bytes, storage_path
            )

    return Attachment(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        project_id=str(row["project_id"]) if row["project_id"] else None,
        task_id=str(row["task_id"]) if row["task_id"] else None,
        uploader_id=str(row["uploader_id"]) if row["uploader_id"] else None,
        filename=row["filename"],
        content_type=row["content_type"],
        size_bytes=int(row["size_bytes"]) if row["size_bytes"] is not None else None,
        storage_path=row["storage_path"],
        created_at=row["created_at"].isoformat() if row["created_at"] else datetime.utcnow().isoformat(),
    )


# PUBLIC_INTERFACE
@router.post(
    "/task",
    response_model=Attachment,
    summary="Upload file to task",
    description="Accepts multipart form-data (file) to upload and attach to a task. Stores file locally and records metadata.",
)
async def upload_to_task(
    payload: dict = Depends(_get_current_user_payload),
    task_id: str = Form(..., description="Task ID to attach file to"),
    file: UploadFile = File(..., description="File to upload"),
) -> Attachment:
    """Upload a file and attach it to a task within the caller's active organization."""
    user_id = payload.get("user_id")
    active_org_id = payload.get("active_org_id")
    if not user_id or not active_org_id:
        raise HTTPException(status_code=400, detail="Missing user_id or active_org_id in token")

    _ensure_upload_dir()

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_membership(conn, user_id, active_org_id)
            await _assert_task_in_org(conn, task_id, active_org_id)

            ext = os.path.splitext(file.filename or "")[1]
            file_id = str(uuid.uuid4())
            stored_name = f"{file_id}{ext}"
            storage_path = os.path.join(UPLOAD_DIR, stored_name)

            size_bytes = 0
            with open(storage_path, "wb") as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    out.write(chunk)

            row = await conn.fetchrow(
                """
                insert into attachments (org_id, project_id, task_id, uploader_id, filename, content_type, size_bytes, storage_path)
                select $1, t.project_id, t.id, $2, $3, $4, $5, $6
                from tasks t
                where t.id = $7 and t.org_id = $1
                returning id, org_id, project_id, task_id, uploader_id, filename, content_type, size_bytes, storage_path, created_at
                """,
                active_org_id, user_id, file.filename, file.content_type, size_bytes, storage_path, task_id
            )

    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

    return Attachment(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        project_id=str(row["project_id"]) if row["project_id"] else None,
        task_id=str(row["task_id"]) if row["task_id"] else None,
        uploader_id=str(row["uploader_id"]) if row["uploader_id"] else None,
        filename=row["filename"],
        content_type=row["content_type"],
        size_bytes=int(row["size_bytes"]) if row["size_bytes"] is not None else None,
        storage_path=row["storage_path"],
        created_at=row["created_at"].isoformat() if row["created_at"] else datetime.utcnow().isoformat(),
    )
