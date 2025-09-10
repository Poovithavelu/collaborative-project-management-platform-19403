import asyncio
import os
import uuid
from typing import AsyncIterator, Iterator

import pytest
from httpx import AsyncClient
from fastapi import FastAPI

# Import application after setting env to ensure settings read correct vars
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRES_MINUTES", "60")

# The tests expect a running Postgres (e.g., provided by CI with env POSTGRES_* or POSTGRES_URL).
# Ensure a dedicated DB/schema is used by tests. If POSTGRES_URL is present, we use it.
# Otherwise rely on discrete POSTGRES_* variables that CI provides.


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def _ensure_db_env() -> None:
    """
    Ensure database environment variables exist for tests.
    NOTE: The CI environment should provide either POSTGRES_URL or POSTGRES_USER/PASSWORD/DB/HOST/PORT.
    We do not create a database process here.
    """
    # If no POSTGRES_URL and no discrete vars, mark tests to xfail early with a helpful message.
    has_url = bool(os.getenv("POSTGRES_URL"))
    has_parts = all(
        os.getenv(k)
        for k in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST")
    )
    if not (has_url or has_parts):
        pytest.skip("Database configuration not provided. Set POSTGRES_URL or discrete POSTGRES_* env vars.")


@pytest.fixture(scope="session")
async def app() -> AsyncIterator[FastAPI]:
    # Local import after env prepared
    from src.api.main import app as fastapi_app
    from src.api.db import init_db_schema

    # Initialize schema once for the test session
    await init_db_schema()
    yield fastapi_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(app=app, base_url="http://testserver") as ac:
        yield ac


# Utilities

async def register_user(client: AsyncClient, email: str = None, password: str = "password123!", org_name: str = None):
    if email is None:
        email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    if org_name is None:
        org_name = f"Org {uuid.uuid4().hex[:6]}"
    resp = await client.post(
        "/auth/register",
        json={"email": email, "password": password, "full_name": "Test User", "org_name": org_name},
    )
    return resp


def auth_headers(token: str | None) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}
