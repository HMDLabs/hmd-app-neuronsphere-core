"""Bridging between FastMCP's async request handling and Django's sync world.

Every tool is ``async def`` and immediately hands off here. Two things make that
mandatory rather than stylistic:

* ``DeploymentAPIClient`` uses a blocking ``httpx.Client`` with a 30s timeout,
  and every ORM call is sync. Running either on the event loop stalls all
  concurrent requests in the worker -- GUI page loads included.
* MCP requests never pass through Django's ``ASGIHandler``, so the
  ``request_started``/``request_finished`` signals that normally close database
  connections never fire. Without explicit ``close_old_connections()`` bracketing
  the threadpool hop, per-thread connections accumulate until Postgres refuses
  new ones.
"""
from django.db import close_old_connections
from fastmcp.server.dependencies import call_sync_fn_in_threadpool


def run_sync(fn, *args, **kwargs):
    """Call ``fn`` with database-connection hygiene. Runs on the current thread."""
    close_old_connections()
    try:
        return fn(*args, **kwargs)
    finally:
        close_old_connections()


async def run_in_django(fn, *args, **kwargs):
    """Await ``fn`` in a worker thread, bracketed by ``close_old_connections``.

    Uses FastMCP's own threadpool helper (``anyio.to_thread.run_sync``), which
    propagates contextvars -- so dependency lookups such as ``get_http_request``
    still resolve inside the thread.
    """
    return await call_sync_fn_in_threadpool(run_sync, fn, *args, **kwargs)
