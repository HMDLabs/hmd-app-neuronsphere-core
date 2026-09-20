"""Render tests for partials/dependency_picker.html.

Verifies the Remove/Undo affordance is gated by ``required``: optional roles get
a Remove control, required roles never do. Renders the real template through a
standalone ``django.template.Engine`` (independent of any global TEMPLATES /
ROOT_URLCONF another test may have configured), stubbing the single ``{% url %}``
tag so no urlconf is needed — matching the suite's lightweight, no-app style.
"""
import os
import unittest

import django
from django.conf import settings

_TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "deployments",
    "templates",
    "deployments",
    "partials",
    "dependency_picker.html",
)

# The one reversed route in the template — replaced with a literal so rendering
# needs no urlconf. If the template's markup for this changes, the assertion
# below catches it (the tag would remain and rendering would fail).
_URL_TAG = "{% url 'deployments:api_dep_candidates' draft_id=draft.pk %}"


def _ensure_settings():
    # Configure only if no other test already did; TEMPLATES is unneeded because
    # we build our own Engine rather than using engines["django"].
    if not settings.configured:
        settings.configure(DEBUG=False, INSTALLED_APPS=[])
        django.setup()


_ensure_settings()

from django.template import Context, Engine  # noqa: E402  (after configure)

with open(_TEMPLATE_PATH, "r", encoding="utf-8") as _fh:
    _SRC = _fh.read()
assert _URL_TAG in _SRC, "dependency_picker.html url tag changed; update _URL_TAG"
_SRC = _SRC.replace(_URL_TAG, "/changeset/1/dep-candidates/")

_TEMPLATE = Engine(dirs=[], app_dirs=False).from_string(_SRC)


class _Draft:
    pk = 1


def _role(name, required, compatible="hmd-inf-thing", selected=None):
    return {
        "role": name,
        "compatible_class_name": compatible,
        "required": required,
        "in_draft_candidates": selected or [],
        "selected": selected or [],
        "initial_source": "draft",
        "stale": False,
        "is_resource": False,
        "resource": None,
    }


def _render(roles):
    return _TEMPLATE.render(
        Context(
            {
                "roles": roles,
                "draft": _Draft(),
                "picker_id": "edit-0",
                "no_version": False,
                "environments": ["dev"],
            }
        )
    )


class TestDependencyPickerRemoveGating(unittest.TestCase):
    def test_optional_role_has_remove_required_does_not(self):
        html = _render(
            [
                _role("vpc", required=True, selected=["base-vpc"]),
                _role("redis", required=False, selected=["cache-a"]),
            ]
        )
        # Exactly one Remove control — for the optional role only.
        self.assertEqual(html.count('@click="removed = true"'), 1)
        # The required role is labelled required and offers no removal.
        self.assertIn(">required</span>", html)
        # Both role blocks wrap their inputs in the disable-on-remove fieldset.
        self.assertEqual(html.count('<fieldset :disabled="removed"'), 2)

    def test_required_only_role_has_no_remove_control(self):
        html = _render([_role("vpc", required=True, selected=["base-vpc"])])
        self.assertNotIn('@click="removed = true"', html)
        self.assertNotIn("Removed", html)

    def test_optional_only_role_has_remove_and_undo(self):
        html = _render([_role("redis", required=False, selected=["cache-a"])])
        self.assertIn('@click="removed = true"', html)  # Remove
        self.assertIn('@click="removed = false"', html)  # Undo
        self.assertIn("Removed", html)

    def test_stale_role_is_removable(self):
        # Stale (undeclared) deps are required=False, so they must be removable.
        stale = _role("legacy", required=False, selected=["old-target"])
        stale["stale"] = True
        stale["initial_source"] = "bom"
        html = _render([stale])
        self.assertIn('@click="removed = true"', html)


if __name__ == "__main__":
    unittest.main()
