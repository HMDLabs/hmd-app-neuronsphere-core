"""MCP (Model Context Protocol) transport for the NeuronSphere Deployment GUI.

A read-only MCP server mounted alongside the Django app at ``/mcp`` (see
``deployment_gui/asgi.py``). Tools are thin adapters: they resolve the caller,
authorize the environment, and delegate to ``deployments.services`` -- the same
functions the GUI views call, so the two surfaces cannot drift.

This is a plain package rather than a Django app: it defines no models,
templates, or migrations. ``MCPApiKey`` lives in ``deployments.models`` with the
other GUI-local state.

Shape follows HMD_MS_BASE_NERD001 (single /mcp endpoint over Streamable HTTP,
Okta bearer or platform API key) so this server and the future hmd-ms-base
transport are the same protocol surface.
"""
