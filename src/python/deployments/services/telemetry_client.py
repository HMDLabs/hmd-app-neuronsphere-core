"""Telemetry service client for environment health checks."""
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, Optional

import httpx
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

TELEMETRY_CACHE_TTL = 30  # seconds


@dataclass
class TelemetryStatus:
    """Health status for an environment from the telemetry service."""

    available: bool = False
    status: str = "unknown"  # healthy, degraded, unhealthy, unknown
    details: Dict = field(default_factory=dict)
    error: Optional[str] = None


class TelemetryClient:
    """Client for querying per-environment telemetry health endpoints."""

    def get_environment_status(self, environment: str) -> TelemetryStatus:
        """Get health status for a single environment.

        Args:
            environment: Environment name (e.g., 'dev', 'test', 'prod')

        Returns:
            TelemetryStatus with health info, defaults to 'unknown' if
            no URL is configured or the service is unreachable.
        """
        cache_key = f"telemetry:{environment}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        urls = getattr(settings, "TELEMETRY_SERVICE_URLS", {})
        url = urls.get(environment)

        if not url:
            status = TelemetryStatus(
                available=False,
                status="unknown",
                error="No telemetry URL configured",
            )
            cache.set(cache_key, status, TELEMETRY_CACHE_TTL)
            return status

        timeout = getattr(settings, "TELEMETRY_SERVICE_TIMEOUT", 5)

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(f"{url.rstrip('/')}/health")

                if response.status_code >= 400:
                    status = TelemetryStatus(
                        available=False,
                        status="unknown",
                        error=f"HTTP {response.status_code}",
                    )
                else:
                    data = response.json() if response.text else {}
                    status = TelemetryStatus(
                        available=True,
                        status=data.get("status", "unknown"),
                        details=data,
                    )

        except httpx.TimeoutException:
            logger.warning(f"Telemetry timeout for {environment}")
            status = TelemetryStatus(available=False, status="unknown", error="Timeout")
        except httpx.RequestError as e:
            logger.warning(f"Telemetry request error for {environment}: {e}")
            status = TelemetryStatus(available=False, status="unknown", error=str(e))

        cache.set(cache_key, status, TELEMETRY_CACHE_TTL)
        return status

    def get_all_environment_statuses(
        self, environments: list
    ) -> Dict[str, TelemetryStatus]:
        """Get health statuses for multiple environments, checked concurrently.

        Each per-environment check is an independent network call with its own
        timeout, so running them in a thread pool keeps the total wall time
        close to the slowest single check instead of the sum of all of them.

        Args:
            environments: List of environment names

        Returns:
            Dict mapping environment names to TelemetryStatus objects
        """
        if not environments:
            return {}

        with ThreadPoolExecutor(max_workers=len(environments)) as executor:
            statuses = executor.map(self.get_environment_status, environments)
            return dict(zip(environments, statuses))
