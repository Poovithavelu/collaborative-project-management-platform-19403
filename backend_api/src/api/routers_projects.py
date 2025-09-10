from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Header, Body

from .db import get_pool
from .schemas import Project, ProjectCreate, ProjectUpdate
from .security import decode_token

router = APIRouter(prefix="/projects", tags=["Projects"])


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


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[Project],
    summary="List projects",
    description="List all projects within the caller's active organization context.",
)
async def list_projects(payload: dict = Depends(_get_current_user_payload)) -> List[Project]:
    """Return projects for the active organization in the JWT."""
    active_org_id = payload.get("active_org_id")
    if not active_org_id:
        raise HTTPException(status_code=400, detail="Active organization is not set")

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            select id, org_id, name, description, created_by, created_at
            from projects
            where org_id = $1
            order by created_at desc
            """,
            active_org_id,
        )

    projects: List[Project] = []
    for r in rows:
        projects.append(
            Project(
                id=str(r["id"]),
                org_id=str(r["org_id"]),
                name=r["name"],
                description=r["description"],
                created_by=str(r["created_by"]) if r["created_by"] else None,
                created_at=r["created_at"].isoformat(),
            )
        )
    return projects


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=Project,
    status_code=201,
    summary="Create project",
    description="Create a new project within the active organization. Uses JWT user_id as created_by.",
)
async def create_project(
    data: ProjectCreate = Body(...),
    payload: dict = Depends(_get_current_user_payload),
) -> Project:
    """Create a new project in the active organization."""
    user_id = payload.get("user_id")
    active_org_id = payload.get("active_org_id")
    if not user_id or not active_org_id:
        raise HTTPException(status_code=400, detail="Missing user_id or active_org_id in token")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            insert into projects (org_id, name, description, created_by)
            values ($1, $2, $3, $4)
            returning id, org_id, name, description, created_by, created_at
            """,
            active_org_id,
            data.name,
            data.description,
            user_id,
        )
    return Project(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        name=row["name"],
        description=row["description"],
        created_by=str(row["created_by"]) if row["created_by"] else None,
        created_at=row["created_at"].isoformat(),
    )


# PUBLIC_INTERFACE
@router.put(
    "/{project_id}",
    response_model=Project,
    summary="Update project",
    description="Update an existing project's name/description within the active organization.",
)
async def update_project(
    project_id: str,
    data: ProjectUpdate = Body(...),
    payload: dict = Depends(_get_current_user_payload),
) -> Project:
    """Update a project in the active organization; only fields provided are changed."""
    active_org_id = payload.get("active_org_id")
    if not active_org_id:
        raise HTTPException(status_code=400, detail="Active organization is not set")

    # Build dynamic update based on provided fields
    fields = []
    values = []
    if data.name is not None:
        fields.append("name = $%d" % (len(values) + 1))
        values.append(data.name)
    if data.description is not None:
        fields.append("description = $%d" % (len(values) + 1))
        values.append(data.description)

    if not fields:
        # Nothing to update; return current record if exists
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                select id, org_id, name, description, created_by, created_at
                from projects
                where id = $1 and org_id = $2
                """,
                project_id,
                active_org_id,
            )
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")
        return Project(
            id=str(row["id"]),
            org_id=str(row["org_id"]),
            name=row["name"],
            description=row["description"],
            created_by=str(row["created_by"]) if row["created_by"] else None,
            created_at=row["created_at"].isoformat(),
        )

    set_clause = ", ".join(fields)

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Update with org guard
        row = await conn.fetchrow(
            f"""
            update projects
            set {set_clause}
            where id = $%d and org_id = $%d
            returning id, org_id, name, description, created_by, created_at
            """ % (len(values) + 1, len(values) + 2),
            *values,
            project_id,
            active_org_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return Project(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        name=row["name"],
        description=row["description"],
        created_by=str(row["created_by"]) if row["created_by"] else None,
        created_at=row["created_at"].isoformat(),
    )
