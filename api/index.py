"""
Vercel serverless entry point.
Vercel Python runtime looks for an `app` variable (WSGI/ASGI) in this file.
"""
import os
import sys

# Ensure the project root is on sys.path so `src` package is importable
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.web import create_app

app = create_app()
