"""Test bootstrap.

Most of this suite is deliberately Django-free -- the service-layer helpers are
pure functions and are tested as such. The MCP tests are not: they exercise
model-backed authentication and per-environment authorization, which only mean
anything against the real models.

So Django is configured here (in-memory SQLite, no external services) and a test
database is created once per session. Tests that need neither are unaffected.
"""
import os

import django
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deployment_gui.settings.test")

# Must run at import time: pytest imports test modules during collection, and
# those import Django models at module scope.
django.setup()


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Create the in-memory schema once for the whole session."""
    from django.db import connection
    from django.test.utils import setup_test_environment, teardown_test_environment

    setup_test_environment()
    config = connection.creation.create_test_db(verbosity=0, keepdb=False)
    try:
        yield
    finally:
        connection.creation.destroy_test_db(config, verbosity=0)
        teardown_test_environment()


@pytest.fixture(autouse=True)
def _clean_database():
    """Reset table contents between tests.

    Deliberately a flush rather than a wrapping transaction: the MCP layer does
    its database work in a worker thread (see ``ns_mcp.context.run_in_django``),
    and an open transaction on the main thread would hold a write lock that the
    worker cannot get past -- SQLite reports "database table is locked". Flushing
    is slightly slower but keeps the threadpool hop testable, which is the part
    most worth covering.
    """
    from django.core.management import call_command

    yield
    call_command("flush", verbosity=0, interactive=False, allow_cascade=True)
