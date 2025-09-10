from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Body
import httpx

from .authz import require_org_role
from .schemas import AssistantPrompt, AssistantResponse

router = APIRouter(prefix="/assistant", tags=["AI Assistant"])

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


async def _openai_chat(prompt: str, context: Optional[str]) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OpenAI not configured")
    messages = []
    sys_prompt = "You are CollabTask AI assistant. Provide concise, actionable task suggestions."
    if context:
        sys_prompt += f"\nContext:\n{context}"
    messages.append({"role": "system", "content": sys_prompt})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": DEFAULT_MODEL, "messages": messages, "temperature": 0.2},
        )
        resp.raise_for_status()
        data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        raise HTTPException(status_code=502, detail="Invalid response from OpenAI")


# PUBLIC_INTERFACE
@router.post(
    "/respond",
    response_model=AssistantResponse,
    summary="AI assistant response",
    description="Generate assistant response based on prompt and optional task context. Requires viewer or higher.",
)
async def assistant_respond(
    body: AssistantPrompt = Body(...),
    _ctx=Depends(require_org_role("viewer")),
) -> AssistantResponse:
    """Generate AI assistant response."""
    text = await _openai_chat(body.prompt, body.task_context)
    return AssistantResponse(message=text)
