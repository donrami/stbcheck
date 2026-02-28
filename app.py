"""
STBcheck - Entry point for the STBcheck application.

This is a thin entry point that imports from the app package.
The main application logic is modularized in the app/ directory.

Usage:
    python app.py

Environment Variables:
    See app/config.py for all available configuration options.
"""

import uvicorn
from app import app
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(app, host=settings.server_host, port=settings.server_port)