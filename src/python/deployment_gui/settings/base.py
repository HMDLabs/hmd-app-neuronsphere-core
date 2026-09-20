"""Base Django settings for NeuronSphere Deployment GUI."""
import importlib.util
import json
import logging
import os
from pathlib import Path
from urllib.parse import quote

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "django-insecure-dev-only-change-in-production"
)

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third-party
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.openid_connect",
    "django_htmx",
    # Local
    "deployments",
]


def _module_list(name, default):
    return [
        m.strip()
        for m in os.environ.get(name, ",".join(default)).split(",")
        if m.strip()
    ]


# The extension seam (NERD0015). An image layered on this one -- the premium
# hmd-app-neuronsphere, which adds run observability and apply -- names its
# Django apps here. Each is installed, its ``urls`` module (if any) is included
# at the root, and its ``<app>/slots/<name>.html`` templates render into the
# core pages' ``{% extension_slot %}`` points. The core itself never imports or
# links to anything in them.
EXTRA_APPS = _module_list("DJANGO_EXTRA_APPS", [])
INSTALLED_APPS += [app for app in EXTRA_APPS if app not in INSTALLED_APPS]

# The class the service client is built from. An extra app may widen it (a
# subclass adding the routes only its service serves) without the core
# knowing those routes exist.
DEPLOYMENT_API_CLIENT_CLASS = os.environ.get(
    "DEPLOYMENT_API_CLIENT_CLASS", "deployments.services.api_client.DeploymentAPIClient"
)

# URL-path prefix -> sidebar section, for sections an extra app contributes
# (the core's own are in deployments.context_processors). "deployments=/deployments".
EXTENSION_SECTIONS = dict(
    item.split("=", 1) for item in _module_list("EXTENSION_SECTIONS", []) if "=" in item
)

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    # Redirect Okta users to re-authenticate once their access token expires,
    # instead of rendering views with a stale token. Must sit after the auth,
    # allauth, and htmx middleware so request.user / request.htmx are populated.
    "deployments.middleware.OktaTokenExpiryMiddleware",
]

ROOT_URLCONF = "deployment_gui.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "deployments.context_processors.sidebar_context",
            ],
        },
    },
]

WSGI_APPLICATION = "deployment_gui.wsgi.application"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sites framework (required by allauth)
SITE_ID = 1

# Authentication backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# django-allauth configuration
ACCOUNT_AUTHENTICATION_METHOD = "username_email"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_EMAIL_VERIFICATION = "none"
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_ON_GET = True
SOCIALACCOUNT_ADAPTER = "deployments.adapters.NeuronSphereSocialAccountAdapter"
# Persist the Okta access token on SocialToken so views can forward it to
# downstream services (the default flipped to False in allauth >= 0.58).
SOCIALACCOUNT_STORE_TOKENS = True

# ---------------------------------------------------------------------------
# Identity providers
#
# The GUI is not Okta-only: customers run Auth0, Entra, or bring their own OIDC
# provider. A provider is therefore configuration, not a code path. OAUTH_PROVIDERS
# is a JSON list, each entry:
#
#   {"provider_id": "acme-auth0", "name": "Acme SSO",
#    "client_id": "...", "client_secret": "...",
#    "server_url": "https://acme.auth0.com",
#    "scope": "openid profile email groups",          # optional
#    "groups_claim": "https://neuronsphere.io/groups"} # optional, default "groups"
#
# `groups_claim` matters because the claim name is not universal -- Auth0 commonly
# namespaces it and Entra may use "roles".
#
# The single-provider OAUTH_PROVIDER_URL / OAUTH_CLIENT_ID / OAUTH_CLIENT_SECRET
# form is still honoured and synthesises one "okta" provider, so deployments
# predating this keep working untouched.
DEFAULT_GROUPS_CLAIM = "groups"


def _normalize_provider(entry):
    """Fill in the optional keys so downstream code never guesses."""
    provider_id = (entry.get("provider_id") or "").strip()
    server_url = (entry.get("server_url") or "").strip()
    if not provider_id or not server_url:
        return None
    return {
        "provider_id": provider_id,
        "name": entry.get("name") or provider_id,
        "client_id": entry.get("client_id"),
        "client_secret": entry.get("client_secret"),
        "server_url": server_url,
        "scope": entry.get("scope") or "openid profile email groups",
        "groups_claim": entry.get("groups_claim") or DEFAULT_GROUPS_CLAIM,
    }


def load_idp_providers():
    """Parse the configured providers, reading os.environ at call time.

    Deliberately a function rather than a module constant: production.py is
    reloaded (in tests, and as the deployed settings module) after base.py is
    already in sys.modules, so a constant computed here would go stale against
    a changed environment.
    """
    oauth_providers_raw = os.environ.get("OAUTH_PROVIDERS", "")
    if oauth_providers_raw:
        try:
            entries = json.loads(oauth_providers_raw)
        except ValueError:
            # A malformed list must not silently fall back to the legacy single
            # provider -- that would register a different IdP than intended.
            raise
        if isinstance(entries, dict):
            entries = [entries]
        return [p for p in (_normalize_provider(e) for e in entries) if p]

    legacy_url = os.environ.get("OAUTH_PROVIDER_URL")
    if not legacy_url:
        return []
    return [
        _normalize_provider(
            {
                "provider_id": "okta",
                "name": "Okta",
                "client_id": os.environ.get("OAUTH_CLIENT_ID"),
                "client_secret": os.environ.get("OAUTH_CLIENT_SECRET"),
                "server_url": legacy_url,
                "groups_claim": os.environ.get("OAUTH_GROUPS_CLAIM"),
            }
        )
    ]


def groups_claims_for(providers):
    """provider_id -> claim carrying group membership, for the login adapter."""
    return {p["provider_id"]: p["groups_claim"] for p in providers}


IDP_PROVIDERS = load_idp_providers()
IDP_GROUPS_CLAIMS = groups_claims_for(IDP_PROVIDERS)

# Group-to-environment-role mapping (JSON, provided at deploy time).
#
# Provider-scoped form, so two providers can use the same group name for
# different teams:
#   {"acme-auth0": {"transform-authors": {"prod": "deployer"}}}
#
# The legacy OKTA_GROUP_MAPPING is the unscoped form -- {"group": {"env": "role"}}
# -- and still applies to *every* provider. That preserves current behaviour
# exactly for single-provider deployments and is the migration-friendly reading
# when a second provider is added with the same group names.
def load_json_env(name):
    raw = os.environ.get(name, "")
    return json.loads(raw) if raw else {}


IDP_GROUP_MAPPING = load_json_env("IDP_GROUP_MAPPING")
OKTA_GROUP_MAPPING = load_json_env("OKTA_GROUP_MAPPING")

# Group names whose members are promoted to Django superuser. Membership is
# reconciled on every login: a user gains is_superuser/is_staff when any of these
# appears in their groups claim, and loses them otherwise. Locally-created
# accounts (no SocialAccount) are never touched.
#
# IDP_SUPERUSER_GROUPS is the provider-scoped JSON form
# ({"acme-auth0": ["platform-admins"]}); the comma-separated OKTA_SUPERUSER_GROUPS
# remains the unscoped form applying to every provider.
def load_csv_env(name):
    return [g.strip() for g in os.environ.get(name, "").split(",") if g.strip()]


IDP_SUPERUSER_GROUPS = load_json_env("IDP_SUPERUSER_GROUPS")
OKTA_SUPERUSER_GROUPS = load_csv_env("OKTA_SUPERUSER_GROUPS")

# Session configuration
SESSION_COOKIE_AGE = 8 * 60 * 60  # 8 hours
SESSION_SAVE_EVERY_REQUEST = True


def redis_cache_config():
    """CACHES["default"] for django-redis, or None if unavailable/unconfigured.

    Wired the same way hmd-app-airflow/hmd-ms-transform connect to the shared
    hmd-inf-redis instance: host/port come straight from the resolved
    dependency (in-cluster service DNS), username/password from a k8s Secret
    synced by an ExternalSecret. Callers fall back to LocMemCache when this
    returns None — REDIS_HOST unset (the `redis` manifest dependency is
    optional and may not be resolved in every deployment yet), or the
    django-redis package isn't installed. Fail-open on purpose: caching must
    never be a hard dependency for the app to serve requests at all (mirrors
    the fail-open Redis clients elsewhere, e.g. hmd-ms-transform's
    redis_cache.py / hmd-ms-deployment's NERD0005 env_cache.py).
    """
    redis_host = os.environ.get("REDIS_HOST")
    if not redis_host:
        return None
    if importlib.util.find_spec("django_redis") is None:
        logging.getLogger(__name__).warning(
            "REDIS_HOST is set but django_redis isn't installed — "
            "falling back to LocMemCache."
        )
        return None
    redis_port = os.environ.get("REDIS_PORT", "6379")
    redis_user = os.environ.get("REDIS_USERNAME", "")
    redis_pass = quote(os.environ.get("REDIS_PASSWORD", ""), safe="")
    return {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{redis_user}:{redis_pass}@{redis_host}:{redis_port}/0",
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }


# Deployment API configuration
DEPLOYMENT_API_URL = os.environ.get("DEPLOYMENT_API_URL", "http://localhost:8080")
DEPLOYMENT_API_TIMEOUT = int(os.environ.get("DEPLOYMENT_API_TIMEOUT", "30"))
DEPLOYMENT_API_CACHE_TTL = int(os.environ.get("DEPLOYMENT_API_CACHE_TTL", "30"))
# Environment BOMs change only on ChangeSet deployment, so they are cached longer
# and invalidated explicitly on apply. This finite TTL is a backstop against
# cross-worker staleness (LocMemCache is per-process).
DEPLOYMENT_BOM_CACHE_TTL = int(os.environ.get("DEPLOYMENT_BOM_CACHE_TTL", "3600"))

# ============== MCP (Model Context Protocol) server ==============
# A read-only MCP server is mounted at MCP_MOUNT_PATH by deployment_gui/asgi.py,
# alongside the Django app. Shape follows HMD_MS_BASE_NERD001.


def _env_flag(name, default):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes")


MCP_ENABLED = _env_flag("MCP_ENABLED", True)
MCP_MOUNT_PATH = os.environ.get("MCP_MOUNT_PATH", "/mcp")
MCP_SERVER_NAME = os.environ.get("MCP_SERVER_NAME", "neuronsphere-deployment")

# Stateless is required whenever more than one gunicorn worker is running:
# workers do not share memory and requests have no affinity, so a session held
# in one worker is invisible to the next request.
MCP_STATELESS_HTTP = _env_flag("MCP_STATELESS_HTTP", True)

# The /mcp mount sits beside Django, not behind it, so Django's SecurityMiddleware
# and ALLOWED_HOSTS do not apply to it. FastMCP does its own Host/Origin checks
# from these lists; empty means "no restriction" and is only appropriate locally.
MCP_ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()
]
MCP_ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("MCP_ALLOWED_ORIGINS", "").split(",") if o.strip()
]

# Platform-issued bearer keys (MCPApiKey), for local dev, bender, and CI where
# no Okta token is available. Cloud leaves this off and authenticates with Okta below;
# a deployment may enable both, in which case either credential is accepted.
MCP_API_KEYS_ENABLED = _env_flag("MCP_API_KEYS_ENABLED", True)

# Bearer tokens, the cloud credential. Verified against the same authorization server
# the GUI itself logs in against, so none of this needs a secret of its own.
#
# One issuer, not the whole IDP_PROVIDERS list: JWTVerifier takes a single issuer, so
# MCP bearer auth accepts tokens from exactly one IdP even where the GUI offers
# several. The first configured provider is that one unless MCP_OKTA_ISSUER names it
# explicitly. Resolved from IDP_PROVIDERS rather than straight from OAUTH_PROVIDER_URL
# so that a deployment which has moved to OAUTH_PROVIDERS -- and therefore has no
# OAUTH_PROVIDER_URL at all -- does not silently end up with no issuer and switch MCP
# bearer auth off via the MCP_OKTA_ENABLED gate below.
def _default_mcp_issuer():
    for provider in IDP_PROVIDERS:
        if provider.get("server_url"):
            return provider["server_url"]
    return ""


MCP_OKTA_ISSUER = os.environ.get("MCP_OKTA_ISSUER") or _default_mcp_issuer()
# `/v1/keys` is Okta's JWKS path, not a standard one -- Auth0 and Entra publish at
# `/.well-known/jwks.json`. Derived unconditionally all the same, because the issuer
# is not reliably recognisable as Okta (an org fronting Okta with its own domain
# asserts that domain), and refusing to derive would break those deployments rather
# than the non-Okta ones it is aimed at. A provider that publishes elsewhere sets
# MCP_OKTA_JWKS_URI, which wins.
MCP_OKTA_JWKS_URI = os.environ.get("MCP_OKTA_JWKS_URI") or (
    f"{MCP_OKTA_ISSUER.rstrip('/')}/v1/keys" if MCP_OKTA_ISSUER else ""
)
# hmd-ms-deployment verifies a *human* caller's token against exactly this audience
# (hmd_lib_auth.lambda_helper._get_issuer_and_audience), which is what makes forwarding
# the caller's own bearer downstream work. A token minted for any other audience is
# treated as a service token there and rejected.
MCP_OKTA_AUDIENCE = os.environ.get("MCP_OKTA_AUDIENCE", "api://neuronsphere")
# Offline verification escape hatch: a PEM public key instead of a JWKS fetch, so tests
# can drive the Okta path without a network. JWTVerifier accepts one or the other.
MCP_OKTA_PUBLIC_KEY = os.environ.get("MCP_OKTA_PUBLIC_KEY", "")
# There is nothing to validate against without a key source, so the flag alone is not
# enough -- the same reason production.py collapses SOCIALACCOUNT_PROVIDERS to {} when
# OAUTH_PROVIDER_URL is unset rather than registering a provider with a null issuer.
MCP_OKTA_ENABLED = _env_flag("MCP_OKTA_ENABLED", False) and bool(
    MCP_OKTA_ISSUER or MCP_OKTA_PUBLIC_KEY
)

# Public origin of this server (scheme + host, no path). RemoteAuthProvider needs it to
# build the RFC 9728 protected-resource document that MCP clients read to discover where
# their token comes from.
MCP_BASE_URL = os.environ.get("MCP_BASE_URL", "").rstrip("/")

# Which identity the downstream hmd-ms-deployment request carries.
#   passthrough -- an Okta caller forwards their own bearer, so the service applies its
#                  RBAC to the user. An API-key caller has no user token to forward and
#                  uses the service account under either mode.
#   service     -- always the service account.
MCP_DOWNSTREAM_TOKEN_MODE = os.environ.get("MCP_DOWNSTREAM_TOKEN_MODE", "passthrough")

# The extension seam: adding a module to one of these lists is the only
# registration step. Tools are called; resources are the same reads addressed by
# URI; prompts are the multi-tool workflows.
MCP_TOOL_MODULES = _module_list(
    "MCP_TOOL_MODULES",
    [
        "ns_mcp.tools.environments",
        "ns_mcp.tools.bom",
        "ns_mcp.tools.instances",
        "ns_mcp.tools.repo_classes",
        "ns_mcp.tools.resources",
    ],
)
MCP_RESOURCE_MODULES = _module_list(
    "MCP_RESOURCE_MODULES", ["ns_mcp.capabilities.resources"]
)
MCP_PROMPT_MODULES = _module_list("MCP_PROMPT_MODULES", ["ns_mcp.capabilities.prompts"])

# Federating tools from deployed services (see ns_mcp/federation.py). Off until
# a service actually publishes an MCP endpoint and per-caller token forwarding
# through a mounted proxy is settled.
MCP_FEDERATION_ENABLED = _env_flag("MCP_FEDERATION_ENABLED", False)
MCP_FEDERATED_ENDPOINTS = os.environ.get("MCP_FEDERATED_ENDPOINTS", "")

# Response-size guards for the tool layer (a real BOM is large).
MCP_DEFAULT_PAGE_SIZE = int(os.environ.get("MCP_DEFAULT_PAGE_SIZE", "100"))
MCP_MAX_PAGE_SIZE = int(os.environ.get("MCP_MAX_PAGE_SIZE", "500"))

# Telemetry service configuration
TELEMETRY_SERVICE_URLS = {
    env.strip(): url.strip()
    for env_url in os.environ.get("TELEMETRY_SERVICE_URLS", "").split(",")
    if "=" in env_url
    for env, url in [env_url.split("=", 1)]
}
TELEMETRY_SERVICE_TIMEOUT = int(os.environ.get("TELEMETRY_SERVICE_TIMEOUT", "5"))

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "deployments": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
