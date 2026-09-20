"""Resource output decoding and resource lookups.

Pure functions extracted from ``views.py`` so the GUI views and the MCP tool
layer share one implementation. No Django or request state.
"""

import json
from typing import Optional


def decode_resource_output(output):
    """Best-effort decode of a Resource ``output`` for display.

    ``get_deployment_resources`` already returns a decoded mapping, but the raw
    ``find_resources_by_tag/selector`` endpoints return ``Resource.serialize()``
    where mapping fields are base64-encoded JSON strings. Decode those so the UI
    shows the actual output rather than an opaque blob; leave anything else as-is.
    """
    if isinstance(output, str) and output:
        try:
            from base64 import b64decode

            return json.loads(b64decode(output).decode("latin-1"))
        except Exception:
            return output
    return output


def parse_tag_selector(tags: str) -> dict:
    """Parse a ``k=v,k=v`` tag-selector string into a dict (AND across pairs).

    Pairs without an ``=`` are ignored; keys and values are stripped.
    """
    selector = {}
    for pair in (tags or "").split(","):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            selector[k.strip()] = v.strip()
    return selector


def query_resources(
    client,
    environment: str,
    key: str = "",
    value: str = "",
    tags: str = "",
    page: int = 1,
    limit: int = 50,
):
    """Fetch an environment's Resources, optionally narrowed by tags.

    Three mutually exclusive modes, in the precedence the GUI uses:
    a ``tags`` AND-selector, a single ``key``/``value`` pair, or -- with neither --
    the full paginated list. Tag-filtered results are unpaginated, matching the
    backend endpoints.

    Returns ``(resources, pagination, error)``; ``pagination`` is ``None`` for the
    tag-filtered modes, ``error`` is ``None`` on success. Never raises.

    Callers are responsible for authorizing ``environment`` first -- this function
    performs no permission check.
    """
    from .pagination import build_pagination, offset_for_page

    if tags:
        response = client.find_resources_by_selector(
            parse_tag_selector(tags), environment=environment
        )
    elif key and value:
        response = client.find_resources_by_tag(key, value, environment=environment)
    else:
        offset = offset_for_page(page, limit)
        response = client.list_resources(
            limit=limit, offset=offset, environment=environment
        )
        if not response.success:
            return [], None, response.error
        data = response.data if isinstance(response.data, dict) else {}
        return (
            data.get("items", []) or [],
            build_pagination(data.get("total", 0), limit, offset, page),
            None,
        )

    if not response.success:
        return [], None, response.error
    return (response.data if isinstance(response.data, list) else []), None, None


def decode_resource_outputs(resources: list) -> list:
    """Decode the ``output`` field of each resource in place, returning the list."""
    for r in resources:
        if isinstance(r, dict) and "output" in r:
            r["output"] = decode_resource_output(r.get("output"))
    return resources


def resolve_resource_definition(
    client,
    resource_definition_name: str,
    namespace: Optional[str] = None,
    version: Optional[str] = None,
):
    """Find a ResourceDefinition by name (and optionally namespace/version).

    Returns the matching definition dict, or ``None`` when nothing matches.
    Used by the MCP provider-lookup tool so callers can pass the readable
    ``namespace/name`` form instead of an opaque identifier.
    """
    response = client.list_resource_definitions(resource_namespace=namespace)
    if not getattr(response, "success", False):
        return None
    items = response.data if isinstance(response.data, list) else []
    for rd in items:
        if rd.get("resource_definition_name") != resource_definition_name:
            continue
        if namespace and rd.get("resource_namespace") != namespace:
            continue
        if version and rd.get("version") != version:
            continue
        return rd
    return None


def filter_resource_definitions(items: list, query: str) -> list:
    """Case-insensitive substring filter over a ResourceDefinition listing.

    Matches name, namespace, or description. An empty ``query`` is a no-op.
    Extracted from the inline block in ``resource_definition_list`` so the GUI
    catalog page and the MCP catalog tool filter identically.
    """
    if not query:
        return items
    needle = query.lower()
    return [
        d
        for d in items
        if needle in (d.get("resource_definition_name") or "").lower()
        or needle in (d.get("resource_namespace") or "").lower()
        or needle in (d.get("description") or "").lower()
    ]
