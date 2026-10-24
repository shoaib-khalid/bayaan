"""
Configuration settings for Bayaan API
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load this file's own .env explicitly. A bare load_dotenv() searches the
# current working directory and upward, so running uvicorn from the repo root
# never found app/.env and every value below silently fell back to its default.
ENV_FILE = Path(__file__).with_name(".env")
load_dotenv(ENV_FILE)

# -------------------------
# Database Configuration
# -------------------------

DATABASE_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3212")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "root"),
    "database": os.getenv("DB_NAME", "bayaan"),
}

# -------------------------
# API Configuration
# -------------------------

API_TITLE = "Bayaan API"
API_DESCRIPTION = "API for Quran word retrieval and translation segment alignment"
API_VERSION = "1.1.0"

# -------------------------
# Server Configuration
# -------------------------

# These can be overridden via command line when running uvicorn
# e.g., uvicorn app.app:app --host 0.0.0.0 --port 8001 --reload
SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# -------------------------
# First administrator (optional)
# -------------------------

# Used once, on the first start against an empty `users` table: the account is
# created and these values are then ignored forever. Remove them afterwards.
# The same job can be done with `python scripts/manage_users.py create <name>
# --role admin`.
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
