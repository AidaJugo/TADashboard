"""Pydantic models for the comments API (FR-COMMENT-1..4, M6)."""

from __future__ import annotations

import uuid  # noqa: TC003 — Pydantic resolves at runtime
from datetime import datetime  # noqa: TC003 — Pydantic resolves at runtime

from pydantic import BaseModel, ConfigDict, Field


class CommentCreateRequest(BaseModel):
    """Create a comment keyed by (position, seniority, hub, salary_eur).

    The UNIQUE constraint ``uq_comment_hire_key`` in the DB enforces one
    comment per hire key.  A duplicate returns 409.
    """

    position: str = Field(max_length=200)
    seniority: str = Field(max_length=100)
    hub: str = Field(max_length=100)
    salary_eur: int
    text: str = Field(max_length=500, description="Hire note, max 500 characters.")


class CommentUpdateRequest(BaseModel):
    text: str = Field(max_length=500, description="Hire note, max 500 characters.")


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: str
    seniority: str
    hub: str
    salary_eur: int
    text: str
    created_at: datetime
    updated_at: datetime
