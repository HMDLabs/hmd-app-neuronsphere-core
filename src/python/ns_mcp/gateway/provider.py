"""Gateway tools: one logical server, an ``environment`` argument, per-caller (NERD012).

``GatewayProvider`` is a FastMCP provider, so it is asked for tools on every
``tools/list`` and ``tools/call`` -- inside the request, with the caller's token
in context. That is the whole trick that NERD008 SPEC014's mount-once proxy could
not do: the tool list, and every forwarded call, are built for *this* caller.

For each logical server the caller can reach in at least one environment, each
upstream tool is exposed once as ``<server>__<tool>`` with an injected
``environment`` argument whose ``enum`` is exactly the environments the caller
may use there (``ns_environment`` if the upstream already has an ``environment``
argument of its own). A caller with one choice need not name it.

The filtered list is a convenience, not the control. ``GatewayTool.run``
re-authorizes the environment it is handed with the same
``assert_environment_access`` every native tool goes through, and audits the
call either way -- a client that ignores the ``enum`` and sends ``prod`` anyway
is refused before anything leaves the gateway.
"""
import asyncio
import copy
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.providers.base import Provider
from fastmcp.server.tasks.config import TaskConfig
from fastmcp.tools.base import Tool, ToolResult
from pydantic import PrivateAttr

from ..context import run_in_django
from ..principal import resolve_principal
from ..tooling import _request_metadata, load_user, write_audit
from .registry import Endpoint, GatewayRegistry, LogicalServer
from .upstream import (
    GATEWAY_HOP_HEADER,
    GatewayCallError,
    call_upstream,
    default_client_factory,
    list_upstream_tools,
    upstream_headers,
)

logger = logging.getLogger(__name__)

ENVIRONMENT_ARG = "environment"
FALLBACK_ENVIRONMENT_ARG = "ns_environment"
AUDIT_TRANSPORT = "mcp-gateway"


def _forwarded_by_a_gateway() -> bool:
    try:
        request = get_http_request()
    except Exception:  # no HTTP request (an in-process listing)
        return False
    return bool(request.headers.get(GATEWAY_HOP_HEADER))


def _version_key(version: str):
    """Sort key for an endpoint's declared version; unparseable sorts lowest."""
    return tuple(int(part) for part in re.findall(r"\d+", version or "")) or (-1,)


class GatewayTool(Tool):
    """One upstream tool, routed to the environment the caller names."""

    task_config: TaskConfig = TaskConfig(mode="forbidden")

    _provider: Any = PrivateAttr(default=None)
    _server_name: str = PrivateAttr(default="")
    _upstream_name: str = PrivateAttr(default="")
    _environment_arg: str = PrivateAttr(default=ENVIRONMENT_ARG)
    _environments: tuple = PrivateAttr(default=())

    async def run(self, arguments: Dict[str, Any], context=None) -> ToolResult:
        provider = self._provider
        arguments = dict(arguments or {})
        environment = arguments.pop(self._environment_arg, None)
        if not environment and len(self._environments) == 1:
            environment = self._environments[0]

        principal = resolve_principal()
        ip_address, user_agent = _request_metadata()
        correlation_id = str(uuid.uuid4())
        started = time.time()
        user = None
        success = True
        error_message = None
        try:
            user = await run_in_django(load_user, principal)
            endpoint = await run_in_django(
                provider.authorize,
                user,
                self._server_name,
                environment,
                self._environment_arg,
                self._environments,
            )
            headers = upstream_headers(endpoint, principal, request_id=correlation_id)
            result = await call_upstream(
                provider.client_factory,
                endpoint,
                self._upstream_name,
                arguments,
                headers,
            )
            if result.isError:
                success = False
                error_message = "upstream returned an error result"
            # Passed through as-is, error results included: the upstream's own
            # content is more useful to the caller than anything we would wrap it in.
            return ToolResult(
                content=result.content,
                structured_content=result.structuredContent,
                meta=result.meta,
                is_error=result.isError,
            )
        except ToolError as exc:
            success = False
            error_message = str(exc)
            raise
        except GatewayCallError as exc:
            success = False
            error_message = str(exc)
            raise ToolError(str(exc)) from None
        except Exception as exc:
            success = False
            error_message = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "MCP gateway call %s/%s in %s failed",
                self._server_name,
                self._upstream_name,
                environment,
            )
            raise ToolError(
                f"'{self._server_name}' in environment '{environment}' could not be "
                "reached."
            ) from None
        finally:
            await run_in_django(
                write_audit,
                user=user,
                principal=principal,
                action="mcp_tool_call",
                environment=environment,
                details={
                    "transport": AUDIT_TRANSPORT,
                    "server": self._server_name,
                    "tool": self._upstream_name,
                    "gateway_tool": self.name,
                    "environment": environment,
                    # Upstream argument values are arbitrary payloads (a SQL query,
                    # say); record which were sent, never what they contained.
                    "argument_names": sorted(arguments),
                },
                ip_address=ip_address,
                user_agent=user_agent,
                correlation_id=correlation_id,
                started=started,
                success=success,
                error_message=error_message,
            )


class GatewayProvider(Provider):
    """Serves every reachable upstream MCP server's tools, built per caller."""

    def __init__(
        self,
        registry: GatewayRegistry,
        client_factory=default_client_factory,
        separator: str = "__",
        tools_ttl: float = 60,
        clock=time.monotonic,
    ):
        super().__init__()
        self.registry = registry
        self.client_factory = client_factory
        self.separator = separator
        self._tools_ttl = tools_ttl
        self._clock = clock
        self._tools_cache: Dict[tuple, tuple] = {}

    # -- Provider interface ------------------------------------------------

    async def _list_tools(self) -> Sequence[Tool]:
        return await self._tools_for(None)

    async def _get_tool(self, name: str, version=None) -> Optional[Tool]:
        server_name, separator, _ = name.partition(self.separator)
        if not separator:
            return None
        for tool in await self._tools_for(server_name):
            if tool.name == name:
                return tool
        return None

    # -- authorization (worker thread) ---------------------------------------

    def reachable(self, principal, user, only: Optional[str] = None):
        """``[(LogicalServer, [Endpoint, ...])]`` the caller can use. Worker thread."""
        from deployments.services.authz import user_has_environment_access

        reachable = []
        for name, server in sorted(self.registry.snapshot().items()):
            if only is not None and name != only:
                continue
            endpoints = [
                endpoint
                for environment, endpoint in sorted(server.endpoints.items())
                if user_has_environment_access(
                    user, environment, endpoint.required_role
                )
                # An API key cannot be forwarded, so a passthrough server is
                # unusable to its holder -- better absent than failing on call.
                and not (endpoint.auth_mode == "passthrough" and principal.is_api_key)
            ]
            if endpoints:
                reachable.append((server, endpoints))
        return reachable

    def authorize(self, user, server_name, environment, environment_arg, offered):
        """The endpoint to call, or a ``ToolError``. Worker thread.

        Authoritative: it runs on every call regardless of what the caller was
        offered in ``tools/list``.
        """
        from deployments.services.authz import AccessDenied, assert_environment_access

        if not environment:
            raise ToolError(
                f"`{environment_arg}` is required: one of {', '.join(offered)}."
            )
        server = self.registry.snapshot().get(server_name)
        endpoint = server.endpoints.get(environment) if server else None
        role = endpoint.required_role if endpoint else "viewer"
        try:
            assert_environment_access(user, environment, role)
        except AccessDenied as exc:
            raise ToolError(str(exc)) from None
        if endpoint is None:
            raise ToolError(
                f"'{server_name}' is not deployed in environment '{environment}'."
            )
        return endpoint

    # -- tool construction ----------------------------------------------------

    async def _tools_for(self, only: Optional[str]) -> List[Tool]:
        if _forwarded_by_a_gateway():
            return []
        try:
            principal = resolve_principal()
        except ToolError:
            return []  # no authenticated caller (e.g. an in-process listing)

        def view():
            return self.reachable(principal, load_user(principal), only)

        try:
            reachable = await run_in_django(view)
        except ToolError:
            return []

        tools: List[Tool] = []
        for server, endpoints in reachable:
            tools.extend(await self._server_tools(server, endpoints, principal))
        return tools

    async def _server_tools(
        self, server: LogicalServer, endpoints: List[Endpoint], principal
    ) -> List[Tool]:
        listings = await asyncio.gather(
            *(self._upstream_tools(endpoint, principal) for endpoint in endpoints)
        )
        listed = [
            (ep, tools) for ep, tools in zip(endpoints, listings) if tools is not None
        ]
        # The newest deployment's schema wins where environments disagree;
        # environment name breaks ties so the choice is stable.
        listed.sort(key=lambda pair: pair[0].environment)
        listed.sort(key=lambda pair: _version_key(pair[0].version), reverse=True)

        schemas: Dict[str, Any] = {}
        environments: Dict[str, List[str]] = {}
        for endpoint, upstream_tools in listed:
            for upstream in upstream_tools:
                schemas.setdefault(upstream.name, upstream)
                environments.setdefault(upstream.name, []).append(endpoint.environment)

        return [
            self._gateway_tool(server, schemas[name], sorted(environments[name]))
            for name in sorted(schemas)
        ]

    async def _upstream_tools(self, endpoint: Endpoint, principal):
        """The upstream's tools, TTL-cached per (server, environment); None if down."""
        key = (endpoint.server_name, endpoint.environment, endpoint.url)
        cached = self._tools_cache.get(key)
        now = self._clock()
        if cached and now - cached[0] < self._tools_ttl:
            return cached[1]
        try:
            headers = upstream_headers(
                endpoint, principal, request_id=str(uuid.uuid4())
            )
            tools = await list_upstream_tools(self.client_factory, endpoint, headers)
        except Exception:
            logger.warning(
                "MCP gateway could not list tools for %s in %s (%s)",
                endpoint.server_name,
                endpoint.environment,
                endpoint.url,
                exc_info=True,
            )
            return None
        self._tools_cache[key] = (now, tools)
        return tools

    def _gateway_tool(self, server: LogicalServer, upstream, environments: List[str]):
        parameters = copy.deepcopy(upstream.inputSchema or {"type": "object"})
        properties = parameters.setdefault("properties", {})
        environment_arg = (
            FALLBACK_ENVIRONMENT_ARG
            if ENVIRONMENT_ARG in properties
            else ENVIRONMENT_ARG
        )
        choice = {
            "type": "string",
            "enum": environments,
            "description": (
                f"The NeuronSphere environment whose '{server.name}' deployment "
                "handles this call."
            ),
        }
        if len(environments) == 1:
            choice["default"] = environments[0]
        else:
            parameters["required"] = [*parameters.get("required", []), environment_arg]
        properties[environment_arg] = choice

        label = server.title or server.name
        description = (upstream.description or "").strip()
        tool = GatewayTool(
            name=f"{server.name}{self.separator}{upstream.name}",
            title=upstream.title,
            description=(
                f"[{label}] {description}\n\nRouted by the NeuronSphere MCP gateway to "
                f"the `{environment_arg}` you choose: {', '.join(environments)}."
            ).strip(),
            parameters=parameters,
            annotations=upstream.annotations,
            output_schema=upstream.outputSchema,
        )
        tool._provider = self
        tool._server_name = server.name
        tool._upstream_name = upstream.name
        tool._environment_arg = environment_arg
        tool._environments = tuple(environments)
        return tool
