"""Unit tests for the dependency form-parser helper used by the ChangeSet views."""
import unittest

from deployments.services.dependency_roles import (
    parse_deps_from_post as _parse_deps_from_post,
)


class _FakeQueryDict:
    """Tiny stand-in for django.http.QueryDict — duck-types keys()/getlist()."""

    def __init__(self, pairs):
        self._data: dict = {}
        for key, value in pairs:
            self._data.setdefault(key, []).append(value)

    def keys(self):
        return list(self._data.keys())

    def getlist(self, key):
        return list(self._data.get(key, []))


class TestParseDepsFromPost(unittest.TestCase):
    def test_single_value_stored_as_string(self):
        post = _FakeQueryDict([("dep_vpc", "base-vpc")])
        self.assertEqual(_parse_deps_from_post(post), {"vpc": "base-vpc"})

    def test_two_values_stored_as_list(self):
        post = _FakeQueryDict([("dep_backends", "a"), ("dep_backends", "b")])
        result = _parse_deps_from_post(post)
        self.assertEqual(sorted(result["backends"]), ["a", "b"])
        self.assertIsInstance(result["backends"], list)

    def test_src_radio_fields_ignored(self):
        post = _FakeQueryDict(
            [
                ("dep_vpc", "base-vpc"),
                ("src_vpc", "draft"),
                ("src_backends", "bom"),
            ]
        )
        self.assertEqual(_parse_deps_from_post(post), {"vpc": "base-vpc"})

    def test_empty_and_whitespace_dropped(self):
        post = _FakeQueryDict(
            [
                ("dep_vpc", ""),
                ("dep_other", "   "),
                ("dep_real", "x"),
            ]
        )
        self.assertEqual(_parse_deps_from_post(post), {"real": "x"})

    def test_role_with_only_blanks_omitted(self):
        post = _FakeQueryDict([("dep_vpc", ""), ("dep_vpc", "  ")])
        self.assertEqual(_parse_deps_from_post(post), {})

    def test_duplicates_deduplicated(self):
        post = _FakeQueryDict(
            [("dep_backends", "a"), ("dep_backends", "a"), ("dep_backends", "b")]
        )
        result = _parse_deps_from_post(post)
        self.assertEqual(sorted(result["backends"]), ["a", "b"])

    def test_dedup_collapses_to_single_string(self):
        post = _FakeQueryDict([("dep_backends", "a"), ("dep_backends", "a")])
        self.assertEqual(_parse_deps_from_post(post), {"backends": "a"})

    def test_bare_dep_prefix_ignored(self):
        post = _FakeQueryDict([("dep_", "x"), ("dep_vpc", "y")])
        self.assertEqual(_parse_deps_from_post(post), {"vpc": "y"})

    def test_values_trimmed(self):
        post = _FakeQueryDict([("dep_vpc", "  base-vpc  ")])
        self.assertEqual(_parse_deps_from_post(post), {"vpc": "base-vpc"})

    def test_removed_role_absent_from_post_is_dropped(self):
        # When the picker "removes" a role it submits no dep_<role> fields for it,
        # so the parsed deps must simply omit that role (implicit removal).
        post = _FakeQueryDict([("dep_vpc", "base-vpc")])
        self.assertEqual(_parse_deps_from_post(post), {"vpc": "base-vpc"})
        self.assertNotIn("redis", _parse_deps_from_post(post))


if __name__ == "__main__":
    unittest.main()
