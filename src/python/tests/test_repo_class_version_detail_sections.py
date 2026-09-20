"""Unit tests for build_repo_class_version_detail_sections."""
import unittest

from deployments.services.repo_class_detail import (
    build_repo_class_version_detail_sections as _build_repo_class_version_detail_sections,
)


class TestBuildRepoClassVersionDetailSections(unittest.TestCase):
    def test_empty_detail_yields_empty_sections(self):
        sections = _build_repo_class_version_detail_sections(None)
        self.assertEqual(sections["discovery"], {})
        self.assertEqual(sections["dependency_rows"], [])
        self.assertEqual(sections["default_configuration"], {})

        sections = _build_repo_class_version_detail_sections({})
        self.assertEqual(sections["discovery"], {})
        self.assertEqual(sections["dependency_rows"], [])
        self.assertEqual(sections["default_configuration"], {})

    def test_missing_discovery_and_configuration_keys_default_to_empty(self):
        detail = {"version": "1.0.0", "identifier": "rcv-1"}
        sections = _build_repo_class_version_detail_sections(detail)
        self.assertEqual(sections["discovery"], {})
        self.assertEqual(sections["default_configuration"], {})

    def test_created_and_updated_extracted_from_underscored_keys(self):
        # Django templates forbid leading-underscore lookups (e.g. `detail._created`),
        # so these must be pulled out into their own top-level keys here.
        detail = {"_created": "2026-01-01T00:00:00", "_updated": "2026-01-02T00:00:00"}
        sections = _build_repo_class_version_detail_sections(detail)
        self.assertEqual(sections["created"], "2026-01-01T00:00:00")
        self.assertEqual(sections["updated"], "2026-01-02T00:00:00")

    def test_created_and_updated_none_when_detail_missing(self):
        sections = _build_repo_class_version_detail_sections(None)
        self.assertIsNone(sections["created"])
        self.assertIsNone(sections["updated"])

    def test_discovery_and_default_configuration_passed_through(self):
        discovery = {"summary": "Does things", "entry_points": [], "capabilities": []}
        default_configuration = {"some_setting": "value"}
        detail = {
            "discovery": discovery,
            "default_configuration": default_configuration,
        }
        sections = _build_repo_class_version_detail_sections(detail)
        self.assertEqual(sections["discovery"], discovery)
        self.assertEqual(sections["default_configuration"], default_configuration)

    def test_required_string_true_normalized_to_bool_true(self):
        detail = {
            "dependencies": {
                "network": {
                    "repo_class_name": "hmd-inf-vpc",
                    "required": "true",
                    "version_spec": "~= 0.1",
                }
            }
        }
        sections = _build_repo_class_version_detail_sections(detail)
        row = sections["dependency_rows"][0]
        self.assertIs(row["required"], True)
        self.assertEqual(row["repo_class_name"], "hmd-inf-vpc")
        self.assertEqual(row["version_spec"], "~= 0.1")
        self.assertEqual(row["role"], "network")

    def test_required_string_false_normalized_to_bool_false(self):
        detail = {
            "dependencies": {
                "sidecar": {"repo_class_name": "hmd-inf-cache", "required": "false"}
            }
        }
        sections = _build_repo_class_version_detail_sections(detail)
        row = sections["dependency_rows"][0]
        self.assertIs(row["required"], False)

    def test_dependency_rows_sorted_by_role(self):
        detail = {
            "dependencies": {
                "zeta": {"repo_class_name": "hmd-inf-z", "required": "true"},
                "alpha": {"repo_class_name": "hmd-inf-a", "required": "false"},
            }
        }
        sections = _build_repo_class_version_detail_sections(detail)
        roles = [r["role"] for r in sections["dependency_rows"]]
        self.assertEqual(roles, ["alpha", "zeta"])


if __name__ == "__main__":
    unittest.main()
