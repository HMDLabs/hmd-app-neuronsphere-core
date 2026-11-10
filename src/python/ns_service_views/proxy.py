"""Forwarding a partial request to the service that serves it (NERD007 SPEC003).

The response is passed back as-is, apart from two host rules: it may be no
larger than ``MAX_RESPONSE_BYTES``, and any ``<script>``, ``<link>`` or
``<style>`` a service sends is removed (SPEC006). The host shell alone loads
assets; a partial runs in the GUI's origin.
"""

import re
from typing import Dict, Optional

import httpx

MAX_RESPONSE_BYTES = 1024 * 1024
TIMEOUT_SECONDS = 15

_PAIRED_ASSET = re.compile(r"<\s*(script|style)\b[^>]*>.*?<\s*/\s*\1\s*>", re.I | re.S)
_LONE_ASSET = re.compile(r"<\s*(script|style|link)\b[^>]*/?>", re.I)


def strip_asset_tags(html: str) -> str:
    return _LONE_ASSET.sub("", _PAIRED_ASSET.sub("", html))


def transport() -> Optional[httpx.BaseTransport]:
    """The HTTP transport for upstream calls; tests replace it."""
    return None


class UpstreamError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def forward(
    method: str,
    url: str,
    *,
    params: Dict,
    data: Optional[Dict],
    token: Optional[str],
) -> httpx.Response:
    headers = {"Accept": "text/html", "HX-Request": "true"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(transport=transport(), timeout=TIMEOUT_SECONDS) as client:
            response = client.request(
                method, url, params=params, data=data, headers=headers
            )
    except httpx.HTTPError as e:
        raise UpstreamError(f"The service is unreachable ({type(e).__name__}).") from e
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise UpstreamError(
            f"The view's response is too large ({len(response.content)} bytes; "
            f"the limit is {MAX_RESPONSE_BYTES})."
        )
    return response
