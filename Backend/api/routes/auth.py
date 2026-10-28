
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from services import json_store

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

USERS_COLLECTION = "users"
ROLES_COLLECTION = "roles"

JWT_SECRET = os.getenv("JWT_SECRET")
DEMO_LOGIN_PIN = os.getenv("DEMO_LOGIN_PIN")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

if not JWT_SECRET or not DEMO_LOGIN_PIN:
    raise RuntimeError("Set JWT_SECRET and DEMO_LOGIN_PIN in your environment")


class LoginRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)


def get_active_user_and_role(user_id: str):
    user = json_store.get_document(USERS_COLLECTION, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid login")

    if not user.get("isActive", False):
        raise HTTPException(status_code=403, detail="Account is inactive")

    role_id = user.get("roleId")
    if not role_id:
        raise HTTPException(status_code=403, detail="No role assigned")

    role = json_store.get_document(ROLES_COLLECTION, role_id)
    if role is None:
        raise HTTPException(status_code=403, detail="Assigned role not found")

    if not role.get("isActive", False):
        raise HTTPException(status_code=403, detail="Role is inactive")

    return user, role, role_id

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

def require_current_user(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer [REDACTED]")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    user, role, role_id = get_active_user_and_role(user_id)

    # Return current role data, not just the token's role claim.
    return {
        "id": user_id,
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "roleId": role_id,
        "roleName": role.get("name", ""),
        "roleLevel": role.get("level"),
    }


@router.get("/me")
def me(current_user: dict = Depends(require_current_user)):
    return {"user": current_user}
