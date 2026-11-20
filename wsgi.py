"""WSGI entry point for Gunicorn / hosted deployments."""
from app import app

application = app
