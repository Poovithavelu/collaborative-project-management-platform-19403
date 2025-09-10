from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Header, Body, Path

from .db import get_pool
from .schemas import ProjectGithubLinkCreate, ProjectGithubLink
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


async def _assert_project_in_org(conn, project_id: str, org_id: str) -> None:
    """Ensure the given project belongs to the same org context."""
    exists = await conn.fetchval("select 1 from projects where id=$1 and org_id=$2", project_id, org_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Project not found in active organization")


# PUBLIC_INTERFACE
@router.post(
    "/{project_id}/link-repo",
    response_model=ProjectGithubLink,
    status_code=201,
    summary="Link GitHub repository to project",
    description="Link a GitHub repository to a project within the active organization. Stores association in the database.",
)
async def link_github_repo_to_project(
    project_id: str = Path(..., description="Project ID to link the repository to"),
    data: ProjectGithubLinkCreate = Body(...),
    payload: dict = Depends(_get_current_user_payload),
) -> ProjectGithubLink:
    """Create or update an association between a project and a GitHub repository for the active organization."""
    active_org_id = payload.get("active_org_id")
    if not active_org_id:
        raise HTTPException(status_code=400, detail="Active organization is not set")

    # Basic validation of repo_full_name format
    if "/" not in data.repo_full_name or len(data.repo_full_name.split("/")) != 2:
        raise HTTPException(status_code=422, detail="repo_full_name must be in the format 'owner/repo'")

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Ensure project exists and belongs to org
            await _assert_project_in_org(conn, project_id, active_org_id)

            # Upsert association; one repo per project (unique on project_id)
            row = await conn.fetchrow(
                """
                insert into project_github_repos
                    (org_id, project_id, repo_full_name, repo_id, repo_url, default_branch, created_at, updated_at)
                values
                    ($1, $2, $3, $4, $5, $6, now(), now())
                on conflict (project_id) do update set
                    org_id = excluded.org_id,
                    repo_full_name = excluded.repo_full_name,
                    repo_id = excluded.repo_id,
                    repo_url = excluded.repo_url,
                    default_branch = excluded.default_branch,
                    updated_at = now()
                returning id, org_id, project_id, repo_full_name, repo_id, repo_url, default_branch, created_at, updated_at
                """,
                active_org_id,
                project_id,
                data.repo_full_name,
                data.repo_id,
                data.repo_url,
                data.default_branch,
            )

    return ProjectGithubLink(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        project_id=str(row["project_id"]),
        repo_full_name=row["repo_full_name"],
        repo_id=int(row["repo_id"]) if row["repo_id"] is not None else None,
        repo_url=row["repo_url"],
        default_branch=row["default_branch"],
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
    )


# PUBLIC_INTERFACE
@router.get(
    "/{project_id}/linked-repo",
    response_model=ProjectGithubLink,
    summary="Get linked GitHub repository for project",
    description="Retrieve the GitHub repository association for a project in the active organization.",
)
async def get_linked_github_repo_for_project(
    project_id: str = Path(..., description="Project ID to retrieve the linked repository for"),
    payload: dict = Depends(_get_current_user_payload),
) -> ProjectGithubLink:
    """Get the associated GitHub repo for a project within the active organization."""
    active_org_id = payload.get("active_org_id")
    if not active_org_id:
        raise HTTPException(status_code=400, detail="Active organization is not set")

    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_project_in_org(conn, project_id, active_org_id)
        row = await conn.fetchrow(
            """
            select id, org_id, project_id, repo_full_name, repo_id, repo_url, default_branch, created_at, updated_at
            from project_github_repos
            where project_id = $1 and org_id = $2
            """,
            project_id, active_org_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="No GitHub repository linked to this project")

    return ProjectGithubLink(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        project_id=str(row["project_id"]),
        repo_full_name=row["repo_full_name"],
        repo_id=int(row["repo_id"]) if row["repo_id"] is not None else None,
        repo_url=row["repo_url"],
        default_branch=row["default_branch"],
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
    )
