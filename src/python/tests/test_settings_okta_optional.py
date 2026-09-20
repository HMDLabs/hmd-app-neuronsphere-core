"""Production settings degrade cleanly when Okta is not configured.

The local NeuronSphere deploy has no Okta: the helm chart's `config.oktaAuth:
false` drops the `OAUTH_*` env vars along with the ExternalSecrets backing them.
Django must then register *no* OIDC provider -- an entry with a null `server_url`
still renders an "Okta" button that fails when allauth builds the provider from
it -- and must not stay in social-only mode, which with an empty registry leaves
no way to sign in at all.
"""

import importlib
import os

import pytest

SETTINGS_MODULE = "deployment_gui.settings.production"
_OAUTH_VARS = (
    "OAUTH_PROVIDER_URL",
    "OAUTH_CLIENT_ID",
    "OAUTH_CLIENT_SECRET",
    "DJANGO_SOCIALACCOUNT_ONLY",
)


@pytest.fixture
def load_settings(monkeypatch):
    """Import production.py fresh under a given environment.

    The module is read for its own attributes rather than through
    django.conf.settings: settings are frozen at django.setup() during conftest
    collection, so reloading is the only way to see a different environment.
    """

    def _load(**env):
        monkeypatch.setenv("DJANGO_SECRET_KEY", "test-key")
        for name in _OAUTH_VARS:
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return importlib.reload(importlib.import_module(SETTINGS_MODULE))

    yield _load
    # Leave the module matching the ambient environment for any later test.
    importlib.reload(importlib.import_module(SETTINGS_MODULE))


def test_no_provider_registered_without_issuer(load_settings):
    settings = load_settings()
    assert settings.SOCIALACCOUNT_PROVIDERS == {}


def test_social_only_disabled_without_issuer(load_settings):
    """Otherwise the login page offers neither a password form nor a provider."""
    settings = load_settings(DJANGO_SOCIALACCOUNT_ONLY="true")
    assert settings.SOCIALACCOUNT_ONLY is False


def test_provider_registered_when_issuer_present(load_settings):
    """Cloud path is unchanged."""
    settings = load_settings(
        OAUTH_PROVIDER_URL="https://example.okta.com/oauth2/default",
        OAUTH_CLIENT_ID="cid",
        OAUTH_CLIENT_SECRET="secret",
    )
    app = settings.SOCIALACCOUNT_PROVIDERS["openid_connect"]["APPS"][0]
    assert app["provider_id"] == "okta"
    assert app["client_id"] == "cid"
    assert app["settings"]["server_url"] == "https://example.okta.com/oauth2/default"
    assert settings.SOCIALACCOUNT_ONLY is True
