"""
Configuration settings for Bayaan API
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

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
API_VERSION = "1.0.0"

# -------------------------
# Server Configuration
# -------------------------

# These can be overridden via command line when running uvicorn
# e.g., uvicorn app.app:app --host 0.0.0.0 --port 8001 --reload
SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
