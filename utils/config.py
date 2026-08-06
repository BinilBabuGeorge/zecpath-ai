"""
Project-wide configuration constants.
Keep environment-specific values (API keys, DB URLs) out of source control —
load them from environment variables here, never hard-code secrets.
"""

import os

# --- Environment ---
ENV = os.getenv("ZECPATH_ENV", "development")  # development | staging | production
DEBUG = ENV == "development"

# --- Service identity (used in logs & model-version tagging, see Day 2 I/O spec) ---
SERVICE_NAME = os.getenv("ZECPATH_SERVICE_NAME", "unnamed-service")
MODEL_VERSION = os.getenv("ZECPATH_MODEL_VERSION", "v0.1.0")

# --- Storage (placeholders — replace with real connection strings) ---
DATABASE_URL = os.getenv("ZECPATH_DATABASE_URL", "sqlite:///data/zecpath.db")
MEDIA_STORAGE_PATH = os.getenv("ZECPATH_MEDIA_PATH", "data/media")

# --- Messaging (placeholders for Queue / Webhook config, see Day 2 architecture) ---
QUEUE_URL = os.getenv("ZECPATH_QUEUE_URL", "")
WEBHOOK_CALLBACK_URL = os.getenv("ZECPATH_WEBHOOK_URL", "")
