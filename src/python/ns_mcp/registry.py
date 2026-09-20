"""Capability registration -- the extension seam.

Adding a capability means writing a module with a ``register(mcp)`` function and
listing it in the matching setting: ``MCP_TOOL_MODULES``, ``MCP_RESOURCE_MODULES``
or ``MCP_PROMPT_MODULES``. Nothing in ``server.py`` changes.

The module lists are explicit rather than discovered by scanning the package: a
module that fails to import should break startup loudly, not vanish silently
from ``tools/list``.

``register(mcp)`` returns the names (or, for resources, the URIs) it registered.
FastMCP's own registries are async-only, so returning them is how the health
endpoint and the registry test can see what loaded without an event loop.
"""
import logging
from importlib import import_module

logger = logging.getLogger(__name__)


def _register_modules(mcp, module_paths, kind: str) -> dict:
    """Import each module and call its ``register(mcp)``.

    Returns ``{module_path: [name, ...]}``. Raises on a module that is missing
    ``register`` or that registers a name another module already took -- a
    silent collision would shadow one of the two.
    """
    registered: dict = {}
    seen: dict = {}
    for path in module_paths:
        module = import_module(path)
        register = getattr(module, "register", None)
        if not callable(register):
            raise TypeError(
                f"MCP {kind} module '{path}' has no callable register(mcp) function"
            )
        names = list(register(mcp) or [])
        for name in names:
            if name in seen:
                raise ValueError(
                    f"MCP {kind} '{name}' is registered by both '{seen[name]}' "
                    f"and '{path}'"
                )
            seen[name] = path
        registered[path] = names

    logger.info(
        "Registered %d MCP %s(s) from %d module(s)", len(seen), kind, len(registered)
    )
    return registered


def register_tool_modules(mcp, module_paths) -> dict:
    """Register the tool modules listed in ``settings.MCP_TOOL_MODULES``."""
    return _register_modules(mcp, module_paths, "tool")


def register_resource_modules(mcp, module_paths) -> dict:
    """Register the resource modules listed in ``settings.MCP_RESOURCE_MODULES``."""
    return _register_modules(mcp, module_paths, "resource")


def register_prompt_modules(mcp, module_paths) -> dict:
    """Register the prompt modules listed in ``settings.MCP_PROMPT_MODULES``."""
    return _register_modules(mcp, module_paths, "prompt")
