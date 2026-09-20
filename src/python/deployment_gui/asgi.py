"""ASGI entry point: the Django app with the MCP server mounted beside it.

Routing is a Starlette router rather than a Django URL pattern because the MCP
server is a complete ASGI application (Streamable HTTP, its own auth), not a
view. Django keeps serving everything else unchanged.

    /mcp   -> FastMCP  (Streamable HTTP, bearer auth)
    /*     -> Django   (all existing views, session auth)

Consequences worth knowing:

* Django's ``SecurityMiddleware``, ``CsrfViewMiddleware``, and ``ALLOWED_HOSTS``
  do NOT apply to /mcp -- it is a sibling mount, not a Django view. FastMCP does
  its own Host/Origin checking (``MCP_ALLOWED_HOSTS`` / ``MCP_ALLOWED_ORIGINS``),
  and bearer auth makes CSRF inapplicable because no cookie is ever consulted.
* The MCP app's lifespan MUST be passed to the router. Without it FastMCP's
  session manager never initialises and every request fails.
* ``/health/`` stays on the Django side, so the k8s probes, the Dockerfile
  HEALTHCHECK, and the ALB annotation are all untouched.
* The auth provider's ``/.well-known`` routes are spliced in at the ROOT, above the
  Django catch-all. RFC 9728 puts the protected-resource document at
  ``https://host/.well-known/oauth-protected-resource/mcp`` -- beside the /mcp mount,
  not inside it -- and a route registered by the FastMCP app alone would only ever be
  reachable under /mcp. Without this an MCP client cannot discover where to get a token.

Setting ``MCP_ENABLED=false`` serves the bare Django app -- the kill switch, and
the other half of the rollback lever alongside ``GUNICORN_WORKER_CLASS=sync``
(``deployment_gui/wsgi.py`` is deliberately kept and unchanged).
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deployment_gui.settings.production")

from django.core.asgi import get_asgi_application  # noqa: E402

# get_asgi_application() runs django.setup(). It must happen before anything
# under ns_mcp is imported, because those modules import Django models.
django_application = get_asgi_application()

from django.conf import settings  # noqa: E402

if settings.MCP_ENABLED:
    from starlette.applications import Starlette
    from starlette.routing import Mount

    from ns_mcp.server import build_mcp_app, get_well_known_routes

    mcp_application = build_mcp_app()

    application = Starlette(
        routes=[
            Mount(settings.MCP_MOUNT_PATH, app=mcp_application),
            # Empty unless an Okta provider is configured; a bare verifier advertises
            # nothing. Must precede the Django mount, which matches everything.
            *get_well_known_routes(),
            Mount("/", app=django_application),
        ],
        lifespan=mcp_application.lifespan,
    )
else:
    application = django_application
