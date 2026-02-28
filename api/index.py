"""
Vercel Serverless Function Entry Point

This file serves as the entry point for Vercel's Python serverless runtime.
It imports and exposes the FastAPI application from the app package.
"""

import sys
import os

# Add the parent directory to Python path so we can import the app package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the FastAPI app from the main module
from app.main import app

# Vercel expects the app to be exposed as 'app'
# The app object is already imported above
