from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db_schema, get_pool
from .routers_auth import router as auth_router
from .routers_projects import router as projects_router
from .routers_tasks import router as tasks_router
from .routers_comments import router as comments_router
from .routers_uploads import router as uploads_router
from .routers_billing import router as billing_router
from .routers_github import router as github_router
from .routers_project_github import router as project_github_router
from .routers_ai import router as ai_router

openapi_tags = [
    {"name": "Authentication", "description": "Endpoints for user authentication and organization management."},
    {"name": "Projects", "description": "CRUD endpoints for projects within an organization."},
    {"name": "Tasks", "description": "CRUD endpoints for tasks within a project in an organization."},
    {"name": "Comments", "description": "Endpoints to list and create comments on tasks within an organization."},
]

app = FastAPI(
    title="CollabTask Backend API",
    description="Backend API for CollabTask: authentication, authorization, projects, tasks, and integrations.",
    version="0.1.0",
    openapi_tags=openapi_tags,
)

settings = get_settings()
allow_origins = [o.strip() for o in settings.cors_allow_origins.split(",")] if settings.cors_allow_origins else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    """Initialize database schema on startup."""
    await init_db_schema()


@app.get("/", summary="Health Check")
def health_check():
    """Simple health check endpoint."""
    return {"message": "Healthy"}


# Middleware to log mutative requests to audit_log
@app.middleware("http")
async def audit_logging_middleware(request: Request, call_next):
    """
    Middleware that logs mutative API calls (POST/PUT/PATCH/DELETE) into audit_log.

    Captures:
    - occurred_at (default now())
    - user_id, org_id from Authorization (if available via routers decoding)
    - project_id/entity_id best-effort from path/body for known endpoints
    - entity_type inferred from path: auth/projects/tasks/comments/unknown
    - action inferred from method: post=create, put/patch=update, delete=delete
    - request_path and method
    - details: subset including query params and possibly request body (redacted for passwords)
    """
    method = request.method.upper()
    if method not in ("POST", "PUT", "PATCH", "DELETE"):
        return await call_next(request)

    # We need to read body safely; receive it and place back into request stream
    body_bytes = await request.body()
    async def receive():
        return {"type": "http.request", "body": body_bytes}
    request = Request(request.scope, receive=receive)

    # Parse minimal JSON if available
    json_body = None
    try:
        if body_bytes:
            json_body = await request.json()
    except Exception:
        json_body = None

    # Infer context from Authorization header if present
    auth_header = request.headers.get("authorization")
    user_id = None
    org_id = None
    try:
        if auth_header and auth_header.lower().startswith("bearer "):
            from .security import decode_token  # local import to avoid circular
            token = auth_header.split(" ", 1)[1]
            payload = decode_token(token)
            user_id = payload.get("user_id")
            org_id = payload.get("active_org_id")
    except Exception:
        # ignore token errors for audit fallback
        pass

    path = request.url.path
    # Infer entity_type and entity_id/project_id from path and body
    entity_type = "unknown"
    entity_id = None
    project_id = None

    if path.startswith("/projects"):
        entity_type = "project"
        # entity_id from path /projects/{id}
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "projects":
            if len(parts) >= 2:
                entity_id = parts[1] if len(parts) > 1 and parts[1] else None
        # attempt to extract from body for create
        if not entity_id and json_body and isinstance(json_body, dict):
            # no project_id available for create; leave None
            pass
    elif path.startswith("/tasks"):
        entity_type = "task"
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "tasks":
            if len(parts) >= 2:
                entity_id = parts[1] if len(parts) > 1 and parts[1] not in ("reorder",) else None
        if json_body and isinstance(json_body, dict):
            project_id = json_body.get("project_id") or project_id
    elif path.startswith("/comments"):
        entity_type = "comment"
        # entity_id for comments is available on response; we won't have it pre-insert; leave None
        if json_body and isinstance(json_body, dict):
            # could relate to a task
            pass
    elif path.startswith("/auth"):
        entity_type = "auth"

    # Map method to action
    action_map = {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}
    action = action_map.get(method, method.lower())

    # Redact sensitive fields
    if isinstance(json_body, dict):
        redacted = dict(json_body)
        if "password" in redacted:
            redacted["password"] = "***"
        details = {"body": redacted, "query": dict(request.query_params)}
    else:
        details = {"query": dict(request.query_params)}

    # Write audit log before processing to ensure logging even on errors (optional choice)
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                insert into audit_log (user_id, org_id, project_id, entity_type, entity_id, action, request_path, method, details)
                values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                user_id, org_id, project_id, entity_type, entity_id, action, path, method, details
            )
    except Exception:
        # Swallow audit failures to not block request handling
        pass

    response = await call_next(request)
    return response


# Mount Routers
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(tasks_router)
app.include_router(comments_router)
app.include_router(uploads_router)
app.include_router(billing_router)
app.include_router(github_router)
app.include_router(project_github_router)
app.include_router(ai_router)
