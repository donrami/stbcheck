"""
Routers module for STBcheck.

Contains FastAPI routers for different API endpoint groups.
"""

from app.routers.portals import router as portals_router
from app.routers.streams import router as streams_router

__all__ = ["portals_router", "streams_router"]