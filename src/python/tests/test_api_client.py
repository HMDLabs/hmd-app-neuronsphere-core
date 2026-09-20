"""Unit tests for DeploymentAPIClient ChangeSet/DeploymentSet methods.

Avoids a live HTTP call by patching `_make_request` on an instance after
construction. Django settings are stubbed via `settings.configure(...)` before
importing the client, for the case where this module is run on its own; when the
suite runs as a whole, `tests/conftest.py` has already configured Django, so
tests assert against `settings.*` rather than a hardcoded number -- otherwise
they would silently depend on which configuration happened to win.
"""
import os
import sys
import unittest

try:
    import django
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            DEBUG=False,
            DEPLOYMENT_API_URL="http://api.test",
            DEPLOYMENT_API_TIMEOUT=5,
            DEPLOYMENT_API_CACHE_TTL=10,
            DEPLOYMENT_BOM_CACHE_TTL=1234,
            CACHES={
                "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
            },
            INSTALLED_APPS=[],
        )
        django.setup()

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from deployments.services.api_client import (  # noqa: E402
        APIResponse,
        DeploymentAPIClient,
        _encode_collection,
    )

    _DJANGO_AVAILABLE = True
except ImportError:
    _DJANGO_AVAILABLE = False


@unittest.skipUnless(_DJANGO_AVAILABLE, "Django not installed in this environment")
class _Base(unittest.TestCase):
    pass


class TestSaveChangeset(_Base):
    """``save_changeset`` searches by name first, then PUTs.

    Without the find step, a second save with the same name collides on the
    ``business_id`` and 500s — see the find-then-upsert change in api_client.
    """

    _DEFINITION = [
        {
            "repo_instance_name": "x",
            "repo_class_name": "rc",
            "repo_class_version": "1",
            "deployment_id": "aaa",
        }
    ]

    def _capture(self, search_result):
        calls = []

        def fake(method, endpoint, params=None, json_data=None, cache_key=None):
            calls.append(
                {
                    "method": method,
                    "endpoint": endpoint,
                    "json_data": json_data,
                    "cache_key": cache_key,
                }
            )
            # First call is the search; subsequent the PUT.
            if len(calls) == 1:
                return search_result
            return APIResponse(success=True, data={})

        return calls, fake

    def test_creates_when_no_existing_changeset(self):
        client = DeploymentAPIClient()
        calls, fake = self._capture(APIResponse(success=True, data=[]))
        client._make_request = fake

        result = client.save_changeset("my-cs", self._DEFINITION)

        self.assertTrue(result.success)
        self.assertEqual(len(calls), 2)

        search = calls[0]
        self.assertEqual(search["method"], "POST")
        self.assertEqual(search["endpoint"], "/api/hmd_lang_deployment.change_set")
        self.assertEqual(
            search["json_data"],
            {"attribute": "name", "operator": "=", "value": "my-cs"},
        )

        put = calls[1]
        self.assertEqual(put["method"], "PUT")
        self.assertEqual(put["endpoint"], "/api/hmd_lang_deployment.change_set")
        self.assertEqual(
            put["json_data"],
            {
                "name": "my-cs",
                "definition": _encode_collection(self._DEFINITION),
            },
        )
        self.assertNotIn("identifier", put["json_data"])

    def test_updates_when_existing_changeset(self):
        client = DeploymentAPIClient()
        calls, fake = self._capture(
            APIResponse(success=True, data=[{"identifier": "cs-123", "name": "my-cs"}])
        )
        client._make_request = fake

        result = client.save_changeset("my-cs", self._DEFINITION)

        self.assertTrue(result.success)
        self.assertEqual(len(calls), 2)
        put = calls[1]
        self.assertEqual(put["method"], "PUT")
        self.assertEqual(
            put["json_data"],
            {
                "name": "my-cs",
                "definition": _encode_collection(self._DEFINITION),
                "identifier": "cs-123",
            },
        )

    def test_returns_search_failure_without_putting(self):
        client = DeploymentAPIClient()
        calls, fake = self._capture(
            APIResponse(success=False, data=None, error="boom", status_code=500)
        )
        client._make_request = fake

        result = client.save_changeset("my-cs", self._DEFINITION)

        self.assertFalse(result.success)
        self.assertEqual(result.error, "boom")
        self.assertEqual(len(calls), 1)


class TestListDeploymentSets(_Base):
    def test_posts_with_no_op_filter_and_caches(self):
        client = DeploymentAPIClient()
        captured = {}

        def fake(method, endpoint, params=None, json_data=None, cache_key=None):
            captured.update(
                method=method,
                endpoint=endpoint,
                json_data=json_data,
                cache_key=cache_key,
            )
            return APIResponse(success=True, data=[])

        client._make_request = fake
        result = client.list_deployment_sets()

        self.assertTrue(result.success)
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(
            captured["endpoint"], "/api/hmd_lang_deployment.deployment_set"
        )
        self.assertEqual(
            captured["json_data"],
            {"attribute": "name", "operator": "!=", "value": "__none__"},
        )
        self.assertEqual(captured["cache_key"], "deployment_sets:all")


class TestGetDeploymentBom(_Base):
    def test_uses_bom_cache_key_and_ttl(self):
        client = DeploymentAPIClient()
        captured = {}

        def fake(
            method,
            endpoint,
            params=None,
            json_data=None,
            cache_key=None,
            cache_ttl=None,
        ):
            captured.update(
                method=method,
                endpoint=endpoint,
                cache_key=cache_key,
                cache_ttl=cache_ttl,
            )
            return APIResponse(success=True, data=[])

        client._make_request = fake
        result = client.get_deployment_bom("dev")

        self.assertTrue(result.success)
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["endpoint"], "/apiop/get_deployment_bom/dev")
        self.assertEqual(captured["cache_key"], "bom:dev")
        # BOM TTL is the configured backstop, not the default API TTL.
        self.assertEqual(captured["cache_ttl"], settings.DEPLOYMENT_BOM_CACHE_TTL)
        self.assertEqual(client.bom_cache_ttl, settings.DEPLOYMENT_BOM_CACHE_TTL)
        self.assertNotEqual(
            client.bom_cache_ttl,
            settings.DEPLOYMENT_API_CACHE_TTL,
            "the BOM must not fall back to the short default API TTL",
        )

    def test_second_call_served_from_cache_without_http(self):
        from django.core.cache import cache

        cache.delete("bom:dev")
        cache.set("bom:dev", [{"repo_instance_name": "x"}], 100)
        client = DeploymentAPIClient()

        # If this reached httpx it would fail (no server); a cache hit returns first.
        result = client.get_deployment_bom("dev")

        self.assertTrue(result.success)
        self.assertEqual(result.data, [{"repo_instance_name": "x"}])
        cache.delete("bom:dev")


class TestInvalidateBomCache(_Base):
    def test_deletes_bom_key(self):
        from django.core.cache import cache

        cache.set("bom:prod", [{"a": 1}], 100)
        client = DeploymentAPIClient()
        client.invalidate_bom_cache("prod")

        self.assertIsNone(cache.get("bom:prod"))

    def test_deletes_bom_dag_key(self):
        from django.core.cache import cache

        cache.set("bom_dag:prod", {"nodes": [], "edges": []}, 100)
        client = DeploymentAPIClient()
        client.invalidate_bom_cache("prod")

        self.assertIsNone(cache.get("bom_dag:prod"))


class _CaptureMixin:
    """Patch ``_make_request`` and capture the single call's arguments."""

    def _capture(self, client, data=None):
        captured = {}

        def fake(
            method,
            endpoint,
            params=None,
            json_data=None,
            cache_key=None,
            cache_ttl=None,
        ):
            captured.update(
                method=method,
                endpoint=endpoint,
                params=params,
                json_data=json_data,
                cache_key=cache_key,
                cache_ttl=cache_ttl,
            )
            return APIResponse(success=True, data=data if data is not None else [])

        client._make_request = fake
        return captured


class TestListResourceDefinitions(_Base, _CaptureMixin):
    def test_lists_all_and_caches(self):
        client = DeploymentAPIClient()
        captured = self._capture(client)

        result = client.list_resource_definitions()

        self.assertTrue(result.success)
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["endpoint"], "/apiop/list_resource_definitions")
        self.assertIsNone(captured["params"])
        self.assertEqual(captured["cache_key"], "resource_defs:all")

    def test_filters_by_namespace_and_scopes_cache_key(self):
        client = DeploymentAPIClient()
        captured = self._capture(client)

        client.list_resource_definitions(
            resource_namespace="kubernetes.neuronsphere.io"
        )

        self.assertEqual(
            captured["params"],
            {"resource_namespace": "kubernetes.neuronsphere.io"},
        )
        self.assertEqual(
            captured["cache_key"], "resource_defs:kubernetes.neuronsphere.io"
        )


class TestGetResourceDefinition(_Base, _CaptureMixin):
    def test_path_and_cache_key(self):
        client = DeploymentAPIClient()
        captured = self._capture(client, data={})
        client.get_resource_definition("rd-1")
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["endpoint"], "/apiop/get_resource_definition/rd-1")
        self.assertEqual(captured["cache_key"], "resource_def:rd-1")


class TestGetResourceDefinitionAncestry(_Base, _CaptureMixin):
    def test_path_and_cache_key(self):
        client = DeploymentAPIClient()
        captured = self._capture(client)
        client.get_resource_definition_ancestry("rd-1")
        self.assertEqual(
            captured["endpoint"], "/apiop/get_resource_definition_ancestry/rd-1"
        )
        self.assertEqual(captured["cache_key"], "resource_def_ancestry:rd-1")


class TestGetEffectiveOutputSchema(_Base, _CaptureMixin):
    def test_path_and_cache_key(self):
        client = DeploymentAPIClient()
        captured = self._capture(client, data={})
        client.get_effective_output_schema("rd-1")
        self.assertEqual(
            captured["endpoint"], "/apiop/get_effective_output_schema/rd-1"
        )
        self.assertEqual(captured["cache_key"], "resource_def_schema:rd-1")


class TestGetProducers(_Base, _CaptureMixin):
    def test_omits_include_subtypes_by_default(self):
        client = DeploymentAPIClient()
        captured = self._capture(client)
        client.get_producers("rd-1")
        self.assertEqual(captured["endpoint"], "/apiop/get_producers/rd-1")
        self.assertIsNone(captured["params"])
        # Live producer set — never cached.
        self.assertIsNone(captured["cache_key"])

    def test_includes_subtypes_when_requested(self):
        client = DeploymentAPIClient()
        captured = self._capture(client)
        client.get_producers("rd-1", include_subtypes=True)
        self.assertEqual(captured["params"], {"include_subtypes": "true"})


class TestGetDeploymentResources(_Base, _CaptureMixin):
    def test_path_and_no_cache(self):
        client = DeploymentAPIClient()
        captured = self._capture(client)
        client.get_deployment_resources("rid-9")
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["endpoint"], "/apiop/get_deployment_resources/rid-9")
        self.assertIsNone(captured["cache_key"])


class TestFindResourcesByTag(_Base, _CaptureMixin):
    def test_path(self):
        client = DeploymentAPIClient()
        captured = self._capture(client)
        client.find_resources_by_tag("tier", "prod")
        self.assertEqual(captured["endpoint"], "/apiop/find_resources_by_tag/tier/prod")
        self.assertIsNone(captured["cache_key"])

    def test_environment_is_sent_as_a_query_param(self):
        client = DeploymentAPIClient()
        captured = self._capture(client)
        client.find_resources_by_tag("tier", "prod", environment="dev")
        self.assertEqual(captured["params"], {"environment": "dev"})


class TestFindResourcesBySelector(_Base, _CaptureMixin):
    def test_serializes_tags_to_query_string(self):
        client = DeploymentAPIClient()
        captured = self._capture(client)
        client.find_resources_by_selector({"tier": "prod", "region": "us-west-2"})
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["endpoint"], "/apiop/find_resources_by_selector")
        # Backend parses a comma-joined key=value string from the ``tags`` query param.
        self.assertEqual(captured["params"], {"tags": "tier=prod,region=us-west-2"})
        # Query string, not a JSON body — never base64-encoded.
        self.assertIsNone(captured["json_data"])

    def test_environment_narrows_the_selector(self):
        client = DeploymentAPIClient()
        captured = self._capture(client)
        client.find_resources_by_selector({"tier": "prod"}, environment="dev")
        self.assertEqual(
            captured["params"], {"tags": "tier=prod", "environment": "dev"}
        )


class TestListResources(_Base, _CaptureMixin):
    def test_defaults_to_an_unscoped_first_page(self):
        client = DeploymentAPIClient()
        captured = self._capture(client, data={"items": [], "total": 0})
        client.list_resources()
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["endpoint"], "/apiop/list_resources")
        self.assertEqual(captured["params"], {"limit": 50, "offset": 0})
        # Live deployment state — never cached.
        self.assertIsNone(captured["cache_key"])

    def test_environment_and_window_are_sent_as_query_params(self):
        client = DeploymentAPIClient()
        captured = self._capture(client, data={"items": [], "total": 0})
        client.list_resources(limit=25, offset=50, environment="dev")
        self.assertEqual(
            captured["params"], {"limit": 25, "offset": 50, "environment": "dev"}
        )


class TestSuggestResourceDependencies(_Base, _CaptureMixin):
    def test_repo_class_version_id_mode(self):
        client = DeploymentAPIClient()
        captured = self._capture(client, data={})
        client.suggest_resource_dependencies("dev", repo_class_version_id="rcv-1")
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(
            captured["endpoint"], "/apiop/suggest_resource_dependencies/dev"
        )
        self.assertEqual(captured["params"], {"repo_class_version_id": "rcv-1"})
        self.assertIsNone(captured["cache_key"])

    def test_ad_hoc_mode_includes_only_non_none_params(self):
        client = DeploymentAPIClient()
        captured = self._capture(client, data={})
        client.suggest_resource_dependencies(
            "dev",
            resource_namespace="kubernetes.neuronsphere.io",
            resource_definition_name="kubernetes-cluster",
            version="0.1",
            version_spec="~= 0.1",
        )
        self.assertEqual(
            captured["params"],
            {
                "resource_namespace": "kubernetes.neuronsphere.io",
                "resource_definition_name": "kubernetes-cluster",
                "version": "0.1",
                "version_spec": "~= 0.1",
            },
        )
        self.assertNotIn("tags", captured["params"])
        self.assertNotIn("repo_class_version_id", captured["params"])


class TestFindRepoClassVersionsPage(_Base, _CaptureMixin):
    def test_posts_with_pagination_params_skips_deps_and_caches(self):
        client = DeploymentAPIClient()
        captured = self._capture(client, data={"items": [], "total": 0})

        result = client.find_repo_class_versions_page(
            "hmd-ms-test", q="1.1", limit=25, offset=50
        )

        self.assertTrue(result.success)
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(
            captured["endpoint"], "/apiop/find_repo_class_versions/hmd-ms-test"
        )
        # include_deps=false is always sent so the picker never pays for the
        # microservice's per-version dependency resolution.
        self.assertEqual(
            captured["params"],
            {"limit": 25, "offset": 50, "include_deps": "false", "q": "1.1"},
        )
        # Cache key is scoped by (name, q, limit, offset) so paging/typing hits
        # distinct entries.
        self.assertEqual(captured["cache_key"], "versions:hmd-ms-test:1.1:25:50")

    def test_omits_q_param_when_blank(self):
        client = DeploymentAPIClient()
        captured = self._capture(client, data={"items": [], "total": 0})

        client.find_repo_class_versions_page("hmd-ms-test")

        self.assertNotIn("q", captured["params"])
        self.assertEqual(
            captured["params"],
            {"limit": 50, "offset": 0, "include_deps": "false"},
        )
        self.assertEqual(captured["cache_key"], "versions:hmd-ms-test::50:0")


class TestSearchDiscovery(_Base, _CaptureMixin):
    """``search_discovery`` -> GET /apiop/search_discovery (NERD0013 SPEC0002)."""

    def test_sends_only_the_filters_that_are_set_and_caches(self):
        client = DeploymentAPIClient()
        captured = self._capture(client, data={"items": [], "total": 0})

        result = client.search_discovery(
            q="rotate logs", kind="cli_command", limit=25, offset=50
        )

        self.assertTrue(result.success)
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["endpoint"], "/apiop/search_discovery")
        self.assertEqual(
            captured["params"],
            {"q": "rotate logs", "kind": "cli_command", "limit": 25, "offset": 50},
        )
        self.assertEqual(
            captured["cache_key"], "discovery:rotate logs:cli_command::25:50"
        )

    def test_prefix_filter_and_defaults(self):
        client = DeploymentAPIClient()
        captured = self._capture(client, data={"items": [], "total": 0})

        client.search_discovery(repo_class_name="hmd-ms-")

        self.assertEqual(
            captured["params"],
            {"repo_class_name": "hmd-ms-", "limit": 50, "offset": 0},
        )
        self.assertNotIn("q", captured["params"])
        self.assertNotIn("kind", captured["params"])
        self.assertEqual(captured["cache_key"], "discovery:::hmd-ms-:50:0")


if __name__ == "__main__":
    unittest.main()
