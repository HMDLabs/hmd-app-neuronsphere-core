"""Unit tests for the ChangeSet topological-sort helper in models.py.

Imports ``topological_sort_changeset`` from models.py by loading the function
bytes directly (regex-extract + exec), so the test runs without booting Django
or importing django.db — mirroring the approach in test_parse_deps.py.
"""
import os
import re
import textwrap
import unittest

_MODELS_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "deployments",
    "models.py",
)


def _extract_topo_sort_source():
    with open(_MODELS_PATH, "r", encoding="utf-8") as fh:
        text = fh.read()
    match = re.search(
        r"^def topological_sort_changeset\(items[\s\S]+?(?=\n(?:@|def |class )|\Z)",
        text,
        re.MULTILINE,
    )
    if not match:
        raise RuntimeError("topological_sort_changeset not found in models.py")
    return textwrap.dedent(match.group(0))


_module_globals: dict = {}
exec(_extract_topo_sort_source(), _module_globals)
topological_sort_changeset = _module_globals["topological_sort_changeset"]


def _item(name, deps=None):
    return {"repo_instance_name": name, "dependencies": deps or {}}


def _names(items):
    return [i.get("repo_instance_name") for i in items]


class TestTopologicalSortChangeset(unittest.TestCase):
    def test_dependent_moved_after_prerequisite(self):
        # B depends on A but is inserted first -> A must come first.
        items = [_item("b", {"vpc": "a"}), _item("a")]
        self.assertEqual(_names(topological_sort_changeset(items)), ["a", "b"])

    def test_multi_target_list_form(self):
        # C depends on [A, B] -> C is last.
        items = [_item("c", {"backends": ["a", "b"]}), _item("a"), _item("b")]
        result = _names(topological_sort_changeset(items))
        self.assertEqual(result[-1], "c")
        self.assertLess(result.index("a"), result.index("c"))
        self.assertLess(result.index("b"), result.index("c"))

    def test_chain_ordered(self):
        # C -> B -> A, inserted reversed, should order [a, b, c].
        items = [
            _item("c", {"r": "b"}),
            _item("b", {"r": "a"}),
            _item("a"),
        ]
        self.assertEqual(_names(topological_sort_changeset(items)), ["a", "b", "c"])

    def test_stability_independent_items_keep_order(self):
        items = [_item("x"), _item("y"), _item("z")]
        self.assertEqual(_names(topological_sort_changeset(items)), ["x", "y", "z"])

    def test_external_bom_targets_ignored(self):
        # "base-vpc" is not an item in the list -> imposes no constraint, no error.
        items = [_item("a", {"vpc": "base-vpc"}), _item("b")]
        self.assertEqual(_names(topological_sort_changeset(items)), ["a", "b"])

    def test_cycle_is_safe(self):
        # A <-> B mutual dependency must not hang; every item returned once.
        items = [_item("a", {"r": "b"}), _item("b", {"r": "a"})]
        result = topological_sort_changeset(items)
        self.assertEqual(sorted(_names(result)), ["a", "b"])
        self.assertEqual(len(result), 2)

    def test_missing_and_empty_dependencies_pass_through(self):
        items = [
            {"repo_instance_name": "a"},  # no dependencies key
            _item("b", {}),
        ]
        self.assertEqual(_names(topological_sort_changeset(items)), ["a", "b"])

    def test_empty_list(self):
        self.assertEqual(topological_sort_changeset([]), [])

    def test_item_without_name_keeps_position(self):
        items = [_item("a"), {"dependencies": {}}, _item("b")]
        result = topological_sort_changeset(items)
        self.assertEqual(len(result), 3)
        # The unnamed item is preserved (defensively not dropped).
        self.assertIn(None, _names(result))

    def test_diamond_dependency(self):
        # d depends on b and c; b and c both depend on a.
        items = [
            _item("d", {"r": ["b", "c"]}),
            _item("b", {"r": "a"}),
            _item("c", {"r": "a"}),
            _item("a"),
        ]
        result = _names(topological_sort_changeset(items))
        self.assertEqual(result[0], "a")
        self.assertEqual(result[-1], "d")
        self.assertLess(result.index("b"), result.index("d"))
        self.assertLess(result.index("c"), result.index("d"))


if __name__ == "__main__":
    unittest.main()
