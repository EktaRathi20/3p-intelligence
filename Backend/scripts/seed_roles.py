"""Seed demo roles and users into the local JSON database.

Run from the repository root::

    python Backend/scripts/seed_roles.py

Writes merge per record, so reruns are safe and unrelated fields on
existing records are preserved.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import json_store  # noqa: E402

ROLES = [
    {
        "id": "role_1",
        "name": "Disaster Assessment Officer",
        "level": 1,
        "description": "Reviews disaster alerts and approves or rejects proposed disasters.",
        "isActive": True,
    },
    {
        "id": "role_2",
        "name": "Operations Planner",
        "level": 2,
        "description": "Reviews response plans, manages tasks, and assigns work to field teams.",
        "isActive": True,
    },
    {
        "id": "role_3",
        "name": "Field Operations Officer",
        "level": 3,
        "description": "Executes assigned disaster response tasks and reports field progress.",
        "isActive": True,
    },
    {
        "id": "role_4",
        "name": "Insurance Recovery Officer",
        "level": 4,
        "description": "Reviews damage assessments, insurance cases, and recovery recommendations.",
        "isActive": True,
    },
    {
        "id": "role_5",
        "name": "Rescue Relief Officer",
        "level": 5,
        "description": "Coordinates rescue operations and uses AI support for routes and shelters.",
        "isActive": True,
    },
]

# Sample users — demo data only.
USERS = [
    {
        "id": "user_1",
        "name": "Aarav Sharma",
        "email": "aarav.demo@example.com",
        "roleId": "role_1",
        "isActive": True,
    },
    {
        "id": "user_2",
        "name": "Priya Verma",
        "email": "priya.demo@example.com",
        "roleId": "role_2",
        "isActive": True,
    },
    {
        "id": "user_3",
        "name": "Rahul Singh",
        "email": "rahul.demo@example.com",
        "roleId": "role_3",
        "isActive": True,
    },
    {
        "id": "user_4",
        "name": "Ananya Patel",
        "email": "ananya.demo@example.com",
        "roleId": "role_4",
        "isActive": True,
    },
    {
        "id": "user_5",
        "name": "Vikram Joshi",
        "email": "vikram.demo@example.com",
        "roleId": "role_5",
        "isActive": True,
    },
]


def seed_roles_and_users() -> tuple[int, int]:
    """Upsert seed roles and users; return (roles, users) counts."""
    for role in ROLES:
        record_id = role["id"]
        json_store.set_document(
            "roles",
            record_id,
            {key: value for key, value in role.items() if key != "id"},
            merge=True,
        )
    for user in USERS:
        record_id = user["id"]
        json_store.set_document(
            "users",
            record_id,
            {key: value for key, value in user.items() if key != "id"},
            merge=True,
        )
    return len(ROLES), len(USERS)


if __name__ == "__main__":
    role_count, user_count = seed_roles_and_users()
    print(f"Successfully seeded {role_count} roles and {user_count} users!")
