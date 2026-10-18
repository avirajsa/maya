
"""Chat endpoints for Maya."""

import logging
from typing import Annotated
from fastapi import Depends
from maya.api.routes.auth import AuthenticatedUser, require_user
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from maya.agent.agent import get_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    session_id: UUID
    voice_mode: bool = False


class ChatResponse(BaseModel):
    session_id: UUID
    response: str


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest,
               user: Annotated[AuthenticatedUser, Depends(require_user)],
               ) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(
            status_code=422,
            detail="Message cannot be empty.",
        )

    try:
        agent = get_agent()
        response = await agent.chat(
            user_input=message,
            # A client-supplied session UUID is not globally unique.
            # Prefix it with the authenticated account ID.
            session_id=f"api:{user.id}:{request.session_id}",
            voice_mode=request.voice_mode,
            user_context={
                "id": str(user.id),
                "role":user.role,
                "permissions":sorted(user.permissions),
                },
        )
    except Exception:
        logger.exception("Maya API chat request failed")
        raise HTTPException(
            status_code=500,
            detail="Maya could not process the request.",
        ) from None

    return ChatResponse(
        session_id=request.session_id,
        response=response,
    )

