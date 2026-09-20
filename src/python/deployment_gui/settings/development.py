"""Development settings for NeuronSphere Deployment GUI."""
import os

from .base import *  # noqa: F401, F403

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Use PostgreSQL if DB_HOST is set (Docker), otherwise SQLite
if os.environ.get("DB_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "deployment_gui"),
            "USER": os.environ.get("DB_USER", "deployment_gui"),
            "PASSWORD": os.environ.get("DB_PASSWORD", "deployment_gui"),
            "HOST": os.environ.get("DB_HOST", "db"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
else:
    # Use SQLite for local development without Docker
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        }
    }

# Allow username/password login for development
SOCIALACCOUNT_ONLY = False

# Mock deployment API for development
DEPLOYMENT_API_URL = os.environ.get(
    "DEPLOYMENT_API_URL", "http://localhost:8080"
)  # noqa: F405

# CSRF settings for local development
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Cache — Redis when REDIS_HOST is set (e.g. local Docker), otherwise in-memory.
CACHES = {
    "default": redis_cache_config()
    or {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}
