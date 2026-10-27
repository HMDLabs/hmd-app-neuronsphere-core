MCP Servers Through the Gateway
===============================

The GUI's MCP endpoint (``/mcp``) is also a gateway to the other MCP servers
NeuronSphere hosts, such as query engines (Trino, ClickHouse) and internal services. You
connect once, to the GUI, and every server you are allowed to use is there.

Connecting
----------

Point your MCP client at ``https://<gui-host>/mcp/`` with your bearer token. For example,
with Claude Code:

.. code-block:: bash

    claude mcp add --transport http neuronsphere https://<gui-host>/mcp/ \
        --header "Authorization: Bearer <token>"

Locally, use ``http://localhost:19003/mcp/`` and the ``nsmcp_`` key printed by
``hmd neuronsphere up``.

One server, many environments
-----------------------------

A server deployed in several environments appears **once**. Its tools are named
``<server>__<tool>``, for example ``trino__query``, and each one takes an
``environment`` argument:

- Its allowed values are the environments you may use, and only those. If you have
  access to dev alone, ``dev`` is the only value offered.
- If you have only one choice you can leave the argument out.
- A call naming an environment you cannot use is refused and recorded in the audit log.
  The upstream server never sees it.

If the upstream tool already has an argument called ``environment``, the gateway's
argument is called ``ns_environment`` instead.

Finding servers
---------------

- Call the ``list_mcp_servers`` tool for the servers you can reach, the tool prefix of
  each, and your environments for each.
- Registry-aware clients can browse ``GET /mcp/registry/v0/servers`` (same bearer). It
  answers in the official MCP Registry ``server.json`` format.
- A server listed with none of its ``<server>__*`` tools has ``tools_unavailable`` on
  each deployment the gateway cannot use, saying why: for example a service-mode
  server with no gateway credential (no ``credential_ref`` and no
  ``config.mcpGatewayIdpSecret``), or an upstream whose ``tools/list`` failed.

Publishing a server (platform engineers)
----------------------------------------

To make a deployed MCP server available through the gateway:

1. Have the deployment emit a Resource of definition ``mcp.neuronsphere.io/mcp-server``
   in its ``resource-outputs.yaml``, tagged ``mcp.neuronsphere.io/kind=mcp-server``. Its
   output needs at least ``server_name`` (the same name in every environment) and
   ``url``.
2. Leave ``auth_mode`` at its default, ``service``. The gateway then calls the server
   with a token from the platform's identity provider (see `Locking down an upstream`_),
   and the server must accept nothing else. For a server outside the platform's IdP,
   add a static credential to the GUI's upstream-credentials secret
   (``config.mcpGatewayCredentialsSecret``) and name its key in ``credential_ref``. To
   have the gateway forward the caller's own SSO token instead, set
   ``auth_mode: passthrough``, but only for a server that enforces its own per-user
   permissions.
3. To require deploy rights rather than view rights, set ``required_role: deployer``.

Turn the gateway on with ``config.mcpGatewayEnabled: "true"``. Servers that are not
deployed through NeuronSphere can be added with ``config.mcpGatewayEndpoints``
(``server@environment=url;auth=...;cred=...``). See NERD012 for the full design.

Discovery needs the deployment service account
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The gateway finds ``mcp-server`` Resources by querying the deployment service as the
GUI's own service account, not as the caller. With ``config.oktaAuth`` on, the GUI's
CDKTF stack creates that account as an Okta service app for the instance, and the
chart syncs ``SERVICE_CLIENT_ID``, ``SERVICE_CLIENT_SECRET`` and
``SERVICE_TOKEN_ISSUER`` into the pod from its secret,
``okta-<instance>-<repo>-<deployment id>``. The issuer is the Okta
``services_issuer``, because the deployment service checks any token that is not from
a trusted human client against that issuer and the ``api://neuronsphere-services``
audience.

If the pod has no service-account token, for example before the stack has created the
app, the gateway skips discovery, logs ``MCP server discovery skipped: no
service-account token``, and serves only ``config.mcpGatewayEndpoints``. ``list_mcp_servers`` stays empty even though the
Resources exist. A per-environment ``MCP server discovery failed ... Unauthorized``
warning instead means a token was sent but refused. Check that its client belongs to
``services_issuer``.

Locking down an upstream
------------------------

The gateway checks each caller's environment permissions, so an upstream that callers
could reach directly would bypass that check. Each ``service``-mode upstream must accept
only tokens the identity provider issued to the gateway, for that upstream's
environment. If the gateway has no way to get such a token, it refuses the call rather
than calling anonymously.

Every environment shares one IdP tenant, so every user's own token verifies against
the same keys. **Checking the signature alone lets every user in.** The client and scope
checks below are what keep users out.

Set up the gateway's client
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Register a machine-to-machine client for the gateway alone, separate from the GUI's
deployment service account, and give it one scope per environment: ``mcp:dev``,
``mcp:test``, ``mcp:prod``, and so on.

**Okta**

1. Under *Security > API > Authorization Servers*, choose the custom authorization
   server to issue the tokens. Client credentials with custom scopes need a custom
   authorization server (Okta's API Access Management). A server of its own, with an
   audience such as ``api://neuronsphere-mcp``, keeps these tokens apart from users'.
2. On its *Scopes* tab, add ``mcp:<environment>`` for each environment.
3. Under *Applications*, create an *API Services* app integration for the gateway, and
   note its client ID and secret.
4. On the authorization server's *Access Policies* tab, add a policy assigned to that
   client, with a rule that allows the *Client Credentials* grant and the ``mcp:*``
   scopes.
5. If this authorization server is not the one the GUI signs users in with, set
   ``config.mcpGatewayIdpIssuer`` to its issuer
   (``https://<org>.okta.com/oauth2/<server-id>``).

The tokens carry the client ID in ``cid`` and the scopes in ``scp``.

**Auth0**

1. Under *Applications > APIs*, create an API whose identifier is the audience, for
   example ``api://neuronsphere-mcp``. On its *Permissions* tab, add
   ``mcp:<environment>`` for each environment.
2. Create a *Machine to Machine* application for the gateway, authorize it for that API,
   and grant it the ``mcp:*`` permissions.
3. Set ``config.mcpGatewayIdpAudience`` to the API identifier. Auth0 picks the API by
   that parameter.

The tokens carry the client ID in ``azp`` and the scopes in ``scope``. Auth0 counts
machine-to-machine tokens against a monthly quota on some plans. The gateway caches one
token per environment until shortly before it expires, so it requests only a handful an
hour.

**Then, for either provider**, store the client's credentials in the secret store as a
secret with ``client_id`` and ``client_secret`` properties. Set
``config.mcpGatewayIdpSecret`` to that secret's name. The GUI finds the token endpoint
from the issuer's OIDC metadata. Set ``config.mcpGatewayIdpTokenUrl`` only to override it,
and ``config.mcpGatewayIdpScope`` only if your scopes are not named
``mcp:{environment}``.

Verify the token at the upstream
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The upstream, or a verifying proxy in front of it, must check all of these on every
request:

- the signature, against the tenant's JWKS, and ``iss`` is the tenant's issuer
- ``aud`` is the MCP audience
- the client is the gateway's (Okta ``cid``, Auth0 ``azp``)
- the scopes include ``mcp:<this environment>``, so a token issued for dev does not
  open prod
- ``exp`` has not passed

The token names the gateway, not the caller. The caller is in the ``X-NS-User`` header,
which the upstream can trust only because the token proves the request came through the
gateway.

Where the upstream shares a cluster with the GUI, also give it a ClusterIP service with
no ingress, and a NetworkPolicy that admits only the GUI's pods.
