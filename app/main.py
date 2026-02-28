"""
Main FastAPI application initialization.
"""

import os
import gc
import logging
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import urllib3

from app.config import settings
from app.routers import portals_router, streams_router

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure Logging
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

# Stream handler for console
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

# Version tracking for Vercel deployments
print(f"Starting STBCheck App - Version: {settings.app_version}")

# File handler for debugging (only if not on Vercel and directory is writable)
if not os.environ.get("VERCEL"):
    try:
        # Check if the current directory is writable before attempting to create the log
        if os.access(os.getcwd(), os.W_OK):
            file_handler = RotatingFileHandler(
                "app.log",
                maxBytes=settings.log_file_max_bytes,
                backupCount=settings.log_backup_count
            )
            file_handler.setFormatter(log_formatter)
            logger.addHandler(file_handler)
            logger.info("File logging initialized successfully.")
    except (OSError, Exception) as e:
        # Fallback to console only if file logging is impossible
        print(f"Notice: File logging disabled (likely read-only environment or permission issue): {e}")

# Initialize FastAPI app
app = FastAPI()

# Add CORS Middleware
# SECURITY NOTE: For production, set CORS_ORIGINS env variable to specific domains
# Example: CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
# Default "*" allows all origins (development only)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(portals_router)
app.include_router(streams_router)


@app.get("/favicon.ico")
async def favicon():
    """Handle favicon requests."""
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serve the main HTML page."""
    with open("index.html", "r") as f:
        return f.read()


if __name__ == "__main__":
    uvicorn.run(app, host=settings.server_host, port=settings.server_port)