"""
Phusion Passenger WSGI entry point for cPanel hosting.

cPanel's "Setup Python App" uses Passenger, which looks for a file named
passenger_wsgi.py that exposes a WSGI callable called `application`.
"""
import sys
import os

# Ensure the app directory is on the path
sys.path.insert(0, os.path.dirname(__file__))

# Import Flask app and expose it as `application` (required by Passenger)
from app import app, init_db

# Initialise database (creates tables + seeds 14 users on first boot)
init_db()

application = app
