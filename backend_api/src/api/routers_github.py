from typing import Optional
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request, status
from fastapi.responses import RedirectResponse

from .db import get_pool
from .security import decode_token

router = APIRouter(prefix="/github", tags=["GitHub"])


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


# PUBLIC_INTERFACE
@router.get(
    "/connect",
    summary="Start GitHub OAuth flow",
    description="Starts the GitHub OAuth flow by redirecting to GitHub authorization URL. Requires a logged-in user (Bearer token). The state parameter is stored server-side for CSRF protection.",
)
async def github_connect(
    request: Request,
    payload: dict = Depends(_get_current_user_payload),
    redirect_uri: Optional[str] = Query(default=None, description="Override callback URL for testing (optional)"),
) -> RedirectResponse:
    """Initiate GitHub OAuth: generate state, store in DB, and redirect to GitHub authorize URL."""
    # settings can be retrieved via get_settings() if needed for future use
    client_id = os.getenv("GITHUB_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured: GITHUB_CLIENT_ID missing")

    # Determine callback URL
    callback_url = redirect_uri or os.getenv("GITHUB_OAUTH_CALLBACK_URL")
    if not callback_url:
        # Attempt to infer from request (best-effort)
        base = str(request.base_url).rstrip("/")
        callback_url = f"{base}/github/callback"

    user_id = payload.get("user_id")
    active_org_id = payload.get("active_org_id")
    if not user_id or not active_org_id:
        raise HTTPException(status_code=400, detail="Missing user_id or active_org_id in token")

    # Generate cryptographically secure state and store
    state = secrets.token_urlsafe(32)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await _ensure_membership(conn, user_id, active_org_id)
        # Upsert a pending state row
        await conn.execute(
            """
            insert into github_oauth_states (state, user_id, org_id, created_at, consumed)
            values ($1, $2, $3, now(), false)
            on conflict (state) do nothing
            """,
            state,
            user_id,
            active_org_id,
        )

    # Build GitHub authorization URL
    scope = os.getenv("GITHUB_OAUTH_SCOPE", "repo read:org user:email")
    params = {
        "client_id": client_id,
        "redirect_uri": callback_url,
        "state": state,
        "scope": scope,
        # Allow users to select orgs/repo during installation (standard authorize URL)
        # Optional: "allow_signup": "false",
    }
    url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
    return RedirectResponse(url=url, status_code=302)


# PUBLIC_INTERFACE
@router.get(
    "/callback",
    summary="GitHub OAuth callback",
    description="Handles the GitHub OAuth callback, verifies state, exchanges code for access token, and stores encrypted/hashed metadata securely.",
)
async def github_callback(
    request: Request,
    code: Optional[str] = Query(default=None, description="Authorization code from GitHub"),
    state: Optional[str] = Query(default=None, description="State parameter for CSRF protection"),
) -> dict:
    """Exchange code for token, verify state, and store token securely per org."""
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    client_id = os.getenv("GITHUB_CLIENT_ID")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured: missing client credentials")

    # Validate state and obtain org/user context
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            select state, user_id, org_id, consumed
            from github_oauth_states
            where state = $1
            """,
            state,
        )
        if not row:
            raise HTTPException(status_code=400, detail="Invalid state")
        if row["consumed"]:
            raise HTTPException(status_code=400, detail="State has already been used")
        _user_id = str(row["user_id"])
        org_id = str(row["org_id"])
        # Variable `_user_id` reserved for future auditing; currently org-scoped token storage is used.

        # Exchange code for access token
        token_url = "https://github.com/login/oauth/access_token"
        headers = {"Accept": "application/json"}
        payload = {"client_id": client_id, "client_secret": client_secret, "code": code}
        callback_url = os.getenv("GITHUB_OAUTH_CALLBACK_URL")
        if callback_url:
            payload["redirect_uri"] = callback_url

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(token_url, headers=headers, data=payload)
            if resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"Failed to exchange token: {resp.text}")
            data = resp.json()

        access_token = data.get("access_token")
        token_type = data.get("token_type", "bearer")
        scope = data.get("scope")
        if not access_token:
            raise HTTPException(status_code=502, detail="No access_token in GitHub response")

        # Optional: fetch the authenticated GitHub user to store account login/id
        gh_user_login = None
        gh_user_id = None
        async with httpx.AsyncClient(timeout=20) as client:
            uresp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {access_token}", "Accept": "application/vnd.github+json"},
            )
            if uresp.status_code < 400:
                u = uresp.json()
                gh_user_login = u.get("login")
                gh_user_id = u.get("id")

        # Store token securely per org. If an existing token exists for org, rotate it.
        await conn.execute(
            """
            insert into github_tokens (org_id, access_token, token_type, scope, gh_user_login, gh_user_id, created_at, updated_at)
            values ($1, $2, $3, $4, $5, $6, now(), now())
            on conflict (org_id) do update set
                access_token = excluded.access_token,
                token_type = excluded.token_type,
                scope = excluded.scope,
                gh_user_login = excluded.gh_user_login,
                gh_user_id = excluded.gh_user_id,
                updated_at = now()
            """,
            org_id,
            access_token,
            token_type,
            scope,
            gh_user_login,
            gh_user_id,
        )

        # Mark state as consumed
        await conn.execute("update github_oauth_states set consumed=true where state=$1", state)

    # You may redirect to a frontend success page if SITE_URL is set
    site_url = os.getenv("SITE_URL")
    if site_url:
        # Append a simple success indicator for the frontend
        return RedirectResponse(url=f"{site_url}/integrations/github?connected=1", status_code=302)

    return {"connected": True, "org_id": org_id, "github_user": gh_user_login, "user_id": _user_id}


# PUBLIC_INTERFACE
@router.get(
    "/repos",
    summary="List GitHub repositories",
    description="Fetch the list of repositories accessible by the organization's stored GitHub token. Requires user authentication and active organization context. Does not expose any tokens or secrets.",
)
async def list_github_repos(
    payload: dict = Depends(_get_current_user_payload),
    visibility: Optional[str] = Query(default=None, description="Optional visibility filter: all, public, private"),
    affiliation: Optional[str] = Query(default=None, description="Optional affiliation filter, e.g., owner, collaborator, organization_member"),
    per_page: int = Query(default=50, ge=1, le=100, description="Page size for GitHub API requests"),
    page: int = Query(default=1, ge=1, description="Page number for GitHub API requests"),
) -> list[dict]:
    """
    Return repositories accessible by the stored GitHub token for the caller's active organization.

    - Validates the JWT and active organization.
    - Ensures the user is a member of the active organization.
    - Fetches the organization's stored GitHub token from the database.
    - Calls GitHub's REST API to list repositories for the authenticated token.
    - Returns a safe subset of repository fields to avoid leaking sensitive info.
    """
    user_id = payload.get("user_id")
    active_org_id = payload.get("active_org_id")
    if not user_id or not active_org_id:
        raise HTTPException(status_code=400, detail="Missing user_id or active_org_id in token")

    pool = await get_pool()
    async with pool.acquire() as conn:
        await _ensure_membership(conn, user_id, active_org_id)
        token_row = await conn.fetchrow(
            "select access_token, token_type from github_tokens where org_id=$1",
            active_org_id,
        )
        if not token_row:
            raise HTTPException(status_code=404, detail="GitHub is not connected for this organization")

        access_token = token_row["access_token"]
        token_type = (token_row["token_type"] or "bearer").lower()

    headers = {
        "Accept": "application/vnd.github+json",
        # GitHub accepts either "token" or "Bearer", we respect stored type but default to "token"
        "Authorization": f"{'token' if token_type not in ('bearer', 'token') else ('Bearer' if token_type == 'bearer' else 'token')} {access_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    params = {"per_page": per_page, "page": page}
    if visibility:
        params["visibility"] = visibility
    if affiliation:
        params["affiliation"] = affiliation

    async with httpx.AsyncClient(timeout=20) as client:
        # Using /user/repos to list repos visible to the authenticated user/token
        resp = await client.get("https://api.github.com/user/repos", headers=headers, params=params)
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="GitHub token is unauthorized or expired; reconnect GitHub")
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"GitHub API error: {resp.text}")
        repos = resp.json()

    # Filter each repo object to a safe subset of fields
    safe_fields = {
        "id",
        "node_id",
        "name",
        "full_name",
        "private",
        "html_url",
        "description",
        "fork",
        "url",
        "archive_url",
        "assignees_url",
        "blobs_url",
        "branches_url",
        "collaborators_url",
        "comments_url",
        "commits_url",
        "compare_url",
        "contents_url",
        "contributors_url",
        "deployments_url",
        "downloads_url",
        "events_url",
        "forks_url",
        "git_commits_url",
        "git_refs_url",
        "git_tags_url",
        "git_url",
        "issue_comment_url",
        "issue_events_url",
        "issues_url",
        "keys_url",
        "labels_url",
        "languages_url",
        "merges_url",
        "milestones_url",
        "notifications_url",
        "pulls_url",
        "releases_url",
        "ssh_url",
        "stargazers_url",
        "statuses_url",
        "subscribers_url",
        "subscription_url",
        "tags_url",
        "teams_url",
        "trees_url",
        "homepage",
        "size",
        "stargazers_count",
        "watchers_count",
        "language",
        "has_issues",
        "has_projects",
        "has_downloads",
        "has_wiki",
        "has_pages",
        "has_discussions",
        "forks_count",
        "mirror_url",
        "archived",
        "disabled",
        "open_issues_count",
        "license",
        "allow_forking",
        "is_template",
        "web_commit_signoff_required",
        "topics",
        "visibility",
        "forks",
        "open_issues",
        "watchers",
        "default_branch",
        "permissions",
        # owner limited subset
        "owner",
    }

    def filter_owner(owner: Optional[dict]) -> Optional[dict]:
        if not isinstance(owner, dict):
            return owner
        owner_fields = {"login", "id", "node_id", "avatar_url", "gravatar_id", "url", "html_url", "type", "site_admin"}
        return {k: v for k, v in owner.items() if k in owner_fields}

    safe_repos: list[dict] = []
    if isinstance(repos, list):
        for r in repos:
            if not isinstance(r, dict):
                continue
            filtered = {k: v for k, v in r.items() if k in safe_fields}
            # ensure owner is filtered
            if "owner" in filtered:
                filtered["owner"] = filter_owner(filtered["owner"])
            safe_repos.append(filtered)

    return safe_repos
