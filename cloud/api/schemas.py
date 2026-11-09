"""Validated request schemas for the cloud control plane."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict


class ProjectCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    brief: str = Field(min_length=1, max_length=12000)
    pipeline_id: str = Field(min_length=1, max_length=100)
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:5"] = "16:9"


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    options: dict[str, Any] = Field(default_factory=dict)
    acknowledged_cost: bool = False
