"""Unit tests for ``sanitize_changeset_item`` in models.py.

Loads the allowed-keys tuple and the function from source (regex-extract +
exec), so the test runs without booting Django, mirroring
test_changeset_topo_sort.py.
"""

import os
import re
import unittest

_MODELS_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "deployments",
    "models.py",
)


def _load_sanitize():
    with open(_MODELS_PATH, "r", encoding="utf-8") as fh:
        text = fh.read()
    match = re.search(
        r"^_CHANGESET_ITEM_ALLOWED_KEYS = \([\s\S]+?^def sanitize_changeset_item\([\s\S]+?(?=\n(?:@|def |class )|\Z)",
        text,
        re.MULTILINE,
    )
    if not match:
        raise RuntimeError("sanitize_changeset_item not found in models.py")
    namespace = {}
    exec(match.group(0), namespace)
    return namespace["sanitize_changeset_item"]


sanitize_changeset_item = _load_sanitize()


class SanitizeChangesetItemTest(unittest.TestCase):
    def test_keeps_an_items_own_deploy_image(self):
        image = "ghcr.io/hmdlabs/hmd-img-projectbuilder:0.5.402"
        item = {
            "repo_instance_name": "db",
            "repo_class_name": "hmd-postgres-rds",
            "repo_class_version": "0.1.40",
            "deploy_image": image,
        }
        self.assertEqual(sanitize_changeset_item(item)["deploy_image"], image)

    def test_drops_bom_runtime_fields(self):
        item = {
            "repo_instance_name": "db",
            "status": "DEPLOYED",
            "auto_deploy": True,
            "deployment_image": "ghcr.io/hmdlabs/hmd-img-projectbuilder:0.5.400",
        }
        self.assertEqual(sanitize_changeset_item(item), {"repo_instance_name": "db"})


if __name__ == "__main__":
    unittest.main()
