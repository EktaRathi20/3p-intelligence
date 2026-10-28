"""Role and user lookup endpoints backed by the local JSON database."""

from typing import Any

from fastapi import APIRouter, HTTPException

from services import json_store

USERS_COLLECTION = "users"
ROLES_COLLECTION = "roles"

router = APIRouter()
# ---------------- ROLES APIs ----------------

@router.get("/api/roles")
def get_roles() -> dict[str, Any]:
    """Fetch all role definitions."""
    try:
        roles = json_store.list_documents(ROLES_COLLECTION)
        roles.sort(key=lambda role: role.get("level", 999))

        return {
            "success": True,
            "count": len(roles),
            "roles": roles,
        }
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to fetch roles.",
        )


@router.get("/api/roles/{role_id}")
def get_role(role_id: str) -> dict[str, Any]:
    """Fetch one role by document ID."""
    try:
        role = json_store.get_document(ROLES_COLLECTION, role_id)

        if role is None:
            raise HTTPException(status_code=404, detail="Role not found")

        return {
            "success": True,
            "role": role,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to fetch role.",
        )


# ---------------- USERS APIs ----------------

@router.get("/api/users")
def get_users() -> dict[str, Any]:
    """Fetch users. Protect this endpoint before production deployment."""
    try:
        users = json_store.list_documents(USERS_COLLECTION)

        return {
            "success": True,
            "count": len(users),
            "users": users,
        }
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to fetch users.",
        )


@router.get("/api/users/{user_id}")
def get_user(user_id: str) -> dict[str, Any]:
    """Fetch one user by document ID."""
    try:
        user = json_store.get_document(USERS_COLLECTION, user_id)

        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "success": True,
            "user": user,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to fetch user.",
        )
