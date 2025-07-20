#!/usr/bin/env python3
"""
WSGI entry point for Tasmota Updater application.

This file provides a proper entry point for WSGI servers like Gunicorn.
"""

# Import the create_app function directly
from server import create_app

# Create the Flask application instance
app = create_app()

if __name__ == "__main__":
    app.run()
