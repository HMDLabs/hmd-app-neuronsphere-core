"""The MCP gateway: every NeuronSphere-hosted MCP server behind ``/mcp`` (NERD012).

* ``registry`` -- which servers exist and in which environments, from
  ``mcp.neuronsphere.io/mcp-server`` Resources plus ``MCP_GATEWAY_ENDPOINTS``.
* ``provider`` -- their tools, one logical server each, with an ``environment``
  argument limited to what the caller may use, re-authorized on every call.
* ``upstream`` -- how a call is forwarded and with whose credential.
* ``catalog`` -- the same registry as an MCP-Registry-shaped HTTP listing.
"""
