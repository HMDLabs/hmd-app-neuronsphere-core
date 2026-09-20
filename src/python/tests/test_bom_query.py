"""Unit tests for the BOM query helpers extracted from ``bom_list``.

``sort_bom`` / ``filter_bom`` / ``bom_facets`` must reproduce the inline
behaviour they replaced; ``summarize_bom`` and ``reverse_dependency_index`` are
new, added for the MCP tool layer.
"""
import unittest

from deployments.services.bom_query import (
    SORTABLE_FIELDS,
    bom_facets,
    filter_bom,
    reverse_dependency_index,
    sort_bom,
    summarize_bom,
)


def _item(name, repo_class, version="0.1", status="DEPLOYED", dependencies=None):
    return {
        "repo_instance_name": name,
        "repo_class_name": repo_class,
        "repo_class_version": version,
        "status": status,
        "dependencies": dependencies or {},
    }


BOM = [
    _item("web", "hmd-app-neuronsphere", "0.3", "DEPLOYED", {"db": "pg", "net": "vpc"}),
    _item("pg", "hmd-database-account", "0.1", "DEPLOYED", {"net": "vpc"}),
    _item("vpc", "hmd-vpc", "0.2", "FAILED"),
    _item("cache", "hmd-inf-redis", "0.1", "NOT_DEPLOYED", {"net": ["vpc"]}),
]


class TestSortBom(unittest.TestCase):
    def test_sorts_ascending_by_default(self):
        names = [i["repo_instance_name"] for i in sort_bom(BOM, "repo_instance_name")]
        self.assertEqual(names, ["cache", "pg", "vpc", "web"])

    def test_sorts_descending(self):
        names = [
            i["repo_instance_name"] for i in sort_bom(BOM, "repo_instance_name", "desc")
        ]
        self.assertEqual(names, ["web", "vpc", "pg", "cache"])

    def test_unknown_field_is_ignored_not_rejected(self):
        self.assertEqual(sort_bom(BOM, "not_a_field"), BOM)
        self.assertEqual(sort_bom(BOM, ""), BOM)

    def test_does_not_mutate_input(self):
        original = list(BOM)
        sort_bom(BOM, "status")
        self.assertEqual(BOM, original)

    def test_every_sortable_field_is_usable(self):
        for field in SORTABLE_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(len(sort_bom(BOM, field)), len(BOM))

    def test_missing_key_sorts_as_empty_string(self):
        items = [{"repo_instance_name": "b"}, {}]
        self.assertEqual(
            sort_bom(items, "repo_instance_name"), [{}, {"repo_instance_name": "b"}]
        )


class TestFilterBom(unittest.TestCase):
    def test_no_filters_is_a_noop(self):
        self.assertEqual(filter_bom(BOM), BOM)

    def test_filters_by_status(self):
        result = filter_bom(BOM, status="FAILED")
        self.assertEqual([i["repo_instance_name"] for i in result], ["vpc"])

    def test_filters_by_repo_class(self):
        result = filter_bom(BOM, repo_class="hmd-vpc")
        self.assertEqual([i["repo_instance_name"] for i in result], ["vpc"])

    def test_search_matches_instance_name_case_insensitively(self):
        result = filter_bom(BOM, search="WE")
        self.assertEqual([i["repo_instance_name"] for i in result], ["web"])

    def test_search_also_matches_repo_class_name(self):
        result = filter_bom(BOM, search="redis")
        self.assertEqual([i["repo_instance_name"] for i in result], ["cache"])

    def test_filters_compose(self):
        result = filter_bom(BOM, search="p", status="DEPLOYED")
        self.assertEqual([i["repo_instance_name"] for i in result], ["web", "pg"])

    def test_no_match_returns_empty(self):
        self.assertEqual(filter_bom(BOM, search="nothing-matches-this"), [])


class TestBomFacets(unittest.TestCase):
    def test_returns_sorted_distinct_values(self):
        self.assertEqual(
            bom_facets(BOM),
            {
                "statuses": ["DEPLOYED", "FAILED", "NOT_DEPLOYED"],
                "repo_classes": [
                    "hmd-app-neuronsphere",
                    "hmd-database-account",
                    "hmd-inf-redis",
                    "hmd-vpc",
                ],
            },
        )

    def test_skips_blank_values(self):
        facets = bom_facets([{"status": "", "repo_class_name": ""}, {}])
        self.assertEqual(facets, {"statuses": [], "repo_classes": []})

    def test_empty_bom(self):
        self.assertEqual(bom_facets([]), {"statuses": [], "repo_classes": []})


class TestSummarizeBom(unittest.TestCase):
    def test_counts_by_status_and_class(self):
        summary = summarize_bom(BOM)
        self.assertEqual(summary["total"], 4)
        self.assertEqual(
            summary["by_status"],
            {"DEPLOYED": 2, "FAILED": 1, "NOT_DEPLOYED": 1},
        )

    def test_repo_classes_ordered_by_count_then_name(self):
        items = BOM + [_item("web2", "hmd-app-neuronsphere")]
        summary = summarize_bom(items)
        self.assertEqual(
            summary["by_repo_class"][0],
            {"repo_class": "hmd-app-neuronsphere", "count": 2},
        )

    def test_missing_status_counts_as_unknown(self):
        summary = summarize_bom([{"repo_instance_name": "x", "repo_class_name": "c"}])
        self.assertEqual(summary["by_status"], {"UNKNOWN": 1})

    def test_empty_bom(self):
        self.assertEqual(
            summarize_bom([]), {"total": 0, "by_status": {}, "by_repo_class": []}
        )


class TestReverseDependencyIndex(unittest.TestCase):
    def test_maps_target_to_its_dependents(self):
        index = reverse_dependency_index(BOM)
        self.assertEqual(index["pg"], [{"instance": "web", "role": "db"}])

    def test_collects_multiple_dependents_sorted(self):
        self.assertEqual(
            reverse_dependency_index(BOM)["vpc"],
            [
                {"instance": "cache", "role": "net"},
                {"instance": "pg", "role": "net"},
                {"instance": "web", "role": "net"},
            ],
        )

    def test_handles_scalar_and_list_valued_dependencies(self):
        # "cache" declares net as a one-element list, "pg" as a bare string.
        index = reverse_dependency_index(BOM)
        dependents = {d["instance"] for d in index["vpc"]}
        self.assertIn("cache", dependents)
        self.assertIn("pg", dependents)

    def test_targets_outside_the_bom_are_skipped(self):
        items = [_item("a", "c", dependencies={"role": "not-in-bom"})]
        self.assertEqual(reverse_dependency_index(items), {})

    def test_instance_with_no_dependents_is_absent(self):
        self.assertNotIn("web", reverse_dependency_index(BOM))

    def test_empty_bom(self):
        self.assertEqual(reverse_dependency_index([]), {})


if __name__ == "__main__":
    unittest.main()
