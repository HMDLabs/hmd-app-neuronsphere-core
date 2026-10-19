"""Which MCP servers exist, and in which environments (NERD012).

A deployed MCP server announces itself the way every other NeuronSphere product
does: by publishing a Resource. Its definition is ``mcp.neuronsphere.io/mcp-server``
and its output carries ``server_name`` and ``url``. The environment is *not* in the
output -- it is wherever the producing repo instance is deployed -- which is what
lets one chart deployed to dev, test and prod surface here as one logical server
with three endpoints, with no per-environment configuration anywhere.

Resources carry no definition reference in their serialized form, so discovery
selects on a tag every producer sets (``DISCOVERY_TAG``) and asks once per
environment. ``MCP_GATEWAY_ENDPOINTS`` is the static escape hatch for servers that
are not deployed through NeuronSphere, and for local work and tests.
"""
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MCP_RESOURCE_NAMESPACE = "mcp.neuronsphere.io"
MCP_RESOURCE_DEFINITION = "mcp-server"

#: The tag every mcp-server Resource carries; discovery selects on it.
DISCOVERY_TAG = ("mcp.neuronsphere.io/kind", "mcp-server")

AUTH_MODES = frozenset({"service", "passthrough"})
#: Static configuration may also opt a server out of upstream auth, for local
#: fixtures. A discovered Resource cannot: a producer must not be able to unlock
#: its own server.
STATIC_AUTH_MODES = AUTH_MODES | {"none"}
ROLES = frozenset({"viewer", "deployer", "admin"})

#: Server names become tool-name prefixes, so they are held to a safe alphabet.
_SERVER_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
#: A credential reference names a file under MCP_GATEWAY_CREDENTIALS_DIR.
_CREDENTIAL_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class Endpoint:
    """One environment's deployment of a logical MCP server."""

    server_name: str
    environment: str
    url: str
    auth_mode: str = "service"
    credential_ref: Optional[str] = None
    required_role: str = "viewer"
    version: str = ""
    resource_name: str = ""


@dataclass
class LogicalServer:
    """An MCP server as callers see it: one name, any number of environments."""

    name: str
    title: str = ""
    description: str = ""
    endpoints: Dict[str, Endpoint] = field(default_factory=dict)


def _valid_endpoint(auth_modes=AUTH_MODES, **kwargs) -> Optional[Endpoint]:
    server_name = (kwargs.get("server_name") or "").strip()
    url = (kwargs.get("url") or "").strip()
    environment = (kwargs.get("environment") or "").strip()
    auth_mode = kwargs.get("auth_mode") or "service"
    required_role = kwargs.get("required_role") or "viewer"
    credential_ref = kwargs.get("credential_ref") or None

    problem = None
    if not _SERVER_NAME.match(server_name):
        problem = f"invalid server_name {server_name!r}"
    elif not url:
        problem = "no url"
    elif not environment:
        problem = "no environment"
    elif auth_mode not in auth_modes:
        problem = f"unknown auth_mode {auth_mode!r}"
    elif required_role not in ROLES:
        problem = f"unknown required_role {required_role!r}"
    elif credential_ref and not _CREDENTIAL_REF.match(credential_ref):
        problem = f"invalid credential_ref {credential_ref!r}"
    if problem:
        logger.warning(
            "Ignoring MCP endpoint (%s): %s",
            problem,
            kwargs.get("resource_name") or server_name or url,
        )
        return None

    return Endpoint(
        server_name=server_name,
        environment=environment,
        url=url,
        auth_mode=auth_mode,
        credential_ref=credential_ref,
        required_role=required_role,
        version=str(kwargs.get("version") or ""),
        resource_name=kwargs.get("resource_name") or "",
    )


def endpoint_from_output(output: dict, environment: str, resource_name: str):
    """An ``Endpoint`` from an mcp-server Resource's output, or ``None`` if invalid."""
    output = output or {}
    return _valid_endpoint(
        server_name=output.get("server_name"),
        url=output.get("url"),
        environment=environment,
        auth_mode=output.get("auth_mode"),
        credential_ref=output.get("credential_ref"),
        required_role=output.get("required_role"),
        version=output.get("version"),
        resource_name=resource_name,
    )


_STATIC_OPTION_KEYS = {
    "auth": "auth_mode",
    "cred": "credential_ref",
    "role": "required_role",
}


def parse_static_endpoints(raw: Optional[str]) -> List[Endpoint]:
    """Parse ``MCP_GATEWAY_ENDPOINTS``.

    Comma-separated ``server@environment=url[;auth=service|passthrough|none][;cred=ref]
    [;role=viewer|deployer|admin]``. Malformed entries are logged and skipped: one
    typo must not take the gateway down.
    """
    endpoints = []
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        head, _, url_and_options = entry.partition("=")
        if "@" not in head:
            logger.warning(
                "Ignoring MCP_GATEWAY_ENDPOINTS entry %r: expected server@environment=url",
                entry,
            )
            continue
        server_name, _, environment = head.partition("@")
        url, *options = url_and_options.split(";")
        fields = {}
        for option in options:
            key, _, value = option.partition("=")
            if key.strip() in _STATIC_OPTION_KEYS:
                fields[_STATIC_OPTION_KEYS[key.strip()]] = value.strip()
        endpoint = _valid_endpoint(
            server_name=server_name,
            environment=environment,
            url=url,
            resource_name="static",
            auth_modes=STATIC_AUTH_MODES,
            **fields,
        )
        if endpoint is not None:
            endpoints.append(endpoint)
    return endpoints


def _environment_names(client) -> List[str]:
    from deployments.services.environment_service import get_all_environments

    return get_all_environments(client)


def _discovered_endpoints(client) -> list:
    """``(Endpoint, output)`` pairs for every valid mcp-server Resource."""
    endpoints = []
    for environment in _environment_names(client):
        response = client.find_resources_by_selector(
            {DISCOVERY_TAG[0]: DISCOVERY_TAG[1]}, environment=environment
        )
        if not response.success:
            logger.warning(
                "MCP server discovery failed for environment %s: %s",
                environment,
                response.error,
            )
            continue
        for resource in response.data or []:
            endpoint = endpoint_from_output(
                resource.get("output"), environment, resource.get("resource_name", "")
            )
            if endpoint is not None:
                endpoints.append((endpoint, resource.get("output") or {}))
    return endpoints


def discover(client, static: Optional[str]) -> Dict[str, LogicalServer]:
    """Group every known endpoint into logical servers keyed by ``server_name``.

    ``client`` is a ``DeploymentAPIClient`` (or ``None`` for static-only). A
    discovered endpoint wins over a static one for the same server and
    environment: the deployment record is the source of truth.
    """
    servers: Dict[str, LogicalServer] = {}

    def add(endpoint: Endpoint, output: dict):
        server = servers.setdefault(
            endpoint.server_name, LogicalServer(endpoint.server_name)
        )
        server.endpoints[endpoint.environment] = endpoint
        server.title = server.title or output.get("title") or ""
        server.description = server.description or output.get("description") or ""

    for endpoint in parse_static_endpoints(static):
        add(endpoint, {})
    if client is not None:
        for endpoint, output in _discovered_endpoints(client):
            add(endpoint, output)
    return servers


class GatewayRegistry:
    """A TTL-cached snapshot of the logical servers.

    Refreshed lazily from whichever thread asks first after expiry. A failed
    refresh keeps the last good snapshot -- the deployment service being briefly
    unreachable should not make every gateway tool vanish mid-session.
    """

    def __init__(
        self,
        loader: Callable[[], Dict[str, LogicalServer]],
        ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._loader = loader
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._snapshot: Optional[Dict[str, LogicalServer]] = None
        self._loaded_at = 0.0

    def snapshot(self) -> Dict[str, LogicalServer]:
        with self._lock:
            now = self._clock()
            if self._snapshot is None or now - self._loaded_at >= self._ttl:
                try:
                    self._snapshot = self._loader()
                except Exception:
                    logger.exception("MCP gateway registry refresh failed")
                    if self._snapshot is None:
                        self._snapshot = {}
                self._loaded_at = now
            return self._snapshot


def default_registry() -> GatewayRegistry:
    """The registry the production server uses: discovery via the service account."""
    from django.conf import settings

    def load():
        from deployments.services.auth import get_api_client

        client = get_api_client() if settings.MCP_GATEWAY_DISCOVERY_ENABLED else None
        return discover(client, settings.MCP_GATEWAY_ENDPOINTS)

    return GatewayRegistry(loader=load, ttl=settings.MCP_GATEWAY_REGISTRY_TTL)
