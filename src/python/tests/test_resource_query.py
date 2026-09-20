"""Unit tests for the resource query helpers extracted from ``resource_list``."""
import json
import unittest
from base64 import b64encode

from deployments.services.repo_class_detail import search_repo_classes
from deployments.services.resource_query import (
    decode_resource_output,
    decode_resource_outputs,
    parse_tag_selector,
    query_resources,
    resolve_resource_definition,
)


class _Resp:
    def __init__(self, data, success=True, error=None):
        self.success = success
        self.data = data
        self.error = error


class _Client:
    def __init__(self, **responses):
        self.calls = []
        self._responses = responses

    def _record(self, name, **kw):
        self.calls.append((name, kw))
        return self._responses.get(name, _Resp([]))

    def find_resources_by_selector(self, selector, environment=None):
        return self._record("selector", selector=selector, environment=environment)

    def find_resources_by_tag(self, key, value, environment=None):
        return self._record("tag", key=key, value=value, environment=environment)

    def list_resources(self, limit=None, offset=None, environment=None):
        return self._record("list", limit=limit, offset=offset, environment=environment)

    def list_resource_definitions(self, resource_namespace=None):
        return self._record("defs", resource_namespace=resource_namespace)


class TestParseTagSelector(unittest.TestCase):
    def test_parses_and_strips_pairs(self):
        self.assertEqual(
            parse_tag_selector(" env = dev , tier=web "), {"env": "dev", "tier": "web"}
        )

    def test_ignores_pairs_without_an_equals(self):
        self.assertEqual(parse_tag_selector("env=dev,garbage"), {"env": "dev"})

    def test_value_may_contain_an_equals(self):
        self.assertEqual(parse_tag_selector("url=a=b"), {"url": "a=b"})

    def test_empty_input(self):
        self.assertEqual(parse_tag_selector(""), {})
        self.assertEqual(parse_tag_selector(None), {})


class TestDecodeResourceOutput(unittest.TestCase):
    def test_decodes_base64_json(self):
        encoded = b64encode(json.dumps({"host": "db"}).encode("latin-1")).decode()
        self.assertEqual(decode_resource_output(encoded), {"host": "db"})

    def test_leaves_already_decoded_mappings_alone(self):
        self.assertEqual(decode_resource_output({"host": "db"}), {"host": "db"})

    def test_undecodable_string_passes_through(self):
        self.assertEqual(decode_resource_output("not-base64!!"), "not-base64!!")

    def test_empty_and_none(self):
        self.assertEqual(decode_resource_output(""), "")
        self.assertIsNone(decode_resource_output(None))

    def test_decode_outputs_maps_over_a_list_in_place(self):
        encoded = b64encode(json.dumps({"a": 1}).encode("latin-1")).decode()
        resources = [{"output": encoded}, {"no_output": 1}, "not-a-dict"]
        result = decode_resource_outputs(resources)
        self.assertIs(result, resources)
        self.assertEqual(resources[0]["output"], {"a": 1})


class TestQueryResources(unittest.TestCase):
    def test_tags_take_precedence_and_are_unpaginated(self):
        client = _Client(selector=_Resp([{"n": 1}]))
        resources, pagination, error = query_resources(
            client, "dev", key="k", value="v", tags="env=dev"
        )
        self.assertEqual(resources, [{"n": 1}])
        self.assertIsNone(pagination)
        self.assertIsNone(error)
        self.assertEqual(client.calls[0][0], "selector")
        self.assertEqual(client.calls[0][1]["selector"], {"env": "dev"})

    def test_single_tag_used_when_no_selector(self):
        client = _Client(tag=_Resp([{"n": 2}]))
        resources, pagination, _ = query_resources(client, "dev", key="k", value="v")
        self.assertEqual(resources, [{"n": 2}])
        self.assertIsNone(pagination)
        self.assertEqual(client.calls[0][0], "tag")

    def test_key_without_value_falls_through_to_the_full_list(self):
        client = _Client(list=_Resp({"items": [], "total": 0}))
        query_resources(client, "dev", key="k")
        self.assertEqual(client.calls[0][0], "list")

    def test_full_list_is_paginated(self):
        client = _Client(list=_Resp({"items": [{"n": 3}], "total": 120}))
        resources, pagination, error = query_resources(client, "dev", page=2)
        self.assertEqual(resources, [{"n": 3}])
        self.assertEqual(pagination["total"], 120)
        self.assertEqual(pagination["page"], 2)
        self.assertEqual(pagination["offset"], 50)
        self.assertIsNone(error)
        self.assertEqual(client.calls[0][1]["offset"], 50)

    def test_environment_is_forwarded_in_every_mode(self):
        for kwargs in ({"tags": "a=b"}, {"key": "k", "value": "v"}, {}):
            with self.subTest(kwargs=kwargs):
                client = _Client(list=_Resp({"items": [], "total": 0}))
                query_resources(client, "prod", **kwargs)
                self.assertEqual(client.calls[0][1]["environment"], "prod")

    def test_failure_returns_the_error_and_no_resources(self):
        client = _Client(list=_Resp(None, success=False, error="boom"))
        resources, pagination, error = query_resources(client, "dev")
        self.assertEqual(resources, [])
        self.assertIsNone(pagination)
        self.assertEqual(error, "boom")

    def test_tag_failure_returns_the_error(self):
        client = _Client(selector=_Resp(None, success=False, error="nope"))
        resources, _, error = query_resources(client, "dev", tags="a=b")
        self.assertEqual(resources, [])
        self.assertEqual(error, "nope")

    def test_non_list_and_non_dict_payloads_are_coerced(self):
        client = _Client(selector=_Resp("garbage"), list=_Resp("garbage"))
        self.assertEqual(query_resources(client, "dev", tags="a=b")[0], [])
        self.assertEqual(query_resources(client, "dev")[0], [])


class TestResolveResourceDefinition(unittest.TestCase):
    DEFS = [
        {
            "resource_definition_name": "postgres",
            "resource_namespace": "database.neuronsphere.io",
            "version": "0.1.0",
        },
        {
            "resource_definition_name": "kubernetes-cluster",
            "resource_namespace": "kubernetes.neuronsphere.io",
            "version": "0.1.0",
        },
    ]

    def test_resolves_by_name(self):
        client = _Client(defs=_Resp(self.DEFS))
        self.assertEqual(
            resolve_resource_definition(client, "postgres")["resource_namespace"],
            "database.neuronsphere.io",
        )

    def test_namespace_narrows_and_is_pushed_to_the_client(self):
        client = _Client(defs=_Resp(self.DEFS))
        result = resolve_resource_definition(
            client, "postgres", namespace="database.neuronsphere.io"
        )
        self.assertIsNotNone(result)
        self.assertEqual(
            client.calls[0][1]["resource_namespace"], "database.neuronsphere.io"
        )

    def test_wrong_namespace_does_not_match(self):
        client = _Client(defs=_Resp(self.DEFS))
        self.assertIsNone(
            resolve_resource_definition(client, "postgres", namespace="other.io")
        )

    def test_version_mismatch_does_not_match(self):
        client = _Client(defs=_Resp(self.DEFS))
        self.assertIsNone(
            resolve_resource_definition(client, "postgres", version="9.9")
        )

    def test_unknown_name_returns_none(self):
        client = _Client(defs=_Resp(self.DEFS))
        self.assertIsNone(resolve_resource_definition(client, "nope"))

    def test_client_failure_returns_none(self):
        client = _Client(defs=_Resp(None, success=False, error="down"))
        self.assertIsNone(resolve_resource_definition(client, "postgres"))


class TestSearchRepoClasses(unittest.TestCase):
    ITEMS = [
        {
            "repo_class_name": "hmd-ms-deployment",
            "repo_type": "microservice",
            "summary": "Orchestrates deployments across environments.",
        },
        {"repo_class_name": "hmd-inf-redis", "repo_type": "infrastructure"},
        {"repo_class_name": "hmd-vpc"},
    ]

    def test_empty_query_is_a_noop(self):
        self.assertEqual(search_repo_classes(self.ITEMS, ""), self.ITEMS)

    def test_matches_name_case_insensitively(self):
        result = search_repo_classes(self.ITEMS, "REDIS")
        self.assertEqual([r["repo_class_name"] for r in result], ["hmd-inf-redis"])

    def test_matches_repo_type(self):
        result = search_repo_classes(self.ITEMS, "microservice")
        self.assertEqual([r["repo_class_name"] for r in result], ["hmd-ms-deployment"])

    def test_matches_discovery_summary(self):
        # NERD0013 SPEC0001: list_repo_classes now carries the latest version's
        # summary, so the catalog search box finds a class by what it does.
        result = search_repo_classes(self.ITEMS, "orchestrates")
        self.assertEqual([r["repo_class_name"] for r in result], ["hmd-ms-deployment"])

    def test_missing_repo_type_does_not_raise(self):
        self.assertEqual(
            [r["repo_class_name"] for r in search_repo_classes(self.ITEMS, "vpc")],
            ["hmd-vpc"],
        )

    def test_no_match_returns_empty(self):
        self.assertEqual(search_repo_classes(self.ITEMS, "zzz"), [])


if __name__ == "__main__":
    unittest.main()
