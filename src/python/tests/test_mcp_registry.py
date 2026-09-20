"""Structural guards over the MCP tool surface.

These tests are the reason the ``@read_tool`` decorator owns authorization
rather than each tool body: a new tool that forgets its environment check should
fail here, not in production. They deliberately assert invariants over whatever
is registered, so they keep working as tools are added.
"""
import inspect
import unittest

from ns_mcp.tooling import ENVIRONMENT_ARG_ATTR, environment_args, read_tool


class _FakeMCP:
    """Records what a module registers, without needing a FastMCP server."""

    def __init__(self):
        self.tools = {}
        self.resources = {}
        self.prompts = {}

    def tool(self, fn=None, *, name=None, description=None, **kwargs):
        self.tools[name or fn.__name__] = {
            "fn": fn,
            "description": description,
            "kwargs": kwargs,
        }
        return fn

    def resource(self, uri, *, name=None, description=None, **kwargs):
        # FastMCP's resource() is a decorator factory, so the seam calls it as
        # mcp.resource(uri, ...)(fn) -- mirror that shape here.
        def decorate(fn):
            self.resources[uri] = {
                "fn": fn,
                "name": name,
                "description": description,
                "kwargs": kwargs,
            }
            return fn

        return decorate

    def prompt(self, fn=None, *, name=None, description=None, **kwargs):
        self.prompts[name or fn.__name__] = {
            "fn": fn,
            "description": description,
            "kwargs": kwargs,
        }
        return fn


def _load_registered_tools():
    """Register every module the settings default lists, against a fake server.

    Driven off ``settings.MCP_TOOL_MODULES`` rather than a hardcoded import so
    that adding a tool module automatically brings it under the invariants
    below -- a new module that skipped its permission check would otherwise
    simply not be looked at.
    """
    from django.conf import settings

    from ns_mcp.registry import register_tool_modules

    mcp = _FakeMCP()
    registered = register_tool_modules(mcp, settings.MCP_TOOL_MODULES)
    return mcp, [n for names in registered.values() for n in names]


def _load_registered_resources():
    """Same, for the resource modules in ``settings.MCP_RESOURCE_MODULES``."""
    from django.conf import settings

    from ns_mcp.registry import register_resource_modules

    mcp = _FakeMCP()
    registered = register_resource_modules(mcp, settings.MCP_RESOURCE_MODULES)
    return mcp, [n for names in registered.values() for n in names]


def _load_registered_prompts():
    """Same, for the prompt modules in ``settings.MCP_PROMPT_MODULES``."""
    from django.conf import settings

    from ns_mcp.registry import register_prompt_modules

    mcp = _FakeMCP()
    registered = register_prompt_modules(mcp, settings.MCP_PROMPT_MODULES)
    return mcp, [n for names in registered.values() for n in names]


class TestRegistrationContract(unittest.TestCase):
    def test_register_returns_the_names_it_registered(self):
        mcp, names = _load_registered_tools()
        self.assertEqual(sorted(names), sorted(mcp.tools))

    def test_every_tool_has_a_nonempty_description(self):
        mcp, _ = _load_registered_tools()
        for name, entry in mcp.tools.items():
            with self.subTest(tool=name):
                self.assertTrue(
                    (entry["description"] or "").strip(),
                    f"{name} must describe itself; the model selects tools on this",
                )

    def test_duplicate_registration_is_rejected(self):
        from ns_mcp.registry import register_tool_modules

        with self.assertRaises(ValueError) as ctx:
            register_tool_modules(
                _FakeMCP(),
                ["ns_mcp.tools.environments", "ns_mcp.tools.environments"],
            )
        self.assertIn("list_environments", str(ctx.exception))

    def test_module_without_register_is_rejected(self):
        from ns_mcp.registry import register_tool_modules

        with self.assertRaises(TypeError):
            register_tool_modules(_FakeMCP(), ["ns_mcp.context"])


class TestResourceAndPromptContract(unittest.TestCase):
    """Resources and prompts register through the same seam as tools."""

    def test_resources_return_the_uris_they_registered(self):
        mcp, uris = _load_registered_resources()
        self.assertEqual(sorted(uris), sorted(mcp.resources))
        self.assertTrue(uris)

    def test_every_resource_uri_is_in_the_platform_scheme(self):
        _, uris = _load_registered_resources()
        for uri in uris:
            with self.subTest(uri=uri):
                self.assertTrue(uri.startswith("neuronsphere://"), uri)

    def test_every_resource_has_a_nonempty_description(self):
        mcp, _ = _load_registered_resources()
        for uri, entry in mcp.resources.items():
            with self.subTest(uri=uri):
                self.assertTrue((entry["description"] or "").strip())

    def test_templated_resources_declare_their_uri_parameters(self):
        """A placeholder with no matching parameter is a resource that cannot
        be read -- FastMCP resolves the template off the signature."""
        import re

        mcp, _ = _load_registered_resources()
        for uri, entry in mcp.resources.items():
            placeholders = set(re.findall(r"{(\w+)}", uri))
            params = set(inspect.signature(entry["fn"]).parameters)
            with self.subTest(uri=uri):
                self.assertEqual(placeholders - params, set())

    def test_prompts_return_the_names_they_registered(self):
        mcp, names = _load_registered_prompts()
        self.assertEqual(sorted(names), sorted(mcp.prompts))
        self.assertTrue(names)

    def test_every_prompt_has_a_nonempty_description(self):
        mcp, _ = _load_registered_prompts()
        for name, entry in mcp.prompts.items():
            with self.subTest(prompt=name):
                self.assertTrue((entry["description"] or "").strip())

    def test_prompts_take_no_context_and_return_text(self):
        """Prompts hold no credentials and read nothing, so unlike tools and
        resources they are not wrapped in @read_tool."""
        mcp, _ = _load_registered_prompts()
        for name, entry in mcp.prompts.items():
            with self.subTest(prompt=name):
                params = inspect.signature(entry["fn"]).parameters
                self.assertNotIn("ctx", params)
                rendered = entry["fn"](**{p: "x" for p in params})
                self.assertIsInstance(rendered, str)
                self.assertTrue(rendered.strip())


class TestAuthorizationIsStructural(unittest.TestCase):
    """The invariant that stops the GUI's ?environment= gap being inherited."""

    def _assert_environment_params_are_declared(self, kind, entries):
        """Every environment-naming parameter must be one @read_tool checks.

        Matching on a trailing ``_environment`` as well as the bare name is
        what brings the two-environment tools (compare_environments) under the
        invariant: checking only ``environment`` would let them past unlooked-at,
        which is precisely the gap this test exists to close.
        """
        for name, entry in entries.items():
            fn = entry["fn"]
            params = [
                p
                for p in inspect.signature(fn).parameters
                if p == "environment" or p.endswith("_environment")
            ]
            if not params:
                continue
            declared = set(environment_args(fn))
            for param in params:
                with self.subTest(**{kind: name, "parameter": param}):
                    self.assertIn(
                        param,
                        declared,
                        f"{name} accepts '{param}' but does not declare it to "
                        f"@read_tool, so it would read that environment "
                        f"without a permission check",
                    )

    def test_every_tool_taking_an_environment_authorizes_on_it(self):
        mcp, _ = _load_registered_tools()
        self._assert_environment_params_are_declared("tool", mcp.tools)

    def test_every_resource_taking_an_environment_authorizes_on_it(self):
        """Resources are reads too, and go through the same decorator."""
        mcp, _ = _load_registered_resources()
        self._assert_environment_params_are_declared("resource", mcp.resources)

    def test_tools_expose_no_context_parameter(self):
        # ToolContext is injected by the decorator; if it leaked into the
        # signature it would appear in the MCP input schema as a required arg.
        mcp, _ = _load_registered_tools()
        for name, entry in mcp.tools.items():
            with self.subTest(tool=name):
                self.assertNotIn("ctx", inspect.signature(entry["fn"]).parameters)

    def test_decorator_requires_a_context_parameter(self):
        with self.assertRaises(TypeError):
            read_tool(action="x")(lambda: None)

    def test_a_tuple_of_environment_args_is_normalized(self):
        @read_tool(action="x", environment_arg=("from_environment", "to_environment"))
        def sample(ctx, from_environment: str, to_environment: str) -> dict:
            return {}

        self.assertEqual(
            environment_args(sample), ("from_environment", "to_environment")
        )

    def test_a_tool_declaring_nothing_has_no_environment_args(self):
        @read_tool(action="x")
        def sample(ctx) -> dict:
            return {}

        self.assertEqual(environment_args(sample), ())

    def test_decorator_strips_only_the_first_parameter(self):
        @read_tool(action="x", environment_arg="environment")
        def sample(ctx, environment: str, limit: int = 10) -> dict:
            return {}

        params = inspect.signature(sample).parameters
        self.assertEqual(list(params), ["environment", "limit"])
        self.assertEqual(getattr(sample, ENVIRONMENT_ARG_ATTR), "environment")


if __name__ == "__main__":
    unittest.main()
