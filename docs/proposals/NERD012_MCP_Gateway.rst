.. NERD012 MCP Registry and Environment-Aware Gateway

NERD012 MCP Registry and Environment-Aware Gateway
========================================================

.. req:: MCP Registry and Environment-Aware Gateway
    :id: HMD_APP_NEURONSPHERE_NERD012
    :links: HMD_APP_NEURONSPHERE_NERD008
    :status: implemented

    Every MCP server NeuronSphere hosts -- its own services, and third-party servers such
    as a Trino or ClickHouse MCP server -- shall be discoverable and callable through the
    GUI's single ``/mcp`` endpoint.

    A server deployed to several environments shall appear as **one** logical server.
    Each of its tools shall take an ``environment`` argument whose allowed values are
    exactly the environments the caller may use, and a call shall only ever be routed to
    an environment the caller is authorized for. A caller with access to dev alone can
    reach only the dev deployment; a caller with access to dev, test and prod chooses
    among all three.

    This supersedes ``HMD_APP_NEURONSPHERE_NERD008_SPEC014`` (Federation), whose
    mount-once proxy could not carry each caller's identity.

Why build it here
-----------------

Before building, we surveyed the open-source MCP gateways: Bifrost, LiteLLM, IBM
ContextForge, agentgateway, Envoy AI Gateway, Microsoft mcp-gateway, the Docker MCP
Gateway, Obot and Unla, plus the official MCP Registry. All of them aggregate several
upstream servers behind one endpoint and prefix tool names, and most offer per-key or
per-team allow-lists. None of them does the one thing this requirement turns on:

* Each gateway treats dev, test and prod as **separate** servers (``dev-trino``,
  ``prod-trino``). None merges them and adds an ``environment`` argument.
* Routing by an argument value, limited by identity, would be custom code in every one of
  them -- a plugin (ContextForge) or a router in front (agentgateway).
* Their access models are their own (virtual keys, teams), so adopting one would duplicate
  the GUI's ``UserEnvironmentPermission`` grants and IdP group sync. Several also reserve
  SSO for their paid editions.

The GUI already has every other piece: the MCP transport, Okta and API-key bearer auth,
per-environment authorization behind ``assert_environment_access``, an audit trail, and --
through ``hmd-ms-deployment`` -- the record of what is deployed in which environment. So
the gateway is built into the GUI, reusing all of it.

Two ideas were taken from the survey:

* Discovery uses the **official MCP Registry** ``server.json`` / ``/v0/servers`` shape
  rather than a format of our own.
* Like Bifrost and LiteLLM, access is **deny-by-default**, and each caller's tool list is
  filtered to what they may use.

.. spec:: The mcp-server Resource definition
    :id: HMD_APP_NEURONSPHERE_NERD012_SPEC001
    :links: HMD_APP_NEURONSPHERE_NERD012
    :status: implemented

    A deployed MCP server shall announce itself with a Resource of the base definition
    ``mcp.neuronsphere.io/mcp-server`` 0.1.0, which ``hmd-ms-deployment-core`` ships with
    the other base definitions. Its parent is ``application.neuronsphere.io/application``.

    The output carries:

    - ``server_name`` (required) -- the logical name, shared by every environment's
      deployment of the same server. It becomes the tool prefix.
    - ``url`` (required) -- the Streamable HTTP endpoint, reachable from the GUI.
    - ``title``, ``description``, ``version`` -- shown in listings.
    - ``auth_mode`` -- ``service`` (the default) or ``passthrough``; see SPEC004.
    - ``credential_ref`` -- for service mode, which gateway credential to present.
    - ``required_role`` -- ``viewer`` (the default), ``deployer`` or ``admin``.

    The Resource shall be tagged ``mcp.neuronsphere.io/kind=mcp-server``. Serialized
    Resources carry no definition reference, so discovery selects on this tag.

    The environment is **not** part of the output. It is wherever the producing repo
    instance is deployed. The same chart deployed to dev, test and prod therefore yields
    three Resources, which the gateway groups into one server with no per-environment
    configuration anywhere.

    A producer emits the Resource through the usual ``resource-outputs.yaml`` ConfigMap,
    as ``hmd-inf-trino`` does for its own outputs.

.. spec:: Registry
    :id: HMD_APP_NEURONSPHERE_NERD012_SPEC002
    :links: HMD_APP_NEURONSPHERE_NERD012
    :status: implemented

    ``ns_mcp/gateway/registry.py`` asks ``find_resources_by_selector`` for the tag in each
    environment from ``list_environments``. It uses the service account, because the
    registry is global and is filtered per caller later. It groups the valid Resources by
    ``server_name``.

    ``MCP_GATEWAY_ENDPOINTS`` adds static endpoints for servers not deployed through
    NeuronSphere, in the form
    ``server@environment=url[;auth=service|passthrough][;cred=ref][;role=...]``. Where a
    static entry and a deployed Resource name the same server and environment, the
    deployed Resource wins.

    The result is cached for ``MCP_GATEWAY_REGISTRY_TTL`` seconds. A failed refresh keeps
    serving the last good result. An invalid Resource or entry, or an environment whose
    query fails, is logged and skipped. None of these stop the server starting.

    ``server_name`` and ``credential_ref`` are held to a safe alphabet. One becomes a tool
    prefix and the other a file name, so neither can carry a path.

.. spec:: Per-caller tools
    :id: HMD_APP_NEURONSPHERE_NERD012_SPEC003
    :links: HMD_APP_NEURONSPHERE_NERD012
    :status: implemented

    ``GatewayProvider`` is a FastMCP provider. FastMCP consults it inside every
    ``tools/list`` and ``tools/call``, with the caller's token in context, so both the
    tool list and every forwarded call are built for *that* caller. This is what removes
    SPEC014's single-identity limitation.

    For each logical server the caller can reach in at least one environment, every
    upstream tool is exposed once:

    - It is named ``<server_name>__<tool>``. The separator is set by
      ``MCP_GATEWAY_TOOL_SEPARATOR``.
    - It gains an ``environment`` argument whose ``enum`` lists the caller's permitted
      environments that host the tool. Where the upstream already has an ``environment``
      argument, the injected one is named ``ns_environment``.
    - When there is a single choice the argument is optional and defaults to it.
      Otherwise it is required.
    - A server is reachable in an environment when ``user_has_environment_access`` grants
      the endpoint's ``required_role``. A passthrough server is hidden from API-key
      callers, whose key cannot be forwarded.
    - Where environments run different versions, the newest one's schema is advertised.
      Upstream tool lists are cached per server and environment for
      ``MCP_GATEWAY_TOOLS_TTL`` seconds. An environment whose upstream cannot be listed is
      left out.

    On every call, ``GatewayTool.run`` **re-authorizes** the named environment with the
    same ``assert_environment_access`` the native tools use. The filtered ``enum`` is a
    convenience, not the control: a caller who sends ``prod`` regardless is refused before
    anything leaves the gateway.

    Every call, allowed or denied, writes an ``AuditLog`` row with ``transport:
    mcp-gateway``, the server, tool and environment, and the *names* of the arguments sent.
    Values are never recorded, since an upstream argument may be a query or a payload. The
    upstream's result, error results included, is passed through unchanged.

.. spec:: Upstream identity
    :id: HMD_APP_NEURONSPHERE_NERD012_SPEC004
    :links: HMD_APP_NEURONSPHERE_NERD012
    :status: implemented

    Each call opens its own Streamable HTTP client, which suits the stateless ``/mcp`` and
    means no session is shared between callers. The credential used depends on the
    server's ``auth_mode``:

    - ``service`` -- the gateway presents its own identity (SPEC007): a static bearer from
      ``MCP_GATEWAY_CREDENTIALS_DIR/<credential_ref>`` when the server names one, otherwise
      an access token the platform's IdP issued to the gateway's client. That directory is
      a mounted Kubernetes secret (``config.mcpGatewayCredentialsSecret``), one key per
      reference. A missing credential, or no credential source at all, is an error, never
      an anonymous call.
    - ``passthrough`` -- the caller's own SSO bearer is forwarded, so the upstream applies
      its own authorization to the user.
    - ``none`` -- identity headers only, for local fixtures. Only static configuration may
      choose it. A discovered Resource cannot, so a producer cannot opt its own server
      out of upstream authentication.

    Every forwarded request carries ``X-NS-User``, ``X-NS-Environment``, ``X-Request-Id``
    (the audit correlation id) and ``X-NS-Gateway-Hop``. A gateway that receives the hop
    header serves no gateway tools. That prevents a loop when two gateways point at each
    other, or one points at its own ``/mcp``.

    Upstream URLs are never shown to callers. Reaching an upstream directly would bypass
    the environment check, so the upstream must accept traffic only from the gateway
    (SPEC007).

.. spec:: Discovery surfaces
    :id: HMD_APP_NEURONSPHERE_NERD012_SPEC005
    :links: HMD_APP_NEURONSPHERE_NERD012
    :status: implemented

    - ``GET /mcp/registry/v0/servers`` and ``/mcp/registry/v0/servers/{name}`` answer in
      the MCP Registry v0 shape. They return one ``server.json`` entry per logical server,
      named ``io.neuronsphere/<server_name>``, whose single remote is this gateway's
      ``/mcp/``. The tool prefix and the caller's environments go under
      ``_meta["io.neuronsphere/gateway"]``. The routes sit beside the MCP endpoint and
      verify the bearer with the same auth provider. Results are filtered per caller, and
      a server the caller cannot reach answers 404, like one that does not exist.
    - The MCP tool ``list_mcp_servers`` returns the same listing from inside a session.
    - ``/health/`` reports ``mcp.gateway_enabled``.

.. spec:: Configuration and rollout
    :id: HMD_APP_NEURONSPHERE_NERD012_SPEC006
    :links: HMD_APP_NEURONSPHERE_NERD012
    :status: implemented

    The gateway is off by default (``MCP_GATEWAY_ENABLED``, chart
    ``config.mcpGatewayEnabled``). ``MCP_FEDERATION_ENABLED`` and
    ``MCP_FEDERATED_ENDPOINTS`` are still honoured as the pre-gateway names. Discovery can
    be switched off with ``MCP_GATEWAY_DISCOVERY_ENABLED`` to use static endpoints only.

    For local work and the acceptance suite, ``config.mcpGatewayEchoFixture`` runs
    ``python -m ns_mcp.gateway.echo`` as a sidecar. It is a credential-free upstream that
    reports back the environment it was routed as. The local config registers it as
    ``echo@dev`` and ``echo@test`` with ``auth=none``, and ``test/13_mcp_gateway.robot``
    drives it. It is also registered as ``locked@dev`` in ``service`` mode with no
    credential. The local deploy has no IdP client for the gateway, so the suite checks
    that ``locked`` is never called.

.. spec:: Upstream lockdown
    :id: HMD_APP_NEURONSPHERE_NERD012_SPEC007
    :links: HMD_APP_NEURONSPHERE_NERD012
    :status: implemented

    The gateway's environment check means nothing if a caller can reach an upstream
    directly. A ``service``-mode upstream therefore accepts only requests carrying a token
    the platform's IdP issued to the **gateway's own client**, for the upstream's **own
    environment**.

    *Tokens.* The gateway gets them with the OAuth client-credentials grant. It uses a
    machine client registered for the gateway alone (``MCP_GATEWAY_IDP_CLIENT_ID`` and
    ``_SECRET``, from the store secret named by ``config.mcpGatewayIdpSecret``), separate
    from the deployment service account. It requests the scope ``mcp:<environment>``
    (``MCP_GATEWAY_IDP_SCOPE``) and, when set, an ``audience``
    (``MCP_GATEWAY_IDP_AUDIENCE``; Auth0 needs one, Okta does not). The token endpoint
    comes from the issuer's OIDC metadata, and the issuer defaults to the SSO provider's.
    No Okta- or Auth0-specific code is involved. Tokens are cached per environment and
    replaced 60 seconds before they expire.

    *Verification at the upstream.* Every environment shares one IdP tenant, so every
    user's own token also verifies against the tenant's keys. A valid signature is
    therefore not enough. The upstream, or a verifying proxy in front of it, must check
    all of:

    - ``iss`` is the tenant's issuer, and the signature verifies against its JWKS
    - ``aud`` is the MCP audience
    - the client is the gateway's (Okta ``cid``; Auth0 ``azp``)
    - the scopes (Okta ``scp``; Auth0 ``scope``) include ``mcp:<this environment>``
    - the token has not expired

    The client check is what shuts out users. A dedicated audience such as
    ``api://neuronsphere-mcp`` keeps the gateway's tokens and users' tokens from being
    exchanged for each other. The environment scope keeps a token issued for dev from
    opening prod.

    *What the token does not carry.* It names the gateway, not the caller, and lives as
    long as the IdP's access-token lifetime. The caller travels in ``X-NS-User``, which an
    upstream can trust only because the token proves the request came from the gateway.

    *Network policy is a second layer.* Where an upstream shares a cluster with the GUI,
    it should be ClusterIP-only, with a NetworkPolicy that admits only the GUI's pods. That
    cannot be the only control, because environments may sit in other clusters and
    ``hmd-ms-*`` services run behind ``hmd_proxy``.

    ``passthrough`` servers cannot be locked down this way: a dev-only user's own token is
    as valid at prod as at dev. Use ``passthrough`` only for upstreams that enforce their
    own per-user authorization.

Out of scope here, and next:

- a verifying proxy (sidecar) for third-party upstreams, packaged once and reused by
  Trino and ClickHouse
- an MCP server producer for Trino (``hmd-inf-trino``), then ClickHouse
- ``HMD_MS_BASE_NERD001``, so that ``hmd-ms-*`` services publish an mcp-server Resource
  and verify the gateway's token without any extra work
