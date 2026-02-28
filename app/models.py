"""
Pydantic models for request/response validation.
"""

from pydantic import BaseModel


class CheckRequest(BaseModel):
    """Request model for checking portals."""
    text: str


class StreamRequest(BaseModel):
    """Request model for stream operations."""
    url: str
    mac: str
    cmd: str


class VerifyRequest(BaseModel):
    """Request model for verification operations."""
    url: str
    mac: str