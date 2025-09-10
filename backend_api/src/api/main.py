from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db_schema
from .routers_auth import router as auth_router
from .routers_projects import router as projects_router

openapi_tags = [
    {"name": "Authentication", "description": "Endpoints for user authentication and organization management."},
    {"name": "Projects", "description": "CRUD endpoints for projects within an organization."},
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


# Mount Routers
app.include_router(auth_router)
app.include_router(projects_router)
