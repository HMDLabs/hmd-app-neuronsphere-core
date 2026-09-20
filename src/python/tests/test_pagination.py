"""Unit tests for the shared pagination envelope.

Guards the extraction of the two byte-identical inline blocks that previously
lived in ``views.py`` (``api_repo_class_versions_options`` and
``resource_list``): ``build_pagination`` must reproduce them exactly.
"""
import unittest

from deployments.services.pagination import (
    build_pagination,
    offset_for_page,
    parse_page,
)


def _legacy(total, limit, offset, page):
    """The dict as it was written inline in views.py, verbatim."""
    total = int(total or 0)
    num_pages = max((total + limit - 1) // limit, 1)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "page": page,
        "num_pages": num_pages,
        "has_prev": page > 1,
        "has_next": page < num_pages,
        "start": offset + 1 if total else 0,
        "end": min(offset + limit, total),
    }


class TestParsePage(unittest.TestCase):
    def test_missing_and_empty_fall_back_to_one(self):
        self.assertEqual(parse_page(None), 1)
        self.assertEqual(parse_page(""), 1)

    def test_non_integer_falls_back_rather_than_raising(self):
        self.assertEqual(parse_page("abc"), 1)
        self.assertEqual(parse_page("3.5"), 1)

    def test_never_below_one(self):
        self.assertEqual(parse_page("0"), 1)
        self.assertEqual(parse_page("-7"), 1)

    def test_valid_value_passes_through(self):
        self.assertEqual(parse_page("4"), 4)
        self.assertEqual(parse_page(4), 4)


class TestOffsetForPage(unittest.TestCase):
    def test_first_page_is_zero_offset(self):
        self.assertEqual(offset_for_page(1, 50), 0)

    def test_later_pages(self):
        self.assertEqual(offset_for_page(3, 50), 100)

    def test_page_below_one_clamps(self):
        self.assertEqual(offset_for_page(0, 50), 0)


class TestBuildPaginationParity(unittest.TestCase):
    """Every case must match the inline implementation byte for byte."""

    CASES = [
        (0, 50, 0, 1),  # empty result set
        (1, 50, 0, 1),  # single item
        (50, 50, 0, 1),  # exactly one full page
        (51, 50, 50, 2),  # boundary: second page holds one item
        (100, 50, 50, 2),  # exact page boundary
        (214, 50, 100, 3),  # mid-range
        (214, 50, 200, 5),  # last, partial page
        (10, 50, 100, 3),  # offset beyond total
    ]

    def test_matches_legacy_dict(self):
        for total, limit, offset, page in self.CASES:
            with self.subTest(total=total, limit=limit, offset=offset, page=page):
                self.assertEqual(
                    build_pagination(total, limit, offset, page),
                    _legacy(total, limit, offset, page),
                )

    def test_total_none_is_treated_as_zero(self):
        self.assertEqual(build_pagination(None, 50, 0, 1), _legacy(0, 50, 0, 1))

    def test_page_derived_from_offset_when_omitted(self):
        # The MCP tools page by offset rather than page number.
        self.assertEqual(build_pagination(214, 50, 100), _legacy(214, 50, 100, 3))
        self.assertEqual(build_pagination(214, 50, 0), _legacy(214, 50, 0, 1))

    def test_zero_limit_does_not_divide_by_zero(self):
        result = build_pagination(10, 0, 0)
        self.assertEqual(result["num_pages"], 1)
        self.assertEqual(result["page"], 1)


if __name__ == "__main__":
    unittest.main()
