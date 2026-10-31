
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from services.auth_context import (
    get_active_user_and_role,
    require_current_user,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

JWT_SECRET = os.getenv("JWT_SECRET")
DEMO_LOGIN_PIN = os.getenv("DEMO_LOGIN_PIN")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

if not JWT_SECRET or not DEMO_LOGIN_PIN:
    raise RuntimeError("Set JWT_SECRET and DEMO_LOGIN_PIN in your environment")

__all__ = ["router", "get_active_user_and_role", "require_current_user"]


class LoginRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)

@router.post("/login")
def login(payload: LoginRequest):
    # Verify the selected user and their active role in the local database.
    user, role, role_id = get_active_user_and_role(payload.user_id)

    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": payload.user_id,
            "role_id": role_id,
            "iat": now,
            "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
        },
        JWT_SECRET,
        algorithm="HS256",
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": payload.user_id,
            "name": user.get("name", ""),
            "email": user.get("email", ""),
            "roleId": role_id,
            "roleName": role.get("name", ""),
            "roleLevel": role.get("level", 0),
        },
    }

@router.get("/me")
def me(current_user: dict = Depends(require_current_user)):
    return {"user": current_user}
