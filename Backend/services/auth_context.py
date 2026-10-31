"""Shared authentication helpers for JSON-backed API routes.

Extracted from ``api/routes/auth.py`` so task and notification routes can
reuse the same Bearer-token verification without importing the ``api.routes``
package (which would pull every router, including ones with optional
third-party dependencies, and break isolated route tests).
"""

from __future__ import annotations

import os

import jwt
from fastapi import Header, HTTPException

from services import json_store

USERS_COLLECTION = "users"
ROLES_COLLECTION = "roles"

JWT_SECRET = os.getenv("JWT_SECRET")

if not JWT_SECRET:
    raise RuntimeError("Set JWT_SECRET in your environment")


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


def require_current_user(authorization: str = Header(default="")) -> dict:
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

    return {
        "id": user_id,
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "roleId": role_id,
        "roleName": role.get("name", ""),
        "roleLevel": role.get("level"),
    }


def is_role_2(user: dict) -> bool:
    """True when the authenticated user is an Operations Planner (Role 2)."""
    if user.get("roleLevel") == 2:
        return True
    if str(user.get("roleId") or "").strip().lower() == "role_2":
        return True
    return "operations planner" in str(user.get("roleName") or "").lower()


def is_role_3(user: dict) -> bool:
    """True when the authenticated user is a Field Operations Officer."""
    if user.get("roleLevel") == 3:
        return True
    if str(user.get("roleId") or "").strip().lower() == "role_3":
        return True
    return "field operations officer" in str(user.get("roleName") or "").lower()
