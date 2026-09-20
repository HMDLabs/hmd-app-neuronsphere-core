"""Multi-provider identity configuration.

The GUI must not be Okta-only: customers run Auth0, Entra, or bring their own
OIDC provider. Every IdP goes through allauth's generic ``openid_connect``
provider as one APPS entry, so adding one is configuration rather than code.

These tests pin the three things that would silently lock a customer out:
providers are registered from the JSON list, the legacy single-provider env vars
still work, and each provider's own groups claim is what gets read.
"""
import importlib
import json
import os

import pytest

SETTINGS_MODULE = "deployment_gui.settings.production"
_ENV_VARS = (
    "OAUTH_PROVIDERS",
    "OAUTH_PROVIDER_URL",
    "OAUTH_CLIENT_ID",
    "OAUTH_CLIENT_SECRET",
    "OAUTH_GROUPS_CLAIM",
    "IDP_GROUP_MAPPING",
    "OKTA_GROUP_MAPPING",
    "IDP_SUPERUSER_GROUPS",
    "OKTA_SUPERUSER_GROUPS",
    "DJANGO_SOCIALACCOUNT_ONLY",
)

TWO_PROVIDERS = [
    {
        "provider_id": "corp-okta",
        "name": "Corp Okta",
        "client_id": "okta-cid",
        "client_secret": "okta-secret",
        "server_url": "https://corp.okta.com/oauth2/default",
    },
    {
        "provider_id": "acme-auth0",
        "name": "Acme SSO",
        "client_id": "auth0-cid",
        "client_secret": "auth0-secret",
        "server_url": "https://acme.auth0.com",
        "groups_claim": "https://neuronsphere.io/groups",
    },
]


@pytest.fixture
def load_settings(monkeypatch):
    def _load(**env):
        monkeypatch.setenv("DJANGO_SECRET_KEY", "test-key")
        for name in _ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return importlib.reload(importlib.import_module(SETTINGS_MODULE))

    yield _load
    # Clear before the restoring reload: monkeypatch tears down *after* this
    # fixture, so a test that set deliberately-invalid config would still have it
    # in os.environ here and the reload would re-raise during teardown.
    for name in _ENV_VARS:
        os.environ.pop(name, None)
    importlib.reload(importlib.import_module(SETTINGS_MODULE))


def _apps(settings):
    return settings.SOCIALACCOUNT_PROVIDERS["openid_connect"]["APPS"]


def test_registers_every_configured_provider(load_settings):
    settings = load_settings(OAUTH_PROVIDERS=json.dumps(TWO_PROVIDERS))
    apps = _apps(settings)
    assert [a["provider_id"] for a in apps] == ["corp-okta", "acme-auth0"]
    assert [a["name"] for a in apps] == ["Corp Okta", "Acme SSO"]


def test_provider_carries_its_own_issuer_and_credentials(load_settings):
    settings = load_settings(OAUTH_PROVIDERS=json.dumps(TWO_PROVIDERS))
    auth0 = _apps(settings)[1]
    assert auth0["client_id"] == "auth0-cid"
    assert auth0["secret"] == "auth0-secret"
    assert auth0["settings"]["server_url"] == "https://acme.auth0.com"


def test_groups_claim_is_per_provider(load_settings):
    """Auth0 commonly namespaces the claim; Okta does not."""
    settings = load_settings(OAUTH_PROVIDERS=json.dumps(TWO_PROVIDERS))
    assert settings.IDP_GROUPS_CLAIMS == {
        "corp-okta": "groups",
        "acme-auth0": "https://neuronsphere.io/groups",
    }


def test_legacy_single_provider_still_registers(load_settings):
    """Deployments predating OAUTH_PROVIDERS must be untouched."""
    settings = load_settings(
        OAUTH_PROVIDER_URL="https://example.okta.com/oauth2/default",
        OAUTH_CLIENT_ID="cid",
        OAUTH_CLIENT_SECRET="secret",
    )
    app = _apps(settings)[0]
    assert app["provider_id"] == "okta"
    assert app["settings"]["server_url"] == "https://example.okta.com/oauth2/default"
    assert settings.IDP_GROUPS_CLAIMS == {"okta": "groups"}


def test_oauth_providers_takes_precedence_over_legacy(load_settings):
    settings = load_settings(
        OAUTH_PROVIDERS=json.dumps(TWO_PROVIDERS),
        OAUTH_PROVIDER_URL="https://legacy.okta.com/oauth2/default",
    )
    assert [a["provider_id"] for a in _apps(settings)] == ["corp-okta", "acme-auth0"]


def test_entry_without_issuer_is_dropped(load_settings):
    """A null server_url would still render a button that fails when clicked."""
    settings = load_settings(
        OAUTH_PROVIDERS=json.dumps(
            [{"provider_id": "broken", "name": "Broken"}] + TWO_PROVIDERS
        )
    )
    assert [a["provider_id"] for a in _apps(settings)] == ["corp-okta", "acme-auth0"]


def test_malformed_provider_list_raises(load_settings):
    """Silently falling back would register a different IdP than intended."""
    with pytest.raises(ValueError):
        load_settings(OAUTH_PROVIDERS="{not json")


def test_no_providers_leaves_registry_empty_and_password_login_on(load_settings):
    settings = load_settings(DJANGO_SOCIALACCOUNT_ONLY="true")
    assert settings.SOCIALACCOUNT_PROVIDERS == {}
    assert settings.SOCIALACCOUNT_ONLY is False


def test_social_only_enabled_once_any_provider_exists(load_settings):
    settings = load_settings(
        OAUTH_PROVIDERS=json.dumps(TWO_PROVIDERS), DJANGO_SOCIALACCOUNT_ONLY="true"
    )
    assert settings.SOCIALACCOUNT_ONLY is True


def test_single_provider_object_accepted(load_settings):
    """A lone object rather than a list is an easy config slip; accept it."""
    settings = load_settings(OAUTH_PROVIDERS=json.dumps(TWO_PROVIDERS[1]))
    assert [a["provider_id"] for a in _apps(settings)] == ["acme-auth0"]


# ---------------------------------------------------------------------------
# MCP bearer auth resolves its issuer from the same provider configuration.
#
# These reload base.py rather than production.py: MCP_OKTA_ISSUER is defined in
# base and not re-exported, so production's reload would read a stale value.
# ---------------------------------------------------------------------------
BASE_SETTINGS_MODULE = "deployment_gui.settings.base"


@pytest.fixture
def load_base(monkeypatch):
    def _load(**env):
        monkeypatch.setenv("DJANGO_SECRET_KEY", "test-key")
        for name in _ENV_VARS + ("MCP_OKTA_ISSUER", "MCP_OKTA_JWKS_URI"):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return importlib.reload(importlib.import_module(BASE_SETTINGS_MODULE))

    yield _load
    for name in _ENV_VARS + ("MCP_OKTA_ISSUER", "MCP_OKTA_JWKS_URI"):
        os.environ.pop(name, None)
    importlib.reload(importlib.import_module(BASE_SETTINGS_MODULE))


def test_mcp_issuer_comes_from_oauth_providers(load_base):
    """The regression: a deployment on OAUTH_PROVIDERS has no OAUTH_PROVIDER_URL.

    Reading the legacy var alone left MCP_OKTA_ISSUER empty, which switches
    MCP_OKTA_ENABLED off -- bearer auth silently disabled rather than failing.
    """
    base = load_base(OAUTH_PROVIDERS=json.dumps(TWO_PROVIDERS), MCP_OKTA_ENABLED="true")
    assert base.MCP_OKTA_ISSUER == "https://corp.okta.com/oauth2/default"
    assert base.MCP_OKTA_ENABLED is True


def test_mcp_issuer_still_honours_the_legacy_var(load_base):
    base = load_base(
        OAUTH_PROVIDER_URL="https://legacy.okta.com", MCP_OKTA_ENABLED="true"
    )
    assert base.MCP_OKTA_ISSUER == "https://legacy.okta.com"


def test_an_explicit_mcp_issuer_wins_over_the_provider_list(load_base):
    base = load_base(
        OAUTH_PROVIDERS=json.dumps(TWO_PROVIDERS),
        MCP_OKTA_ISSUER="https://explicit.example.com",
    )
    assert base.MCP_OKTA_ISSUER == "https://explicit.example.com"


def test_no_providers_leaves_mcp_bearer_auth_off(load_base):
    base = load_base(MCP_OKTA_ENABLED="true")
    assert base.MCP_OKTA_ISSUER == ""
    assert base.MCP_OKTA_ENABLED is False


def test_jwks_uri_is_derived_from_whatever_issuer_won(load_base):
    """Unconditional derivation: an Okta org fronted by its own domain still works."""
    base = load_base(OAUTH_PROVIDER_URL="https://id.acme.com", MCP_OKTA_ENABLED="true")
    assert base.MCP_OKTA_JWKS_URI == "https://id.acme.com/v1/keys"
