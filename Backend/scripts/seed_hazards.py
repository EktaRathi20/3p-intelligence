"""Seed default hazard types into the local JSON database.

Run from the repository root::

    python Backend/scripts/seed_hazards.py

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


# --------------------------------------------------
# Default hazard types
# --------------------------------------------------

HAZARDS = [
    {
        "id": "flood",
        "name": "Flood",
        "code": "FLOOD",
        "description": "Flooding caused by heavy rainfall or overflowing water.",
        "active": True,
    },
    {
        "id": "cyclone",
        "name": "Cyclone",
        "code": "CYCLONE",
        "description": "Cyclonic storms and associated hazards.",
        "active": True,
    },
    {
        "id": "fire",
        "name": "Fire",
        "code": "FIRE",
        "description": "Urban, structural, and wildland fire incidents.",
        "active": True,
    },
    {
        "id": "heatwave",
        "name": "Heatwave",
        "code": "HEATWAVE",
        "description": "Extreme heat events.",
        "active": True,
    },
    {
        "id": "landslide",
        "name": "Landslide",
        "code": "LANDSLIDE",
        "description": "Slope failure and landslide incidents.",
        "active": True,
    },
    {
        "id": "earthquake",
        "name": "Earthquake",
        "code": "EARTHQUAKE",
        "description": "Seismic events and associated impacts.",
        "active": True,
    },
    {
        "id": "drought",
        "name": "Drought",
        "code": "DROUGHT",
        "description": "Prolonged rainfall deficiency and water scarcity.",
        "active": True,
    },
]


# --------------------------------------------------
# Seed the JSON database
# --------------------------------------------------

def seed_hazards():
    for hazard in HAZARDS:
        hazard_id = hazard["id"]
        document_data = {
            key: value
            for key, value in hazard.items()
            if key != "id"
        }

        document_data["updatedAt"] = json_store.utcnow_iso()

        json_store.set_document(
            "hazards",
            hazard_id,
            document_data,
            merge=True,
        )

    print(f"Successfully seeded {len(HAZARDS)} hazard types.")

    for hazard in HAZARDS:
        print(f"  - {hazard['id']}: {hazard['name']}")


if __name__ == "__main__":
    seed_hazards()
