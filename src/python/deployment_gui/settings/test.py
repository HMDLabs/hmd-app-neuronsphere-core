"""Settings for the unit test suite.

An in-memory SQLite database and a fixed secret so ``pytest`` needs no
environment setup. Imported by ``tests/conftest.py``; not used by any deployment.
"""
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-a-real-secret")

from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = ["localhost", "testserver"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Keep the suite hermetic: no Redis, no outbound calls, no password-hash cost.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
DEPLOYMENT_API_URL = "http://deployment-api.invalid"

# MCP_ENABLED / MCP_API_KEYS_ENABLED are deliberately NOT pinned here: they
# default to True in base.py, and leaving them env-driven keeps the
# MCP_ENABLED=false kill switch exercisable from the environment.
