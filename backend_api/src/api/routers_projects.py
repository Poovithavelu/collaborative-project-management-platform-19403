from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Body
from .authz import require_org_role
from .db import get_pool
from .schemas import ProjectCreate, ProjectUpdate, Project

router = APIRouter(prefix="/projects", tags=["Projects"])


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=Project,
    status_code=201,
    summary="Create project",
    description="Create a new project within the active organization. Requires member or higher.",
)
async def create_project(
    data: ProjectCreate = Body(...),
    ctx=Depends(require_org_role("member")),
) -> Project:
    """Create a project in active org."""
    user_id, active_org_id, _role = ctx
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            insert into projects (org_id, name, description, created_by)
            values ($1, $2, $3, $4)
            returning id, org_id, name, description, created_by
            """,
            active_org_id, data.name, data.description, user_id
        )
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create project")
    return Project(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        name=row["name"],
        description=row["description"],
        created_by=str(row["created_by"]),
    )


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[Project],
    summary="List projects",
    description="List projects in the active organization. Requires viewer or higher.",
)
async def list_projects(ctx=Depends(require_org_role("viewer"))) -> List[Project]:
    """List projects for active org."""
    _user_id, active_org_id, _role = ctx
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "select id, org_id, name, description, created_by from projects where org_id=$1 order by created_at desc",
            active_org_id
        )
    return [
        Project(
            id=str(r["id"]),
            org_id=str(r["org_id"]),
            name=r["name"],
            description=r["description"],
            created_by=str(r["created_by"]),
        )
        for r in rows
    ]


# PUBLIC_INTERFACE
@router.get(
    "/{project_id}",
    response_model=Project,
    summary="Get project",
    description="Get a single project by ID (must belong to active organization).",
)
async def get_project(project_id: str, ctx=Depends(require_org_role("viewer"))) -> Project:
    """Get a project by id in active org."""
    _user_id, active_org_id, _role = ctx
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select id, org_id, name, description, created_by from projects where id=$1 and org_id=$2",
            project_id, active_org_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")
    return Project(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        name=row["name"],
        description=row["description"],
        created_by=str(row["created_by"]),
    )


# PUBLIC_INTERFACE
@router.patch(
    "/{project_id}",
    response_model=Project,
    summary="Update project",
    description="Update project fields. Requires admin or owner.",
)
async def update_project(
    project_id: str,
    data: ProjectUpdate = Body(...),
    ctx=Depends(require_org_role("admin")),
) -> Project:
    """Update a project in active org."""
    _user_id, active_org_id, _role = ctx
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "select id from projects where id=$1 and org_id=$2", project_id, active_org_id
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Project not found")
        row = await conn.fetchrow(
            """
            update projects set
              name = coalesce($1, name),
              description = coalesce($2, description)
            where id=$3
            returning id, org_id, name, description, created_by
            """,
            data.name, data.description, project_id
        )
    return Project(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        name=row["name"],
        description=row["description"],
        created_by=str(row["created_by"]),
    )


# PUBLIC_INTERFACE
@router.delete(
    "/{project_id}",
    status_code=204,
    summary="Delete project",
    description="Delete a project. Requires owner or admin.",
)
async def delete_project(project_id: str, ctx=Depends(require_org_role("admin"))) -> None:
    """Delete project from active org."""
    _user_id, active_org_id, _role = ctx
    pool = await get_pool()
    async with pool.acquire() as conn:
        res = await conn.execute("delete from projects where id=$1 and org_id=$2", project_id, active_org_id)
        if res.split()[-1] == "0":
            raise HTTPException(status_code=404, detail="Project not found")
