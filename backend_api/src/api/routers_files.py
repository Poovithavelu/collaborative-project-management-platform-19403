from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Response
from .authz import require_org_role
from .db import get_pool
from .schemas import FileUploadResponse

router = APIRouter(prefix="/files", tags=["Files"])


# PUBLIC_INTERFACE
@router.post(
    "/upload",
    response_model=FileUploadResponse,
    summary="Upload file",
    description="Upload a file associated with the active organization. Requires member or higher.",
)
async def upload_file(
    f: UploadFile = File(...),
    ctx=Depends(require_org_role("member")),
) -> FileUploadResponse:
    """Upload and store a file in DB linked to active org."""
    user_id, active_org_id, _role = ctx
    blob = await f.read()
    if len(blob) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            insert into files (org_id, filename, content_type, size_bytes, data, uploaded_by)
            values ($1, $2, $3, $4, $5, $6)
            returning id, filename, content_type
            """,
            active_org_id, f.filename, f.content_type, len(blob), blob, user_id
        )
    return FileUploadResponse(file_id=str(row["id"]), filename=row["filename"], content_type=row["content_type"])


# PUBLIC_INTERFACE
@router.get(
    "/{file_id}",
    summary="Download file",
    description="Download a stored file if it belongs to active org.",
)
async def download_file(file_id: str, ctx=Depends(require_org_role("viewer"))) -> Response:
    """Download file binary."""
    _user_id, active_org_id, _role = ctx
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select filename, content_type, data from files where id=$1 and org_id=$2",
            file_id, active_org_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        content_type = row["content_type"] or "application/octet-stream"
        return Response(
            content=bytes(row["data"]),
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{row["filename"]}"'}
        )
