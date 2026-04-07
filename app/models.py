"""
Pydantic models for request/response validation.
"""

from pydantic import BaseModel, Field


class CheckRequest(BaseModel):
    """Request model for checking portals."""

    text: str = Field(..., min_length=0, max_length=50000)


class StreamRequest(BaseModel):
    """Request model for stream operations."""

    url: str
    mac: str
    cmd: str


class VerifyRequest(BaseModel):
    """Request model for verification operations."""

    url: str
    mac: str
