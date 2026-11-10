"""Which services contribute views, per environment (NERD007 SPEC004).

A service announces its views the way an MCP server announces itself (NERD012):
by publishing a Resource, here ``ui.neuronsphere.io/view-set``, tagged so it can
be selected without a definition reference. The environment is not in the
output; it is wherever the producing instance is deployed, so one selector
query per environment is the whole inventory.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from django.core.cache import cache

from deployments.services.resource_query import decode_resource_output

logger = logging.getLogger(__name__)

#: The tag every view-set Resource carries; discovery selects on it.
VIEW_SET_TAG = ("ui.neuronsphere.io/kind", "view-set")
VIEW_PATH_PREFIX = "/views/"
CACHE_SECONDS = 300


def _cache_key(environment: str) -> str:
    return f"ns_service_views:inventory:{environment}"


@dataclass
class ServiceViews:
    """One deployed service's published views."""

    service: str
    instance: str
    base_url: str
    views: List[Dict]
    group_permissions: Dict[str, List[str]] = field(default_factory=dict)
    version: str = ""

    @classmethod
    def from_output(cls, output) -> Optional["ServiceViews"]:
        """Parse a view-set output, or None when it is unusable. Individual
        malformed views are dropped; the rest of the service still shows."""
        if not isinstance(output, dict):
            return None
        if not all(output.get(k) for k in ("service", "instance", "base_url")):
            return None
        views = []
        for view in output.get("views") or []:
            if not isinstance(view, dict) or not all(
                view.get(k) for k in ("id", "title", "path")
            ):
                logger.warning(
                    "Ignoring malformed view in %s: %r", output["instance"], view
                )
                continue
            if not view["path"].startswith(VIEW_PATH_PREFIX):
                logger.warning(
                    "Ignoring view %s of %s: path %r is outside %s",
                    view["id"],
                    output["instance"],
                    view["path"],
                    VIEW_PATH_PREFIX,
                )
                continue
            views.append(view)
        views.sort(key=lambda v: (v.get("group", ""), v.get("order", 0), v["title"]))
        group_permissions = output.get("group_permissions")
        return cls(
            service=output["service"],
            instance=output["instance"],
            base_url=output["base_url"].rstrip("/"),
            views=views,
            group_permissions=group_permissions
            if isinstance(group_permissions, dict)
            else {},
            version=output.get("version", ""),
        )

    def view_at(self, path: str) -> Optional[Dict]:
        return next((v for v in self.views if v["path"] == path), None)


def discover(client, environment: str) -> List[ServiceViews]:
    """The environment's view-sets. A failed query is an empty inventory, never
    an error page: views are secondary to everything else the GUI shows."""
    response = client.find_resources_by_selector(
        {VIEW_SET_TAG[0]: VIEW_SET_TAG[1]}, environment=environment
    )
    if not response.success:
        logger.warning("View discovery failed for %s: %s", environment, response.error)
        return []
    services = []
    for resource in response.data or []:
        svc = ServiceViews.from_output(decode_resource_output(resource.get("output")))
        if svc is None:
            logger.warning(
                "Ignoring unusable view-set %s", resource.get("resource_name")
            )
            continue
        services.append(svc)
    services.sort(key=lambda s: s.instance)
    return services


def inventory(client, environment: str) -> List[ServiceViews]:
    """``discover``, cached per environment for ``CACHE_SECONDS``."""
    key = _cache_key(environment)
    cached = cache.get(key)
    if cached is not None:
        return cached
    services = discover(client, environment)
    cache.set(key, services, CACHE_SECONDS)
    return services


def invalidate(environment: str) -> None:
    """Drop the environment's cached inventory, e.g. after a deploy there."""
    cache.delete(_cache_key(environment))


def find_service(client, environment: str, instance: str) -> Optional[ServiceViews]:
    return next(
        (s for s in inventory(client, environment) if s.instance == instance), None
    )
