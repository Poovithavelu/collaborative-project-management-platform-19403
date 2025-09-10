from __future__ import annotations

from typing import Optional, Literal, Tuple

from fastapi import Header, HTTPException, status, Depends

from .security import decode_token
from .db import get_pool

Role = Literal["owner", "admin", "member", "viewer"]

ROLE_RANK = {"viewer": 1, "member": 2, "admin": 3, "owner": 4}


async def _extract_payload(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload


# PUBLIC_INTERFACE
async def require_user(payload: dict = Depends(_extract_payload)) -> dict:
    """Validate JWT and return payload with user_id."""
    if not payload.get("user_id"):
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


# PUBLIC_INTERFACE
async def require_org_role(
    min_role: Role = "member",
):
    """Dependency factory to ensure the current user has at least given role in active_org."""
    async def _dep(payload: dict = Depends(require_user)) -> Tuple[str, str, Role]:
        user_id = payload["user_id"]
        active_org_id = payload.get("active_org_id")
        if not active_org_id:
            raise HTTPException(status_code=400, detail="Active organization is not set")

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "select role from memberships where user_id=$1 and org_id=$2",
                user_id, active_org_id
            )
            if not row:
                raise HTTPException(status_code=403, detail="Not a member of active organization")
            role: Role = row["role"]  # type: ignore
            if ROLE_RANK.get(role, 0) < ROLE_RANK.get(min_role, 0):
                raise HTTPException(status_code=403, detail=f"Requires role {min_role} or higher")
        return user_id, active_org_id, role
    return _dep
