from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field

# PUBLIC_INTERFACE
class RegisterRequest(BaseModel):
    """Request body for user registration including initial organization creation."""
    email: EmailStr = Field(..., description="Unique user email address")
    password: str = Field(..., min_length=8, description="Password with minimum 8 characters")
    full_name: Optional[str] = Field(default=None, description="User full name")
    org_name: str = Field(..., description="Name of the initial organization to create")

# PUBLIC_INTERFACE
class LoginRequest(BaseModel):
    """Request body for user login."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")

# PUBLIC_INTERFACE
class TokenResponse(BaseModel):
    """Response containing access token and context identifiers."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type, always 'bearer'")
    user_id: str = Field(..., description="Authenticated user's ID")
    active_org_id: Optional[str] = Field(default=None, description="Active organization context ID")

# PUBLIC_INTERFACE
class Membership(BaseModel):
    """A single organization membership entry."""
    org_id: str = Field(..., description="Organization ID")
    org_name: str = Field(..., description="Organization name")
    role: str = Field(..., description="Role of the user in the organization (e.g., owner, admin, member)")

# PUBLIC_INTERFACE
class UserProfile(BaseModel):
    """Current user profile with memberships and active organization context."""
    id: str = Field(..., description="User ID")
    email: EmailStr = Field(..., description="User email")
    full_name: Optional[str] = Field(default=None, description="Full name")
    active_org_id: Optional[str] = Field(default=None, description="Active organization ID")
    memberships: List[Membership] = Field(default_factory=list, description="List of organization memberships")

# PUBLIC_INTERFACE
class SwitchOrgRequest(BaseModel):
    """Request to switch the active organization context."""
    org_id: str = Field(..., description="Organization ID to switch to")
