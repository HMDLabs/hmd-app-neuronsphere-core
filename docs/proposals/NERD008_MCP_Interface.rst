.. NERD008 Read-Only MCP Interface

NERD008 Read-Only MCP Interface
========================================================

.. req:: Read-Only MCP Interface
    :id: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    Expose the Deployment GUI's read surface over the Model Context Protocol, so an agent
    can answer "what is deployed in Dev", "what does instance X depend on", "which repo
    classes can provide resource Y", and "what is the deployed configuration of instance Z"
    against the same service layer and the same per-environment RBAC the web UI enforces.

    The interface shall be read-only. It shall reuse the ``deployments/services/`` functions
    the GUI views already call rather than reimplementing any query or shaping logic, so the
    two surfaces cannot drift. Authorization shall be structural rather than per-tool, and
    every call shall be audited.

    The transport shall be a single ``/mcp`` endpoint over Streamable HTTP, authenticated by
    an Okta bearer token or a platform-issued API key, matching ``HMD_MS_BASE_NERD001`` so
    that this server and the future ``hmd-ms-base`` transport are the same protocol surface
    and can be composed rather than bridged.

The GUI already holds everything needed to answer these questions -- the BOM, resource-typed
dependency roles, producers, effective configuration -- but only through a human clicking
pages. Exposing it over MCP makes deployment state queryable by agents without a bespoke
server, and does it through the same RBAC the UI enforces rather than around it.

This is also the first Python MCP implementation in the platform. ``HMD_MS_BASE_NERD001`` and
its siblings are drafted but unimplemented, and the only working MCP code in the tree is
Go-side agent tooling, which shares no code path with the microservice framework. Building the
interface here first de-risks the ``hmd-ms-base`` transport and gives the federation model a
real consumer.

Two constraints shaped the design more than anything else. The first is cost: the deployment
service is expensive to fan out against, and a model will happily ask for far more than it
needs. The second is that the GUI's own view layer has known authorization gaps, so "do what
the views do" was not an acceptable answer for how the MCP surface authorizes; see SPEC003 and
SPEC013.

.. spec:: Service-layer extraction
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC001
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    The query and shaping logic shared by the web views and the MCP tools shall live in
    ``deployments/services/`` and be called by both. No MCP tool shall reimplement a query,
    filter, sort, pagination, or projection the GUI already performs.

    Seven pure helpers, three inline query blocks, and a duplicated pagination dictionary
    were moved out of ``views.py`` into ``services/`` (``bom_query``, ``dependency_roles``,
    ``instance_detail``, ``repo_class_detail``, ``resource_query``, ``config_projection``,
    ``pagination``, ``authz``, ``audit``). Five existing tests that regex-extracted function
    source out of ``views.py`` and ``exec``'d it became plain imports.

.. spec:: Transport and ASGI entry point
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC002
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    The MCP server shall be mounted at ``/mcp`` beside the Django application by an ASGI
    entry point (``deployment_gui/asgi.py``), not registered as a Django view. It is a
    complete ASGI application with its own transport and authentication, and a Starlette
    router is the honest way to express that.

    Consequences that shall be documented at the mount point:

    1. Django's ``SecurityMiddleware``, ``CsrfViewMiddleware``, and ``ALLOWED_HOSTS`` do not
       apply to ``/mcp``. FastMCP performs its own Host and Origin checks, configured from
       ``MCP_ALLOWED_HOSTS`` and ``MCP_ALLOWED_ORIGINS``.
    2. The MCP application's lifespan must be passed to the router, or the session manager
       never initialises.
    3. ``stateless_http`` is required, not optional: gunicorn forks several workers with no
       request affinity, so a session held in one worker's memory is invisible to the next
       request.
    4. ``MCP_ENABLED=false`` serves the bare Django application. Together with
       ``GUNICORN_WORKER_CLASS=sync`` and the retained ``wsgi.py``, that is the rollback
       lever for the WSGI-to-ASGI switch.

.. spec:: Structural authorization
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC003
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    Authorization shall be performed by the ``@read_tool`` decorator, not by tool bodies. A
    tool declares which of its parameters names an environment (``environment_arg``, a string
    or a tuple when a tool spans more than one), and the decorator calls
    ``assert_environment_access`` for every one of them before the body runs. First failure
    wins.

    This is deliberately opt-out rather than opt-in, and a test shall enforce the invariant:
    any tool or resource taking a parameter named ``environment``, or ending in
    ``_environment``, must declare it to the decorator. The test drives
    ``settings.MCP_TOOL_MODULES`` rather than a fixed import, so a newly added module is
    covered automatically.

    The reason for making this structural is SPEC013: several GUI endpoints accepted an
    arbitrary ``?environment=`` behind only ``@login_required``. The MCP surface must not
    inherit that class of bug by construction.

.. spec:: Auditing
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC004
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    Every tool call and resource read shall write an ``AuditLog`` row, including calls that
    were refused. The row shall record the resolved Django user, the tool name, the transport
    (``mcp``), the authentication mode, the correlation id, the duration, and the outcome.

    Arguments shall be recorded through an allowlist rather than a denylist, so a future tool
    cannot leak a payload into the audit log merely by adding a parameter.

.. spec:: Read-only tool surface
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC005
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    Eleven tools shall be advertised, each a thin adapter over SPEC001's service layer:

    - ``list_environments`` -- the caller's accessible environments.
    - ``describe_environment`` -- the BOM, at ``summary`` or ``full`` detail, with filters,
      facets, sorting, and pagination.
    - ``describe_instance`` -- one instance's metadata, effective configuration, and
      dependency wiring with each role tagged by kind.
    - ``get_instance_configuration`` -- the narrower, cheaper read of just the configuration,
      able to project a dotted path (list indices included) or list keys with their types, so
      a several-hundred-key document is navigable in two cheap steps rather than one
      expensive one.
    - ``get_instance_dependencies`` -- edges in either direction. The reverse direction is
      new surface; the GUI exposes it only visually, through the DAG.
    - ``search_repo_classes`` and ``describe_repo_class`` -- the catalog of what can be
      deployed and what each version declares.
    - ``list_resource_definitions`` -- the vocabulary of dependency roles.
    - ``find_resource_providers`` -- which repo classes could satisfy a role. This fuses
      three GUI flows that no single page shows together.
    - ``find_resource_candidates`` -- the same question about what is already deployed in one
      environment.
    - ``compare_environments`` -- how two environments have diverged.

    The server ``instructions`` shall steer a caller through the surface: summary before
    full, ``get_instance_dependencies`` rather than ``describe_instance`` when walking many
    instances, catalog before producers.

.. spec:: Response cost constraints
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC006
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    ``classify_dependency_roles`` issues one ``find_repo_class_versions`` plus one
    ``suggest_resource_dependencies`` per ``(class, version)`` pair. It shall only be called
    for a *single* instance. Fanning it out across a BOM is exactly what caused the DAG
    gateway timeouts fixed in ``e4de1e1``.

    Each tool shall be held to a call budget by test, against a fake client that records
    every call it receives. In particular: ``describe_environment`` shall cost exactly one
    ``get_deployment_bom`` and zero classification calls at either detail level;
    ``describe_instance`` shall classify exactly one pair; ``get_instance_configuration``
    shall cost one ``get_deployment_config`` and classify nothing; ``describe_repo_class``
    shall use the paged ``find_repo_class_versions_page`` and never the unpaged variant that
    resolves dependencies per version; and ``compare_environments`` shall read no BOM at all.

    Caller-supplied page sizes shall be clamped to ``MCP_DEFAULT_PAGE_SIZE`` and
    ``MCP_MAX_PAGE_SIZE`` rather than rejected. A truncated answer is more useful to a model
    than an error.

.. spec:: Resources and prompts
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC007
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    The same reads shall additionally be addressable by URI under ``neuronsphere://``, and
    the multi-tool workflows shall be published as prompts.

    Resource bodies shall re-wrap the tool bodies in ``@read_tool``, so a resource read is
    authorized and audited identically to the tool call it delegates to. Prompts take no
    context and read nothing, so they are not decorated.

    Tools, resources, and prompts shall each be registered from a settings-driven module list
    (``MCP_TOOL_MODULES``, ``MCP_RESOURCE_MODULES``, ``MCP_PROMPT_MODULES``); adding a module
    to one of those lists shall be the only registration step. The health endpoint shall
    report the three counts separately, so a capability that failed to register cannot hide
    inside the tool count.

.. spec:: Platform API key authentication
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC008
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    An ``MCPApiKey`` model shall provide bearer tokens for local development, acceptance
    tests, and CI, where no Okta token is available. Only the SHA-256 hash of the key shall
    be stored; the plaintext is shown once at creation and is unrecoverable afterwards.

    A key authorizes *as its owner*: every tool applies the same ``UserEnvironmentPermission``
    checks the GUI applies to that user. Every failure mode -- unknown, revoked, expired,
    malformed -- shall be indistinguishable to the caller.

    ``create_mcp_api_key`` shall accept a supplied key (``--key``) as well as generating one,
    so a deploy-time bootstrap can install a known value without parsing it back out of pod
    stdout, and shall not echo a supplied key into deploy logs.

.. spec:: Okta bearer authentication and identity mapping
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC009
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    Cloud callers shall authenticate with an Okta bearer token, verified via JWKS at
    ``{OAUTH_PROVIDER_URL}/v1/keys`` against the same authorization server the GUI logs in
    against. ``OAUTH_PROVIDER_URL`` is already present in the pod, so this requires no new
    secret.

    A verified token shall be resolved to a Django user by joining on the access token's
    ``uid`` claim against ``SocialAccount.uid`` for ``provider="okta"``. The join must be on
    ``uid`` and not ``sub``: django-allauth stores the *ID token's* ``sub`` (the Okta user id,
    ``00u...``) in ``SocialAccount.uid``, while an *access* token's ``sub`` is the user's
    email, so matching on ``sub`` first fails for every user. A secondary match of ``sub``
    against ``User.email`` shall cover an authorization server that does not emit ``uid``;
    issuer and audience are verified before it runs, so it cannot admit an identity from
    another tenant.

    A token that verifies but matches no local account shall *not* be rejected as
    unauthenticated. It shall be returned tagged with its authentication mode and without a
    user id, which the principal layer turns into an actionable message directing the holder
    to sign in to the GUI once so their account and permissions are provisioned. Only a token
    that fails verification is indistinguishable from any other bad credential.

    Each verifier shall stamp the authentication mode onto the token's claims. A missing mode
    defaults to the API-key path, which would silently route an Okta caller's downstream
    request to the service account, so a test shall assert the claim is present on every
    token the Okta verifier returns.

.. spec:: Credential composition and protected resource metadata
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC010
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    ``build_auth_provider()`` shall be the single place authentication is wired. A deployment
    may enable either credential or both; with both enabled they compose as
    ``MultiAuth(server=RemoteAuthProvider(...), verifiers=[ApiKeyVerifier()])``.

    The Okta side must be the ``server`` argument rather than a second verifier.
    ``MultiAuth`` delegates route creation only to its server, and those routes are the
    RFC 9728 protected-resource metadata document a client reads to discover where to obtain
    a token. An Okta side passed as a verifier would authenticate correctly and never
    advertise itself.

    The metadata document shall be served at the application root, at
    ``/.well-known/oauth-protected-resource/mcp``, and not underneath the ``/mcp`` mount,
    where no client looks. The ASGI entry point shall splice the provider's well-known routes
    in above the Django catch-all.

    The resource URL shall be the server's public URL (``MCP_BASE_URL`` plus the mount path)
    rather than being composed from the path the application is served at internally.
    Composing it from the internal path yields a trailing slash the endpoint does not have,
    and, more seriously, the 401 challenge is computed from the outer provider while the
    metadata route is created by the inner one, so the two can disagree and leave discovery
    pointing at a document that does not exist. Tests shall pin the exact string on both
    sides.

    If no credential is configured and ``DEBUG`` is false, the server shall refuse to start
    rather than serve unauthenticated. An incompletely configured credential shall likewise
    fail loudly, naming the missing setting; falling back to the remaining credential would
    turn a misconfiguration into a less protected server.

.. spec:: Downstream identity
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC011
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    Under the default ``MCP_DOWNSTREAM_TOKEN_MODE=passthrough``, a call authenticated by an
    Okta bearer shall forward the caller's own token to ``hmd-ms-deployment``, so that service
    applies its RBAC to the user. This matches what ``get_api_client_for_request`` does for
    the web views.

    A call authenticated by an API key has no user token to forward and shall use the service
    account. Authorization still happens locally, against the key's owner. This asymmetry is
    deliberate and shall be documented on the model.

    ``MCP_DOWNSTREAM_TOKEN_MODE=service`` shall force every downstream call onto the service
    account, as the fallback for a deployment where forwarding is not accepted.

    Whether forwarding is accepted is a fact about the other service, not about this one.
    ``hmd_lib_auth`` verifies a *human* caller against ``aud: api://neuronsphere`` only when
    the token's ``cid`` is a trusted human client; a token issued to any other client is
    treated as a service token and checked against ``api://neuronsphere-services`` instead,
    and fails. A ``check_mcp_token`` management command shall print a real token's ``iss``,
    ``aud``, ``cid``, ``uid``, and ``sub``, verify it, and report the resolved user, so this
    can be confirmed against a live environment rather than assumed. If ``cid`` is not
    trusted downstream, the remedy is ``HMD_LIB_AUTH_NERD001`` (configurable trusted client
    ids), not the service-token fallback.

.. spec:: Acceptance testing
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC012
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: proposed

    A protocol-level acceptance suite (``test/12_mcp.robot``) shall speak JSON-RPC to
    ``/mcp/`` directly rather than driving a browser, covering the bearer challenge, the
    initialize handshake, every advertised tool, resource, and prompt, and tool calls against
    a seeded BOM. It shall introduce no new pip dependency.

    The suite is also the acceptance check on SPEC002: if the application ever falls back to
    WSGI, the endpoint disappears and the whole suite fails.

    The suite has been authored but not yet executed. Running it, together with the existing
    browser-driven suites 01 through 11, against a local deploy remains the outstanding
    regression check on the WSGI-to-ASGI switch. Unit tests cover the MCP surface but do not
    prove the browser-driven GUI flows still work under uvicorn workers.

.. spec:: View-layer authorization
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC013
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    Every view that takes an environment from the request, rather than from the route it
    was matched on, shall authorize it before fetching any data for it. The check shall go
    through ``services.authz.user_has_environment_access`` -- the same function SPEC003 uses
    -- so there is one definition of the decision across both surfaces.

    Six views accepted a caller-named environment behind only ``@login_required``:
    ``api_search_instances``, ``api_search_instances_html``, ``api_dep_candidates``,
    ``api_repo_class_version_resources``, ``changeset_bom_impact``, and
    ``environment_compare_create_changeset``. The last is a POST that copies the named
    environments' instance records into a persisted draft, and is the reason this is
    remediation rather than tidying; its single-environment sibling
    ``bom_create_changeset`` was correctly decorated, which is what marks the omission as an
    oversight. ``api_search_instances`` additionally defaulted to ``environment="dev"``,
    reading an environment the caller had not named.

    ``require_environment_access`` shall support this range of views directly rather than
    forcing each to hand-roll a check:

    1. ``param`` accepts a tuple, so a view spanning two environments authorizes both, first
       failure wins. This mirrors ``@read_tool``'s ``environment_arg``.
    2. ``when_missing="defer"`` hands off to the view when no environment is named, for the
       HTMX partials that render a "pick an environment" hint. Deferring is safe precisely
       because no environment means no environment data is fetched.
    3. ``response`` selects the denial shape -- ``page``, ``partial``, or ``json``.
       ``access_denied.html`` extends ``base.html``, so returning it to a caller expecting
       JSON, or swapping it into an HTMX target, would turn a correct 403 into a broken
       page.

    ``require_deployment_set_access`` remains applied to zero views: the only view taking a
    deployment set, ``changeset_apply``, checks inline so it can redirect with a message
    rather than render a 403, which is the better result for a POSTed form. It now calls
    ``user_has_deployment_set_access`` rather than the model directly. The decorator's
    ``when_missing`` shall default to denying; it previously invoked the view whenever it
    found no deployment set, so applying it to a view that carried the set anywhere it did
    not look would have protected nothing while appearing to.

    Note for the record that ``UserEnvironmentPermission.user_can_view`` and its
    ``DeploymentSetPermission`` counterparts already short-circuit on ``is_superuser``. The
    inline checks in ``environment_compare`` and ``resource_list`` were therefore never a
    privilege bug; routing them through ``services/authz`` is a single-definition change, and
    their behavior is unchanged.

.. spec:: Federation
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC014
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: proposed

    A service opting into MCP shall publish a Resource of definition
    ``mcp.neuronsphere.io/mcp-server`` carrying ``url`` and ``namespace``. Discovery then
    reuses ``find_resources_by_selector`` and ``list_resources``, which already exist on the
    client, rather than introducing a separate registry.

    One problem must be resolved before this is enabled: a proxy mounted once at startup
    carries a single downstream identity, but each call should forward the *caller's* bearer,
    per SPEC011. Until that is settled, federation stays off by default and is limited to
    endpoints reachable with the service token.

    This is genuinely last. It requires ``HMD_MS_BASE_NERD001`` to be implemented somewhere.
    The seam ships inert so that nothing needs retrofitting.

.. spec:: Capability search and the discovery resource
    :id: HMD_APP_NEURONSPHERE_NERD008_SPEC015
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    An agent that knows what it needs done but not what it is called shall be able to find the
    repo class for it. The catalog half of the surface gains:

    - ``search_capabilities(query, kind, repo_class_name, limit, offset)`` -- one call to
      ``GET /apiop/search_discovery`` (``hmd-ms-deployment`` NERD0013 SPEC0002), which
      matches every whitespace token of ``query`` against each class's latest-version
      summary, capability names and descriptions, and entry points; ``kind`` is an exact
      BACON capability kind, validated locally so a typo costs no round trip;
      ``repo_class_name`` is a prefix filter. The result carries ``capabilities`` (one row per
      matching capability with class, version, kind, description and source location, shaped
      by the same ``build_capability_rows`` the GUI's capability search renders) and
      ``repo_classes`` (every matching class, ranked, with ``score``, ``matched_fields`` and
      ``capability_count`` -- including summary-only hits with no capability rows). A catalog
      tool: no ``environment_arg``, and it declares its call budget in ``test_mcp_tools``
      like every other tool.
    - ``search_repo_classes`` populates the ``description`` it has always emitted -- and
      always emitted empty -- from the latest version's summary, which ``list_repo_classes``
      now returns, and matches the query against it; each entry also reports
      ``latest_version`` and ``capability_count``.
    - the templated resource ``neuronsphere://repo-classes/{repo_class_name}/discovery``
      returns one class's full discovery block (summary, entry points, every capability,
      related docs) at its latest version. It is one ``search_discovery`` call with the class
      name as the prefix filter and an exact-name pick on the result, because the prefix
      ``hmd-ms-deploy`` would otherwise also answer for ``hmd-ms-deployment``.
    - the ``find_capability`` prompt records the intended call order: ``search_capabilities``
      first, then ``describe_repo_class`` (or the resource) on the best hit, then
      ``describe_environment`` to say whether it is deployed anywhere.

    Nothing here searches class names -- ``search_repo_classes`` does that -- and nothing here
    reads a manifest: the discovery block is whatever the version was registered with, which
    locally depends on the seeder forwarding it (NERD0013 SPEC0005).

Operational notes
-----------------

Two things about running this are worth recording, neither of which is a requirement.

Cloud deployments enable the Okta credential and disable API keys. Before SPEC009 existed
that combination left the server with no credential at all, and because
``build_auth_provider()`` is called at import time from ``asgi.py``, the process failed to
start rather than degrading. The pairing is now asserted by the chart render tests.

Redis becomes effectively required under ASGI. It is declared optional in the manifest and
the cache configuration fails open to a per-process ``LocMemCache``. With N workers that
means N copies of the BOM cache and N token fetches, and MCP adds a second high-volume
consumer of the same large payloads. The service account is a related gap: the deployment
supplies no ``SERVICE_CLIENT_ID`` or ``SERVICE_CLIENT_SECRET``, so the service-token path in
SPEC011 has no credentials in cloud today, and the server logs at boot when that mode is
selected without them.
