from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi import Body

from .db import get_pool
from .security import hash_password, verify_password, create_access_token, decode_token
from .schemas import RegisterRequest, LoginRequest, TokenResponse, UserProfile, Membership, SwitchOrgRequest

router = APIRouter(prefix="/auth", tags=["Authentication"])


async def _get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
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
@router.post(
    "/register",
    response_model=TokenResponse,
    summary="Register user and organization",
    description="Create a user with hashed password, an organization, and a membership. Returns an access token.",
    status_code=201,
)
async def register(data: RegisterRequest = Body(...)) -> TokenResponse:
    """Register a user, create an organization and membership, and return JWT token."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Ensure email is not taken
            existing = await conn.fetchval("select id from users where email=$1", str(data.email))
            if existing:
                raise HTTPException(status_code=400, detail="Email already registered")

            # Create user
            pw_hash = hash_password(data.password)
            user_row = await conn.fetchrow(
                "insert into users (email, password_hash, full_name) values ($1, $2, $3) returning id",
                str(data.email), pw_hash, data.full_name
            )
            user_id = str(user_row["id"])

            # Create org
            org_row = await conn.fetchrow(
                "insert into organizations (name, owner_user_id) values ($1, $2) returning id",
                data.org_name, user_id
            )
            org_id = str(org_row["id"])

            # Create membership with owner role
            await conn.execute(
                "insert into memberships (user_id, org_id, role) values ($1, $2, $3)",
                user_id, org_id, "owner"
            )

            # Set active org
            await conn.execute("update users set active_org_id=$1 where id=$2", org_id, user_id)

    token = create_access_token(user_id=user_id, active_org_id=org_id)
    return TokenResponse(access_token=token, token_type="bearer", user_id=user_id, active_org_id=org_id)


# PUBLIC_INTERFACE
@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login user",
    description="Authenticate user by email and password. Returns a JWT including active_org_id.",
)
async def login(data: LoginRequest = Body(...)) -> TokenResponse:
    """Login using email/password and return JWT."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select id, password_hash, active_org_id from users where email=$1", str(data.email)
        )
        if not row:
            raise HTTPException(status_code=400, detail="Invalid credentials")
        if not verify_password(data.password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="Invalid credentials")

        user_id = str(row["id"])
        active_org_id = str(row["active_org_id"]) if row["active_org_id"] else None

    token = create_access_token(user_id=user_id, active_org_id=active_org_id)
    return TokenResponse(access_token=token, token_type="bearer", user_id=user_id, active_org_id=active_org_id)


# PUBLIC_INTERFACE
@router.get(
    "/me",
    response_model=UserProfile,
    summary="Get current user",
    description="Returns the current user profile with memberships and active organization.",
)
async def me(payload: dict = Depends(_get_current_user)) -> UserProfile:
    """Return current user profile with memberships."""
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    pool = await get_pool()
    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "select id, email, full_name, active_org_id from users where id=$1", user_id
        )
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")

        membership_rows = await conn.fetch(
            """
            select m.org_id, o.name as org_name, m.role
            from memberships m
            join organizations o on o.id = m.org_id
            where m.user_id=$1
            """,
            user_id,
        )

    memberships: List[Membership] = [
        Membership(org_id=str(r["org_id"]), org_name=r["org_name"], role=r["role"]) for r in membership_rows
    ]
    return UserProfile(
        id=str(user_row["id"]),
        email=user_row["email"],
        full_name=user_row["full_name"],
        active_org_id=str(user_row["active_org_id"]) if user_row["active_org_id"] else None,
        memberships=memberships,
    )


# PUBLIC_INTERFACE
@router.post(
    "/orgs/switch",
    response_model=TokenResponse,
    summary="Switch active organization",
    description="Switch the user's active organization and return a new JWT with the updated active_org_id.",
)
async def switch_org(
    data: SwitchOrgRequest = Body(...),
    payload: dict = Depends(_get_current_user),
) -> TokenResponse:
    """Switch active organization to one the user is a member of and return new token."""
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Verify membership
        membership = await conn.fetchval(
            "select 1 from memberships where user_id=$1 and org_id=$2", user_id, data.org_id
        )
        if not membership:
            raise HTTPException(status_code=403, detail="Not a member of the specified organization")

        await conn.execute("update users set active_org_id=$1 where id=$2", data.org_id, user_id)

    token = create_access_token(user_id=user_id, active_org_id=data.org_id)
    return TokenResponse(access_token=token, token_type="bearer", user_id=user_id, active_org_id=data.org_id)
