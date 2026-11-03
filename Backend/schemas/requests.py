from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class AlertLocation(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    region_key: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class ClimateAlertInput(BaseModel):
    hazard_type: str = Field(min_length=1, max_length=80)
    severity: Literal["critical", "high", "moderate", "low"]
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    location: AlertLocation
    source: str = Field(min_length=1, max_length=120)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    measurements: dict[str, Any] = Field(default_factory=dict)


class SimulatorAlertInput(BaseModel):
    region_key: str = Field(min_length=1, max_length=80)
    tier: Literal["YELLOW", "ORANGE", "RED"]
    ward: str = Field(min_length=1, max_length=160)


class DispatchChatRequest(BaseModel):
    query: str
    region: str = "vizag"
    current_location: str = "Unknown"
