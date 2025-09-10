import datetime as dt
from typing import Optional, Any, Dict

import jwt
from passlib.context import CryptContext

from .config import get_settings

# Initialize passlib context for bcrypt hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# PUBLIC_INTERFACE
def hash_password(plain: str) -> str:
    """Hash a plaintext password."""
    return pwd_context.hash(plain)


# PUBLIC_INTERFACE
def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a hash."""
    return pwd_context.verify(plain, hashed)


# PUBLIC_INTERFACE
def create_access_token(user_id: str, active_org_id: Optional[str]) -> str:
    """Create a signed JWT including user_id and active_org_id with expiry."""
    settings = get_settings()
    now = dt.datetime.utcnow()
    payload: Dict[str, Any] = {
        "sub": user_id,
        "user_id": user_id,
        "active_org_id": active_org_id,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=settings.jwt_expires_minutes)).timestamp()),
        "scope": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    # PyJWT returns str in v2, ensure type is str for downstream usage
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


# PUBLIC_INTERFACE
def decode_token(token: str) -> dict:
    """Decode and verify a JWT token."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
