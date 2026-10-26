"""The service token is cached for its real lifetime, never longer.

The cache used to hold every token for a fixed 55 minutes. An IdP whose tokens
live less than that left an expired token in the cache, and every call through
the service account (including the MCP gateway's discovery) was refused by the
authorizer until the entry ran out.
"""

from unittest import mock

import pytest

from deployments.services.auth import AuthTokenManager


@pytest.fixture
def manager():
    m = AuthTokenManager()
    m.okta_issuer, m.client_id, m.client_secret = "https://idp.test", "id", "secret"
    return m


def _response(expires_in):
    body = {"access_token": "tok"}
    if expires_in is not None:
        body["expires_in"] = expires_in
    return mock.Mock(status_code=200, json=mock.Mock(return_value=body))


def _cached_timeout(manager, expires_in):
    with (
        mock.patch("deployments.services.auth.cache") as cache,
        mock.patch("deployments.services.auth.httpx.post") as post,
    ):
        cache.get.return_value = None
        post.return_value = _response(expires_in)
        assert manager.get_token() == "tok"
        return cache.set.call_args.kwargs["timeout"]


def test_short_lived_token_is_cached_for_less_than_its_lifetime(manager):
    timeout = _cached_timeout(manager, 1800)
    assert timeout == 1800 - AuthTokenManager.TOKEN_BUFFER_SECONDS


def test_cache_never_outlasts_the_old_one_hour_cap(manager):
    timeout = _cached_timeout(manager, 86400)
    assert timeout == 3600 - AuthTokenManager.TOKEN_BUFFER_SECONDS


def test_token_shorter_than_the_buffer_is_still_cached_inside_its_life(manager):
    timeout = _cached_timeout(manager, 120)
    assert 0 < timeout < 120


def test_missing_expires_in_keeps_the_conservative_default(manager):
    timeout = _cached_timeout(manager, None)
    assert 0 < timeout <= 3600 - AuthTokenManager.TOKEN_BUFFER_SECONDS


def test_service_tokens_come_from_the_services_issuer_when_set(monkeypatch):
    """hmd-ms-deployment checks a non-human token against ``services_issuer``.

    ``OAUTH_PROVIDER_URL`` is the issuer the GUI's users log in against; a
    client-credentials token from it carries the human audience and is refused as
    a service call. ``SERVICE_TOKEN_ISSUER`` names the server service tokens come
    from instead.
    """
    monkeypatch.setenv("OAUTH_PROVIDER_URL", "https://idp.test/oauth2/default")
    monkeypatch.setenv("SERVICE_TOKEN_ISSUER", "https://idp.test/oauth2/services")
    assert AuthTokenManager().okta_issuer == "https://idp.test/oauth2/services"


def test_the_login_issuer_is_the_fallback(monkeypatch):
    monkeypatch.setenv("OAUTH_PROVIDER_URL", "https://idp.test/oauth2/default")
    monkeypatch.delenv("SERVICE_TOKEN_ISSUER", raising=False)
    assert AuthTokenManager().okta_issuer == "https://idp.test/oauth2/default"


def test_missing_credentials_warn_once_and_return_no_token():
    """Without credentials every service-account call goes out anonymous.

    That used to be a DEBUG line, so a pod with no SERVICE_CLIENT_* looked healthy
    while the deployment service refused each call as Unauthorized. Say so at
    WARNING -- once, since this runs on every uncached call.
    """
    m = AuthTokenManager()
    m.okta_issuer, m.client_id, m.client_secret = "https://idp.test", None, None
    with (
        mock.patch("deployments.services.auth.cache") as cache,
        mock.patch("deployments.services.auth.httpx.post") as post,
        mock.patch("deployments.services.auth.logger") as logger,
    ):
        cache.get.return_value = None
        assert m.get_token() is None
        assert m.get_token() is None
        post.assert_not_called()

    logger.warning.assert_called_once()
    assert "SERVICE_CLIENT_ID" in logger.warning.call_args.args[0]
