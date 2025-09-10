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


# ---------- Projects Schemas ----------

# PUBLIC_INTERFACE
class ProjectCreate(BaseModel):
    """Request body to create a project within the active organization."""
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(default=None, description="Project description")

# PUBLIC_INTERFACE
class ProjectUpdate(BaseModel):
    """Request body to update a project."""
    name: Optional[str] = Field(default=None, description="New project name")
    description: Optional[str] = Field(default=None, description="New project description")

# PUBLIC_INTERFACE
class Project(BaseModel):
    """Project response model."""
    id: str = Field(..., description="Project ID")
    org_id: str = Field(..., description="Owning organization ID")
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(default=None, description="Project description")
    created_by: Optional[str] = Field(default=None, description="ID of user who created the project")
    created_at: str = Field(..., description="Creation timestamp (ISO)")

# PUBLIC_INTERFACE
class ProjectGithubLinkCreate(BaseModel):
    """Request body to link a GitHub repository to a project."""
    repo_full_name: str = Field(..., description="Full repository name in 'owner/repo' format")
    repo_id: Optional[int] = Field(default=None, description="GitHub repository numeric ID (optional)")
    repo_url: Optional[str] = Field(default=None, description="Repository HTML URL (optional)")
    default_branch: Optional[str] = Field(default=None, description="Default branch name (optional)")

# PUBLIC_INTERFACE
class ProjectGithubLink(BaseModel):
    """Response model for a project to GitHub repository link."""
    id: str = Field(..., description="Link ID")
    org_id: str = Field(..., description="Organization ID")
    project_id: str = Field(..., description="Project ID")
    repo_full_name: str = Field(..., description="Full repository name in 'owner/repo' format")
    repo_id: Optional[int] = Field(default=None, description="GitHub repository numeric ID")
    repo_url: Optional[str] = Field(default=None, description="Repository HTML URL")
    default_branch: Optional[str] = Field(default=None, description="Default branch name")
    created_at: str = Field(..., description="Creation timestamp (ISO)")
    updated_at: str = Field(..., description="Last update timestamp (ISO)")


# ---------- Tasks Schemas ----------

# PUBLIC_INTERFACE
class TaskCreate(BaseModel):
    """Request body to create a task within a project in the active organization."""
    project_id: str = Field(..., description="Project ID the task belongs to")
    title: str = Field(..., description="Task title")
    description: Optional[str] = Field(default=None, description="Task description")
    status: Optional[str] = Field(default="todo", description="Task status (todo, in_progress, done, etc.)")
    assignee_id: Optional[str] = Field(default=None, description="User ID assigned to the task")

# PUBLIC_INTERFACE
class TaskUpdate(BaseModel):
    """Request body to update a task."""
    title: Optional[str] = Field(default=None, description="New task title")
    description: Optional[str] = Field(default=None, description="New task description")
    status: Optional[str] = Field(default=None, description="New task status")
    assignee_id: Optional[str] = Field(default=None, description="New assignee user ID (null to unassign)")

# PUBLIC_INTERFACE
class Task(BaseModel):
    """Task response model."""
    id: str = Field(..., description="Task ID")
    org_id: str = Field(..., description="Owning organization ID")
    project_id: Optional[str] = Field(default=None, description="Project ID this task belongs to")
    title: str = Field(..., description="Task title")
    description: Optional[str] = Field(default=None, description="Task description")
    status: str = Field(..., description="Task status")
    assignee_id: Optional[str] = Field(default=None, description="Assigned user ID")
    created_by: Optional[str] = Field(default=None, description="ID of user who created the task")
    created_at: str = Field(..., description="Creation timestamp (ISO)")

# PUBLIC_INTERFACE
class TaskOrderPatch(BaseModel):
    """Single task ordering patch."""
    task_id: str = Field(..., description="Task ID to update")
    order_index: int = Field(..., description="New order index for the task")

# PUBLIC_INTERFACE
class TasksReorderRequest(BaseModel):
    """Bulk request body to reorder tasks in a project (and optional status lane)."""
    project_id: str = Field(..., description="Project whose tasks are being reordered")
    status: Optional[str] = Field(default=None, description="Optional status lane; if provided, update only tasks in this status")
    patches: List[TaskOrderPatch] = Field(..., description="Array of task_id and order_index pairs to set")

# ---------- Comments Schemas ----------

# PUBLIC_INTERFACE
class CommentCreate(BaseModel):
    """Request body to create a new comment for a task within the active organization."""
    task_id: str = Field(..., description="Task ID this comment belongs to")
    content: str = Field(..., description="Comment text content")

# PUBLIC_INTERFACE
class Comment(BaseModel):
    """Comment response model."""
    id: str = Field(..., description="Comment ID")
    org_id: str = Field(..., description="Owning organization ID")
    task_id: str = Field(..., description="Task ID this comment belongs to")
    author_id: Optional[str] = Field(default=None, description="User ID who wrote the comment")
    content: str = Field(..., description="Comment text content")
    created_at: str = Field(..., description="Creation timestamp (ISO)")

# ---------- Uploads/Attachments Schemas ----------

# PUBLIC_INTERFACE
class Attachment(BaseModel):
    """Attachment metadata returned after upload."""
    id: str = Field(..., description="Attachment ID")
    org_id: str = Field(..., description="Owning organization ID")
    project_id: Optional[str] = Field(default=None, description="Project ID this file is associated with")
    task_id: Optional[str] = Field(default=None, description="Task ID this file is associated with")
    uploader_id: Optional[str] = Field(default=None, description="User ID who uploaded the file")
    filename: str = Field(..., description="Original filename")
    content_type: Optional[str] = Field(default=None, description="MIME type of the uploaded file")
    size_bytes: Optional[int] = Field(default=None, description="Size of file in bytes")
    storage_path: str = Field(..., description="Local storage path where the file is saved")
    created_at: str = Field(..., description="Creation timestamp (ISO)")

# PUBLIC_INTERFACE
class UploadTarget(BaseModel):
    """Target association for an upload (one of project_id or task_id required)."""
    project_id: Optional[str] = Field(default=None, description="Project ID to associate the file with")
    task_id: Optional[str] = Field(default=None, description="Task ID to associate the file with")

# ---------- Billing/Stripe Schemas ----------

# PUBLIC_INTERFACE
class CheckoutSessionRequest(BaseModel):
    """Request to create a Stripe Checkout Session for a price/product."""
    price_id: str = Field(..., description="Stripe Price ID to subscribe/purchase")
    success_url: str = Field(..., description="Where to redirect on success (must be allowed by Stripe settings)")
    cancel_url: str = Field(..., description="Where to redirect if the user cancels")

# PUBLIC_INTERFACE
class CheckoutSessionResponse(BaseModel):
    """Response with checkout session URL."""
    url: str = Field(..., description="Hosted Checkout URL")

# PUBLIC_INTERFACE
class CustomerPortalRequest(BaseModel):
    """Request to create a Stripe Billing Portal link."""
    return_url: str = Field(..., description="URL to return to after managing billing")

# PUBLIC_INTERFACE
class CustomerPortalResponse(BaseModel):
    """Response with billing portal URL."""
    url: str = Field(..., description="Customer portal URL")
