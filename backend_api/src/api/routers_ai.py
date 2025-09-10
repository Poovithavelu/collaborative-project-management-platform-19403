from typing import Optional, List, AsyncGenerator

import os
from fastapi import APIRouter, Depends, HTTPException, status, Header, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .db import get_pool
from .security import decode_token

router = APIRouter(prefix="/ai", tags=["AI"])


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


class AICompletionRequest(BaseModel):
    """Request body for AI completion."""
    prompt: str = Field(..., description="User prompt/question for the AI assistant")
    project_id: Optional[str] = Field(default=None, description="Optional project context ID")
    task_id: Optional[str] = Field(default=None, description="Optional task context ID (must belong to project/org)")
    stream: bool = Field(default=False, description="If true, stream tokens as server-sent text/event-stream")
    model: Optional[str] = Field(default=None, description="Override default OpenAI model (e.g., gpt-4o-mini, gpt-4o)")

class AICompletionChunk(BaseModel):
    """Chunk of streamed completion text."""
    content: str = Field(..., description="Chunk of generated text")

class AICompletionResponse(BaseModel):
    """Non-streaming completion response."""
    content: str = Field(..., description="Full generated text response")
    model: str = Field(..., description="Model used for generation")
    project_id: Optional[str] = Field(default=None, description="Project context used")
    task_id: Optional[str] = Field(default=None, description="Task context used")


async def _fetch_context_text(org_id: str, project_id: Optional[str], task_id: Optional[str]) -> str:
    """Load relevant project/task context for the org and return a text block summarizing it."""
    pool = await get_pool()
    context_lines: List[str] = []
    async with pool.acquire() as conn:
        # Project context
        if project_id:
            proj = await conn.fetchrow(
                """
                select p.id, p.name, p.description, p.created_at
                from projects p
                where p.id = $1 and p.org_id = $2
                """,
                project_id, org_id,
            )
            if not proj:
                raise HTTPException(status_code=404, detail="Project not found in active organization")
            context_lines.append(f"Project: {proj['name']} (ID: {proj['id']})")
            if proj["description"]:
                context_lines.append(f"Project Description: {proj['description']}")
        # Task context (validate belongs)
        if task_id:
            task = await conn.fetchrow(
                """
                select t.id, t.project_id, t.title, t.description, t.status, t.created_at
                from tasks t
                where t.id = $1 and t.org_id = $2
                """,
                task_id, org_id,
            )
            if not task:
                raise HTTPException(status_code=404, detail="Task not found in active organization")
            # If project_id provided, ensure match
            if project_id and str(task["project_id"]) != project_id:
                raise HTTPException(status_code=400, detail="Task does not belong to the specified project")
            context_lines.append(f"Task: {task['title']} (ID: {task['id']})")
            context_lines.append(f"Task Status: {task['status']}")
            if task["description"]:
                context_lines.append(f"Task Description: {task['description']}")
        # If only project_id provided, add a brief list of latest tasks to augment context
        if project_id and not task_id:
            task_rows = await conn.fetch(
                """
                select id, title, status
                from tasks
                where org_id = $1 and project_id = $2
                order by created_at desc
                limit 10
                """,
                org_id, project_id
            )
            if task_rows:
                context_lines.append("Recent Project Tasks:")
                for r in task_rows:
                    context_lines.append(f"- [{r['status']}] {r['title']} (ID: {r['id']})")
    return "\n".join(context_lines)


def _get_openai_client():
    """Create OpenAI client using env var; raises HTTPException if not configured."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured")
    # Lazy import to keep optional dependency out of cold paths
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        # Suggest installing dependency if missing
        raise HTTPException(status_code=500, detail="OpenAI SDK not installed. Add 'openai' to requirements.txt") from e
    return OpenAI(api_key=api_key)


def _build_system_prompt() -> str:
    """System prompt guiding the assistant behavior."""
    return (
        "You are CollabTask AI, an assistant that helps teams plan and execute project tasks. "
        "Use the provided project/task context when drafting helpful, concise, and actionable responses. "
        "If information is missing, ask clarifying questions. Avoid hallucinations."
    )


async def _compose_messages(user_prompt: str, context_text: str) -> list[dict]:
    """Compose messages list for Chat Completions API."""
    messages: list[dict] = [
        {"role": "system", "content": _build_system_prompt()},
    ]
    if context_text.strip():
        messages.append({"role": "system", "content": f"Context:\n{context_text}"})
    messages.append({"role": "user", "content": user_prompt})
    return messages


async def _stream_chat(client, model: str, messages: list[dict]) -> AsyncGenerator[bytes, None]:
    """Stream assistant tokens as a simple text/event-stream of plain text chunks."""
    # Using responses.create with stream=True for modern OpenAI python client
    stream = client.chat.completions.create(model=model, messages=messages, stream=True)
    try:
        for event in stream:
            delta = event.choices[0].delta if hasattr(event.choices[0], "delta") else getattr(event.choices[0], "delta", None)
            text = ""
            if delta and getattr(delta, "content", None):
                text = delta.content
            elif hasattr(event.choices[0], "delta") and isinstance(event.choices[0].delta, dict):
                text = event.choices[0].delta.get("content") or ""
            if text:
                # Plain text streaming (not SSE framing), frontend can read incrementally
                yield text.encode("utf-8")
        # Ensure final newline
        yield b""
    except Exception as e:
        # Best-effort termination notice
        yield f"\n[stream-error] {str(e)}".encode("utf-8")


# PUBLIC_INTERFACE
@router.post(
    "/complete",
    response_model=AICompletionResponse,
    summary="AI completion with project/task context",
    description="Accepts a prompt and optional project/task IDs, pulls relevant context from the database within the caller's active organization, calls OpenAI, and returns the completion. Supports streaming responses when stream=true.",
    responses={
        200: {"description": "Completion generated"},
        400: {"description": "Bad request / invalid context"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Not found"},
        500: {"description": "Server error or OpenAI not configured"},
    },
)
async def ai_complete(
    data: AICompletionRequest = Body(...),
    payload: dict = Depends(_get_current_user_payload),
):
    """
    AI assistant endpoint.

    Parameters:
    - prompt: user message to complete
    - project_id: optional project context
    - task_id: optional task context (must belong to org and project if provided)
    - stream: if true, streams text chunks
    - model: optional OpenAI model override

    Returns:
    - Non-stream: { content, model, project_id, task_id }
    - Stream: text/plain streamed chunks
    """
    user_id = payload.get("user_id")
    active_org_id = payload.get("active_org_id")
    if not user_id or not active_org_id:
        raise HTTPException(status_code=400, detail="Missing user_id or active_org_id in token")

    # Build context text
    context_text = await _fetch_context_text(active_org_id, data.project_id, data.task_id)

    # Prepare OpenAI call
    client = _get_openai_client()
    model = data.model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    messages = await _compose_messages(data.prompt, context_text)

    # Streaming branch
    if data.stream:
        async def generator_wrapper():
            # wrap sync generator into async
            for chunk in _stream_chat(client, model, messages):
                # chunk is a generator of bytes from sync function; iterate it
                async for _ in ():  # no-op to keep async signature valid
                    pass
                # In practice, call the sync generator directly:
                break  # This placeholder will be replaced below

        # Because _stream_chat is sync generator (uses client stream), create a thin async wrapper
        async def async_stream():
            for b in _stream_chat(client, model, messages):
                yield b

        return StreamingResponse(async_stream(), media_type="text/plain")

    # Non-streaming: single-shot completion
    try:
        # Modern client
        resp = client.chat.completions.create(model=model, messages=messages)
        content = resp.choices[0].message.content if hasattr(resp.choices[0], "message") else resp.choices[0].get("message", {}).get("content")  # type: ignore
        if not content:
            content = ""
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {str(e)}") from e

    return AICompletionResponse(content=content, model=model, project_id=data.project_id, task_id=data.task_id)
