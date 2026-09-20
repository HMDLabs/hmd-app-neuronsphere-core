"""Production settings for NeuronSphere Deployment GUI."""
import os
from .base import *  # noqa: F401, F403


def _env_bool(name, default):
    """Parse a boolean env var; fall back to ``default`` when unset."""
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


DEBUG = False

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
if pod_ip := os.environ.get("POD_IP"):
    ALLOWED_HOSTS.append(pod_ip)

# Security settings
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

# PostgreSQL database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "deployment_gui"),
        "USER": os.environ.get("DB_USER"),
        "PASSWORD": os.environ.get("DB_PASSWORD"),
        "HOST": os.environ.get("DB_HOST"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# Security settings for HTTPS. Overridable so a local (plain-http) deploy can turn the
# HTTPS-only enforcement off; all default to the hardened production values.
SECURE_SSL_REDIRECT = _env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = _env_bool("DJANGO_SESSION_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = _env_bool("DJANGO_CSRF_COOKIE_SECURE", True)
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REDIRECT_EXEMPT = [r"^health/$"]

# CSRF trusted origins
CSRF_TRUSTED_ORIGINS = os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")

# OAuth-only login in production; a local deploy can re-enable username/password auth
# (DJANGO_SOCIALACCOUNT_ONLY=false) so acceptance tests can sign in without an IdP.
# Forced off when no OIDC provider is configured (see SOCIALACCOUNT_PROVIDERS below):
# social-only login with zero social providers leaves no way to sign in at all.
# Recomputed here rather than inherited: base.py is already in sys.modules by the
# time this module is (re)loaded, so its module-level values would reflect the
# environment at first import instead of the current one.
IDP_PROVIDERS = load_idp_providers()
IDP_GROUPS_CLAIMS = groups_claims_for(IDP_PROVIDERS)
IDP_GROUP_MAPPING = load_json_env("IDP_GROUP_MAPPING")
OKTA_GROUP_MAPPING = load_json_env("OKTA_GROUP_MAPPING")
IDP_SUPERUSER_GROUPS = load_json_env("IDP_SUPERUSER_GROUPS")
OKTA_SUPERUSER_GROUPS = load_csv_env("OKTA_SUPERUSER_GROUPS")

SOCIALACCOUNT_ONLY = _env_bool("DJANGO_SOCIALACCOUNT_ONLY", True) and bool(
    IDP_PROVIDERS
)

# OIDC provider registry, built from the normalised IDP_PROVIDERS list in base.py.
# Every provider -- Okta, Auth0, Entra, or a customer's own -- goes through allauth's
# generic `openid_connect` provider, one APPS entry each, so adding an IdP is
# configuration rather than a code change. Each needs its authorization server to
# emit the group claim named by that provider's `groups_claim`.
#
# Registered only for providers that actually have an issuer. The local NeuronSphere
# deploy runs without any IdP (helm `config.oktaAuth: false` drops the OAUTH_* env
# vars along with the ExternalSecrets that back them), and registering a provider with
# a null server_url would still put a button on the login page -- allauth builds the
# provider from these settings when the template asks for it, and a null issuer fails
# there rather than here. With the registry empty, login.html's
# `{% if socialaccount_providers %}` blocks collapse to username/password, which is the
# account the chart's init container creates.
SOCIALACCOUNT_PROVIDERS = (
    {
        "openid_connect": {
            "APPS": [
                {
                    "provider_id": provider["provider_id"],
                    "name": provider["name"],
                    "client_id": provider["client_id"],
                    "secret": provider["client_secret"],
                    "settings": {
                        "server_url": provider["server_url"],
                        "token_params": {"scope": provider["scope"]},
                    },
                }
                for provider in IDP_PROVIDERS
            ],
        }
    }
    if IDP_PROVIDERS
    else {}
)

# Cache — Redis when the `redis` dependency is resolved (REDIS_HOST set),
# otherwise falls back to the per-process LocMemCache.
CACHES = {
    "default": redis_cache_config()
    or {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}

# JSON logging for production
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
