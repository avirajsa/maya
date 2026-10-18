"""Authentication and role-based authorization for Maya's API."""

import logging
import os
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

Role = Literal["owner", "trusted_user", "guest"]

bearer_scheme = HTTPBearer(auto_error=False)

AUTH_TIMEOUT = 8.0


class AuthenticatedUser(BaseModel):
    """Identity and authorization data verified by Maya's backend."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    email: str | None = None
    role: Role
    permissions: frozenset[str] = frozenset()


def _unauthorized(detail: str = "Invalid or expired access token.") -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _server_configuration() -> tuple[str, str, str]:
    """Return Supabase URL, publishable key, and backend secret key."""

    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    secret_key = os.getenv("SUPABASE_SECRET_KEY", "")

    if not url or not publishable_key or not secret_key:
        logger.error("Required Supabase authentication configuration is missing.")
        raise HTTPException(
            status_code=503,
            detail="Authentication is not configured on this server.",
        )

    return url, publishable_key, secret_key


async def require_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> AuthenticatedUser:
    """Validate a Supabase session and load the user's current role."""

    if credentials is None:
        raise _unauthorized("A Bearer access token is required.")

    url, publishable_key, secret_key = _server_configuration()
    access_token = credentials.credentials

    try:
        async with httpx.AsyncClient(timeout=AUTH_TIMEOUT) as client:
            # Ask Supabase Auth to validate the access token.
            auth_response = await client.get(
                f"{url}/auth/v1/user",
                headers={
                    "apikey": publishable_key,
                    "Authorization": f"Bearer {access_token}",
                },
            )

            if auth_response.status_code in (401, 403):
                raise _unauthorized()

            auth_response.raise_for_status()
            auth_payload = auth_response.json()

            user_id = UUID(auth_payload["id"])

            # Use the server-side secret key only on the backend.
            # Never send it to a browser, mobile app, or client.
            backend_headers = {
                "apikey": secret_key,
                "Authorization": f"Bearer {secret_key}",
            }

            profile_response = await client.get(
                f"{url}/rest/v1/profiles",
                params={
                    "select": "role",
                    "id": f"eq.{user_id}",
                },
                headers=backend_headers,
            )
            profile_response.raise_for_status()
            profiles = profile_response.json()

            if not profiles:
                raise HTTPException(
                    status_code=403,
                    detail="No profile is registered for this account.",
                )

            role_value = profiles[0].get("role")
            if role_value not in ("owner", "trusted_user", "guest"):
                logger.error("Invalid role configured for user %s", user_id)
                raise HTTPException(
                    status_code=403,
                    detail="The account has an invalid role configuration.",
                )

            permissions_response = await client.get(
                f"{url}/rest/v1/tool_permissions",
                params={
                    "select": "tool_name",
                    "user_id": f"eq.{user_id}",
                },
                headers=backend_headers,
            )
            permissions_response.raise_for_status()
            permission_rows = permissions_response.json()

            permissions = frozenset(
                row["tool_name"] for row in permission_rows if isinstance(row.get("tool_name"), str)
            )

            return AuthenticatedUser(
                id=user_id,
                email=auth_payload.get("email"),
                role=role_value,
                permissions=permissions,
            )

    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        logger.exception("Supabase authentication or profile lookup failed")
        raise HTTPException(
            status_code=503,
            detail="Could not validate the account with the authentication provider.",
        ) from None


def require_roles(
    *allowed_roles: Role,
):
    """Create a dependency that permits only the specified roles."""

    async def role_checker(
        user: Annotated[AuthenticatedUser, Depends(require_user)],
    ) -> AuthenticatedUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="Your role does not allow this action.",
            )
        return user

    return role_checker


def require_tool_permission(tool_name: str):
    """Create a dependency that checks permission for a named tool."""

    async def permission_checker(
        user: Annotated[AuthenticatedUser, Depends(require_user)],
    ) -> AuthenticatedUser:
        if not tool_name.strip():
            raise HTTPException(
                status_code=500,
                detail="Tool permission configuration is invalid.",
            )

        # The owner has administrative access to tools.
        if user.role == "owner":
            return user

        if tool_name not in user.permissions:
            raise HTTPException(
                status_code=403,
                detail=f"You do not have permission to use '{tool_name}'.",
            )

        return user

    return permission_checker
