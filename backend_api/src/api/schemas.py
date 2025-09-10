from __future__ import annotations

from typing import Optional, List, Literal
from pydantic import BaseModel, Field, EmailStr

# Auth and user/org models

class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=8, description="User password, will be hashed")
    full_name: Optional[str] = Field(None, description="Full name of the user")
    org_name: str = Field(..., description="Name of the organization to create")


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., description="User password")


class SwitchOrgRequest(BaseModel):
    org_id: str = Field(..., description="Organization ID to switch to")


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Type of token")
    user_id: str = Field(..., description="User ID")
    active_org_id: Optional[str] = Field(None, description="Active organization ID if set")


class Membership(BaseModel):
    org_id: str = Field(..., description="Organization ID")
    org_name: str = Field(..., description="Organization name")
    role: Literal["owner", "admin", "member", "viewer"] = Field(..., description="Role in the organization")


class UserProfile(BaseModel):
    id: str = Field(..., description="User ID")
    email: EmailStr = Field(..., description="User email")
    full_name: Optional[str] = Field(None, description="Full name")
    active_org_id: Optional[str] = Field(None, description="Active organization")
    memberships: List[Membership] = Field(default_factory=list, description="Memberships for this user")

# Organization models

class OrganizationCreate(BaseModel):
    name: str = Field(..., description="Organization name")


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, description="New organization name")


class Organization(BaseModel):
    id: str
    name: str
    owner_user_id: Optional[str] = None

# Project models

class ProjectCreate(BaseModel):
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Project description")


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, description="New project name")
    description: Optional[str] = Field(None, description="New description")


class Project(BaseModel):
    id: str
    org_id: str
    name: str
    description: Optional[str] = None
    created_by: str

# Task models

class TaskCreate(BaseModel):
    project_id: str = Field(..., description="Parent project ID")
    title: str = Field(..., description="Task title")
    description: Optional[str] = Field(None, description="Task description")
    assignee_id: Optional[str] = Field(None, description="User assigned to this task")
    status: Literal["todo", "in_progress", "done"] = Field(default="todo", description="Task status")
    priority: Literal["low", "medium", "high"] = Field(default="medium", description="Task priority")


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    status: Optional[Literal["todo", "in_progress", "done"]] = None
    priority: Optional[Literal["low", "medium", "high"]] = None


class Task(BaseModel):
    id: str
    project_id: str
    title: str
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    status: Literal["todo", "in_progress", "done"]
    priority: Literal["low", "medium", "high"]
    created_by: str

# Comment models

class CommentCreate(BaseModel):
    task_id: str = Field(..., description="Task ID")
    body: str = Field(..., description="Comment text")


class Comment(BaseModel):
    id: str
    task_id: str
    body: str
    created_by: str

# File upload

class FileUploadResponse(BaseModel):
    file_id: str = Field(..., description="Stored file ID")
    filename: str = Field(..., description="Original filename")
    content_type: Optional[str] = Field(None, description="Content type")

# Stripe

class StripeWebhookResult(BaseModel):
    received: bool = True
    event_type: Optional[str] = None

# OpenAI Assistant

class AssistantPrompt(BaseModel):
    task_context: Optional[str] = Field(None, description="Context of task/project")
    prompt: str = Field(..., description="User prompt for AI assistant")


class AssistantResponse(BaseModel):
    message: str = Field(..., description="Assistant response text")


# GitHub linkage

class GitHubLinkRepoRequest(BaseModel):
    org_id: str = Field(..., description="Organization ID")
    repo_full_name: str = Field(..., description="owner/repo")
    installation_id: Optional[int] = Field(None, description="GitHub App installation ID")


class GitHubIssueCreate(BaseModel):
    project_id: str = Field(..., description="Project ID")
    title: str = Field(..., description="Issue title")
    body: Optional[str] = Field(None, description="Issue body")
