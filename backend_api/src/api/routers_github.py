from __future__ import annotations

import os


from fastapi import APIRouter, Depends, HTTPException, Body
import httpx

from .authz import require_org_role
from .db import get_pool
from .schemas import GitHubLinkRepoRequest, GitHubIssueCreate

router = APIRouter(prefix="/github", tags=["GitHub"])

GITHUB_API = "https://api.github.com"


async def _github_headers() -> dict:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="GitHub not configured")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


# PUBLIC_INTERFACE
@router.post(
    "/link-repo",
    summary="Link a GitHub repo",
    description="Link a GitHub repository to the active organization for future operations.",
)
async def link_repo(
    body: GitHubLinkRepoRequest = Body(...),
    ctx=Depends(require_org_role("admin")),
):
    """Store GitHub repo linkage for an org."""
    _user_id, active_org_id, _role = ctx
    if body.org_id != active_org_id:
        raise HTTPException(status_code=400, detail="org_id must equal active_org_id")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            insert into github_repos (org_id, repo_full_name, installation_id)
            values ($1, $2, $3)
            on conflict (org_id, repo_full_name) do update set installation_id=excluded.installation_id
            """,
            active_org_id, body.repo_full_name, body.installation_id
        )
    return {"linked": True}


# PUBLIC_INTERFACE
@router.post(
    "/create-issue",
    summary="Create GitHub issue",
    description="Create a GitHub issue for a project; requires a linked repo for the org.",
)
async def create_issue(
    body: GitHubIssueCreate = Body(...),
    ctx=Depends(require_org_role("member")),
):
    """Create issue in linked repo."""
    _user_id, active_org_id, _role = ctx
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Find any linked repo for org (simple approach)
        repo = await conn.fetchval(
            "select repo_full_name from github_repos where org_id=$1 order by created_at desc limit 1",
            active_org_id
        )
        if not repo:
            raise HTTPException(status_code=400, detail="No linked GitHub repo for this organization")
    headers = await _github_headers()
    owner_repo = repo
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner_repo}/issues",
            headers=headers,
            json={"title": body.title, "body": body.body or ""},
        )
        if resp.status_code >= 300:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        data = resp.json()
    return {"html_url": data.get("html_url"), "number": data.get("number")}
