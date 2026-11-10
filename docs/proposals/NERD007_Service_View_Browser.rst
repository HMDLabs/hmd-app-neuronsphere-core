.. NERD007 Service View Browser and HTMX Partial Mounting

NERD007 Service View Browser and HTMX Partial Mounting
========================================================

.. req:: Service View Browser and HTMX Partial Mounting
    :id: HMD_APP_NEURONSPHERE_NERD007
    :status: in_progress

    Add a generic service browser to the NeuronSphere Django host that, for the currently
    selected environment, lists every deployed service-with-views (one selector query for the
    environment's ``ui.neuronsphere.io/view-set`` Resources, per ``NERD0003_HMD_MS_DEPLOYMENT``),
    surfaces the views each service declares (per ``HMD_BASE_SERVICE_NERD003``), fetches those
    views through a Django proxy
    that forwards the user's bearer token, and mounts them in the host shell.

    The host integration shall be provided by a dedicated base Django app, ``ns_service_views``,
    that owns the registry consumption, mount container, proxy endpoint, icon mapping,
    permission filtering, and observability described in this NERD. The base app shall be
    extensible: a service-specific Django app (e.g. ``ns_service_views_transform``) may be
    installed alongside the base to contribute navbar entries, host-side Django models, and
    host-side views that orchestrate calls across multiple microservice endpoints when a single
    partial on the microservice cannot reasonably do the work. Microservices remain the source
    of truth for view definitions; extensions are strictly additive on the host side.

The Django app today is wired specifically to ``hmd-ms-deployment``; new operator UIs require
host-app changes. This NERD introduces a consumer-side contract that completes the trio with
``HMD_BASE_SERVICE_NERD003`` and ``NERD0003_HMD_MS_DEPLOYMENT``: read the env's view inventory
from one place, render a service browser, and mount selected partials via a same-origin proxy.

Revision 2026-11-10: the view inventory is now the environment's ``view-set`` Resources, not a
registry read through ``views_for_env``. Discovery mirrors the MCP gateway (``NERD012``),
which already finds ``mcp-server`` Resources in each environment with
``find_resources_by_selector``. ``ns_service_views`` should share that discovery code rather
than grow a second copy.
The consumer-side contract is implemented by the ``ns_service_views`` base Django app; any
host-side workflow logic that genuinely belongs on the host (for example, orchestration across
multiple microservice endpoints) lives in a service-specific extension app installed in this
Django project alongside the base.

.. spec:: Service browser page and navigation
    :id: HMD_APP_NEURONSPHERE_NERD007_SPEC001
    :links: HMD_APP_NEURONSPHERE_NERD007
    :status: implemented

    A new top-level navigation entry "Services" shall list, for the currently selected
    environment, every service instance that publishes a ``ui.neuronsphere.io/view-set``
    Resource there (SPEC004). Selecting a service shall reveal that
    service's registered views grouped by their ``group`` field and sorted by ``order``, then
    by ``title``. Each view entry shall display its ``title``, ``description``, and ``icon``.

.. spec:: Mount container and partial loading
    :id: HMD_APP_NEURONSPHERE_NERD007_SPEC002
    :links: HMD_APP_NEURONSPHERE_NERD007
    :status: implemented

    The host shell (``base.html``) shall expose a stable mount container
    ``<div id="ns-service-view">`` inside the existing ``{% block content %}`` for service
    browser pages. Selecting a view shall issue ``hx-get`` against a Django proxy URL of the
    form ``/services/<env>/<instance>/views/<rest>``, where ``/views/<rest>`` is the view's
    declared ``path``, with ``hx-target="#ns-service-view"`` and ``hx-swap="innerHTML"``.
    The partial returned by the microservice shall be rendered directly into the container.

    The service's page lives at ``/services/<env>/<instance>/``. A partial's relative HTMX
    URLs resolve against the page's address, not the proxy's, so a partial shall write its
    links relative to the service root, for example ``hx-get="views/users?page=2"``. Those
    resolve to the proxy route above.

.. spec:: Django proxy endpoint
    :id: HMD_APP_NEURONSPHERE_NERD007_SPEC003
    :links: HMD_APP_NEURONSPHERE_NERD007
    :status: implemented

    A Django view at ``/services/<env>/<instance>/views/<path:rest>/`` shall:

    1. Resolve the service instance's base URL from the ``base_url`` in its ``view-set``
       Resource output (SPEC004). Refuse any ``<instance>`` or view path that the cached
       inventory doesn't list, so the proxy can't be pointed at an arbitrary service.
    2. Forward the request method, query string, and body to ``<base>/<rest>/``.
    3. Forward the *user's* Okta bearer token (not the Django service-account token) in the
       ``Authorization`` header so the microservice can authenticate the end user directly.
    4. Apply the existing ``@require_environment_access("viewer")`` decorator before
       proxying.
    5. Return the response body verbatim with ``Content-Type`` preserved, plus an
       ``X-NS-Service`` response header for traceability.

    Responses larger than a configurable cap (default 1 MiB) shall be rejected with a
    Tailwind-styled error fragment.

.. spec:: Registry consumption and caching
    :id: HMD_APP_NEURONSPHERE_NERD007_SPEC004
    :links: HMD_APP_NEURONSPHERE_NERD007
    :status: implemented

    The host shall read the env's view inventory exclusively from
    ``DeploymentAPIClient.find_resources_by_selector({"ui.neuronsphere.io/kind": "view-set"},
    environment=<env>)``, decoding each Resource's output as the MCP gateway does
    (``deployments.services.resource_query.decode_resource_output``). The host shall not
    enumerate the BOM and shall not call ``/views/manifest`` on individual instances. That
    endpoint is for debugging only. Malformed outputs shall be skipped with a warning, as the
    gateway skips a malformed ``mcp-server``, so one bad service can't break the browser.
    Responses shall be cached in Django's cache keyed by ``env`` with a TTL of 5 minutes by
    default. The cache shall be invalidated for an env whenever a deploy event for any
    instance in that env is received (per ``NERD0003_HMD_MS_DEPLOYMENT_SPEC0005``).

.. spec:: Permission filtering
    :id: HMD_APP_NEURONSPHERE_NERD007_SPEC005
    :links: HMD_APP_NEURONSPHERE_NERD007
    :status: implemented

    Before listing a view in the service browser, the host shall filter by the entry's
    ``required_permissions``. It turns the user's groups (the IdP claims stored at sign-in)
    into permissions with ``permissions_for(groups, group_permissions)``, using the
    ``group_permissions`` map from that service's view-set Resource, the map the service
    itself uses (``HMD_BASE_SERVICE_NERD003_SPEC010``). The host carries its own copy of
    ``permissions_for`` rather than importing ``hmd-lib-auth``, because the GUI depends on no
    hmd library. The copy is tested against the same cases as ``hmd-lib-auth``'s, so the two
    resolve identically and the menu never shows a view the service will refuse. Filtering
    applies only when users sign in through an IdP: without one (local development), services
    skip their own check too, under ``AUTHORIZATION=NONE``. The setting
    ``SERVICE_VIEWS_ENFORCE_PERMISSIONS`` overrides this. Hidden entries shall
    not appear in the menu, and the proxy endpoint shall also enforce the same check
    server-side as defense in depth (the microservice is the ultimate authority per
    ``HMD_BASE_SERVICE_NERD003_SPEC004``).

.. spec:: Icon mapping and asset constraints
    :id: HMD_APP_NEURONSPHERE_NERD007_SPEC006
    :links: HMD_APP_NEURONSPHERE_NERD007
    :status: partial

    The host shall ship the curated icon set (heroicons or lucide) referenced by manifest
    ``icon`` names. Unknown icon names shall fall back to a default placeholder. Partials
    returned through the proxy must rely solely on host-loaded Tailwind, HTMX, and Alpine
    assets; the host shall remove any ``<script>``, ``<link>`` or ``<style>`` a service
    returns before it reaches the browser.

    Status: the asset rule is implemented. The icon set is not yet: views render without
    icons.

.. spec:: Error handling and observability
    :id: HMD_APP_NEURONSPHERE_NERD007_SPEC007
    :links: HMD_APP_NEURONSPHERE_NERD007
    :status: partial

    Proxy and registry interactions shall emit existing telemetry (correlation id, user,
    target service, latency, status). User-visible failure modes shall include: registry
    unreachable, service instance unreachable, view returned non-2xx, view exceeded size
    cap, and user lacks required permission. Each shall return a Tailwind-styled HTML
    fragment that swaps cleanly into ``#ns-service-view`` without breaking the surrounding
    page.

    Status: the error fragments are implemented. Telemetry is only warning logs so far:
    correlation id, user, target service and latency are not yet emitted.

Host Django App Architecture
----------------------------

.. spec:: Base Django app ``ns_service_views``
    :id: HMD_APP_NEURONSPHERE_NERD007_SPEC008
    :links: HMD_APP_NEURONSPHERE_NERD007
    :status: implemented

    A Django app named ``ns_service_views`` shall be the canonical implementation of the host
    responsibilities defined in SPEC001 through SPEC007. It shall own: the view-set discovery
    client and its 5-minute cache (per SPEC004), the proxy endpoint (per SPEC003), the service browser
    pages and ``<div id="ns-service-view">`` mount-container scaffolding (per SPEC001 and
    SPEC002), the curated icon set (per SPEC006), the host-side permission filter (per
    SPEC005), and the telemetry and error fragments (per SPEC007).

    ``ns_service_views`` shall be installable into any NeuronSphere Django project by adding
    it to ``INSTALLED_APPS`` and including its URLconf. With no service-specific extension
    apps installed, ``ns_service_views`` alone shall provide the full generic browser and
    proxy experience described in SPEC001 through SPEC007 unmodified. The existing
    ``deployments`` app remains separate and is not in scope for migration onto this base.

.. spec:: Service-specific extension app contract
    :id: HMD_APP_NEURONSPHERE_NERD007_SPEC009
    :links: HMD_APP_NEURONSPHERE_NERD007
    :status: proposed

    A *service-specific extension app* shall be a standard Django app installed alongside
    ``ns_service_views`` in ``INSTALLED_APPS``. The recommended naming convention is
    ``ns_service_views_<service>`` (for example ``ns_service_views_transform`` for
    ``hmd-ms-transform``).

    Each extension app shall declare, at registration time (typically in its
    ``AppConfig.ready()`` hook), the manifest ``service`` value or values it claims, matching
    the ``service`` field of entries returned by ``GET /apiop/views_for_env/<env>``.
    ``ns_service_views`` shall expose a documented registration API for extensions to use;
    extensions shall not monkey-patch base-app modules. The system shall behave identically
    to the un-extended case for any service whose manifest has no registered extension.

.. spec:: Navbar extension hook
    :id: HMD_APP_NEURONSPHERE_NERD007_SPEC010
    :links: HMD_APP_NEURONSPHERE_NERD007, HMD_APP_NEURONSPHERE_NERD007_SPEC005, HMD_APP_NEURONSPHERE_NERD007_SPEC006
    :status: proposed

    ``ns_service_views`` shall provide a context-processor-driven navbar contribution
    mechanism analogous to the existing ``deployments.context_processors.sidebar_context``.
    Extension apps shall be able to register navbar entries declaring at minimum: ``title``,
    ``url`` (a Django URL name or path), ``icon`` (from the curated icon set in SPEC006),
    ``required_permissions``, ``group``, and ``order``.

    Entries contributed by extensions shall be merged with the auto-generated browser entries
    from SPEC001 and filtered by ``required_permissions`` against the user's resolved Okta
    groups, consistent with SPEC005. Extension-contributed entries shall not bypass the host
    permission filter, and entries whose permissions are not satisfied shall not render.

.. spec:: Host-side multi-endpoint workflow views
    :id: HMD_APP_NEURONSPHERE_NERD007_SPEC011
    :links: HMD_APP_NEURONSPHERE_NERD007, HMD_APP_NEURONSPHERE_NERD007_SPEC003, HMD_APP_NEURONSPHERE_NERD007_SPEC006
    :status: proposed

    Extension apps may implement host-side Django views when a workflow cannot reasonably be
    expressed as a single partial on the microservice -- for example, when it must orchestrate
    calls across multiple endpoints on the same service or across multiple services before
    composing a single response. Such host-side views shall:

    1. Use ``DeploymentAPIClient`` and ``EnvironmentServiceConfig`` for service discovery,
       consistent with SPEC003.
    2. Forward the user's Okta bearer token to each microservice call, consistent with SPEC003
       step 3; the Django service-account token shall not be used for end-user actions.
    3. Apply the same ``@require_environment_access(...)`` decorator as SPEC003 before any
       orchestration call begins.
    4. Be declared as host-side in the extension app's documentation, with a brief
       justification of why the work cannot live on the microservice.
    5. Render with the same asset constraints as proxied partials (per SPEC006): host-loaded
       Tailwind, HTMX, and Alpine assets only; no service-supplied ``<script>`` or ``<link>``
       tags.

    Host-side views are an exception, not the default. The default placement of view logic
    remains the microservice, per ``HMD_BASE_SERVICE_NERD003``.

.. spec:: Host-side Django models in extension apps
    :id: HMD_APP_NEURONSPHERE_NERD007_SPEC012
    :links: HMD_APP_NEURONSPHERE_NERD007
    :status: proposed

    Extension apps may define their own Django models for host-side persistence -- for
    example, draft state for a host-orchestrated workflow, or per-user preferences specific
    to that service. Each extension app shall own its migrations under its own
    ``migrations/`` package.

    Extension apps shall not modify base-app or ``deployments``-app models or migrations.
    Cross-app coordination shall use Django signals or documented base-app hooks rather than
    direct foreign keys into another extension's models.

.. spec:: Default behavior with no extensions
    :id: HMD_APP_NEURONSPHERE_NERD007_SPEC013
    :links: HMD_APP_NEURONSPHERE_NERD007
    :status: implemented

    Installing ``ns_service_views`` alone, with no service-specific extension apps, shall
    yield the full generic browser and proxy experience described in SPEC001 through SPEC007.
    Adding or removing an extension app shall not require any change to the base app and
    shall not regress non-extended services. Bare microservices that contribute only a
    ``/views/manifest`` and partials shall remain first-class consumers of the base app.

.. spec:: Reaching services in other accounts (reserved)
    :id: HMD_APP_NEURONSPHERE_NERD007_SPEC014
    :links: HMD_APP_NEURONSPHERE_NERD007, HMD_APP_NEURONSPHERE_NERD007_SPEC003
    :status: future

    Discovery already works across environments, because view-set Resources are scoped to
    the environment their service is deployed in, wherever that is. Reaching those services
    does not. A control-plane host proxying to a ``base_url`` in a pipeline account needs a
    network path to that account's ApiGateway, and that account's authorizer has to trust
    the host's audience for the user's forwarded token. Until a later revision specifies
    both, the proxy shall serve only view-sets whose ``base_url`` it can reach. It shall list
    any other view-set in the browser as unavailable, with the reason, and never fail the
    whole page. Control-plane services, ``hmd-ms-identity`` among them, are unaffected.
