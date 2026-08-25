"""
Main FastAPI application initialization.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Response, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from app.limiter import limiter
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
import uvicorn

from app.config import settings
from app.routers import portals_router, streams_router

# Path to index.html relative to this file
INDEX_HTML = Path(__file__).parent.parent / "index.html"

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
                backupCount=settings.log_backup_count,
            )
            file_handler.setFormatter(log_formatter)
            logger.addHandler(file_handler)
            logger.info("File logging initialized successfully.")
    except (OSError, Exception) as e:
        # Fallback to console only if file logging is impossible
        print(
            f"Notice: File logging disabled (likely read-only environment or permission issue): {e}"
        )

# Initialize FastAPI app
app = FastAPI()

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


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


# =============================================================================
# Security Middleware
# =============================================================================


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers including CSP to all responses."""
    response = await call_next(request)

    # Content Security Policy
    # Based on the application's needs:
    # - Scripts: self + CDNs for HLS.js, mpegts.js
    # - Styles: self + CDN for Font Awesome + Google Fonts
    # - Images: self + data: URIs (base64 logos) + fallback CDN
    # - Connect: self + CDNs for HLS.js, mpegts.js, DOMPurify
    csp_directives = [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com",
        "style-src-elem 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com",
        "style-src-attr 'self' 'unsafe-inline'",
        "img-src 'self' data: blob: https://cdn-icons-png.flaticon.com https://*.flaticon.com",
        "media-src 'self' blob:",
        "connect-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com https://fonts.gstatic.com",
        "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "worker-src 'self' blob:",
    ]
    response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # X-Frame-Options to prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # Strict Transport Security (if using HTTPS)
    if not os.environ.get("DEV_MODE"):
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    return response


@app.get("/favicon.ico")
async def favicon():
    """Handle favicon requests."""
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serve the main HTML page."""
    return INDEX_HTML.read_text(encoding="utf-8")


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "ok", "version": settings.app_version}


if __name__ == "__main__":
    uvicorn.run(app, host=settings.server_host, port=settings.server_port)
