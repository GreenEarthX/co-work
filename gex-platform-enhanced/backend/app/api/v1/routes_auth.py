"""
JWT auth routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.core.auth import (
    decode_access_token,
    get_user_payload_from_token,
    issue_login_response,
    role_payload_from_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_at: str
    email: str
    role: dict
    user: dict


@router.get("/health")
async def auth_health():
    return {"status": "ok", "service": "jwt_auth"}


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    response = issue_login_response(request.email, request.password)
    if not response:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return LoginResponse(**response)


@router.get("/me")
async def me(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    try:
        decode_access_token(token)
        user = get_user_payload_from_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return {
        "email": user["email"],
        "role": role_payload_from_user(user),
        "user": user,
    }
