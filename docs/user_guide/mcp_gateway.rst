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

Publishing a server (platform engineers)
----------------------------------------

To make a deployed MCP server available through the gateway:

1. Have the deployment emit a Resource of definition ``mcp.neuronsphere.io/mcp-server``
   in its ``resource-outputs.yaml``, tagged ``mcp.neuronsphere.io/kind=mcp-server``. Its
   output needs at least ``server_name`` (the same name in every environment) and
   ``url``.
2. If the server needs a credential from the gateway, add it to the GUI's
   upstream-credentials secret (``config.mcpGatewayCredentialsSecret``) and name its key
   in ``credential_ref``. To have the gateway forward the caller's own SSO token instead,
   set ``auth_mode: passthrough``.
3. To require deploy rights rather than view rights, set ``required_role: deployer``.

Turn the gateway on with ``config.mcpGatewayEnabled: "true"``. Servers that are not
deployed through NeuronSphere can be added with ``config.mcpGatewayEndpoints``
(``server@environment=url;auth=...;cred=...``). See NERD012 for the full design.
