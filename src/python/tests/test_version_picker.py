"""The ChangeSet version picker: lazy loading, filtering, and per-item scoping.

Opening "Edit instance" used to block on fetching *every* version of the item's
repo class through the unpaged ``find_repo_class_versions``, which also makes the
microservice resolve dependencies per version -- work the editor never uses. The
panel now renders with no API call at all and pulls one page of versions
afterwards, through the same endpoint the "Add Instance" form already used.

Three things are worth pinning:

* the editor view makes no version call whatsoever (the regression that would
  silently reintroduce the slow panel),
* the search box actually filters (it submits ``version_q``, and the view used
  to read only ``q``, so typing did nothing), and
* element ids are scoped per item, since several panels can be open at once.
"""
import unittest
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from deployments.models import ChangeSetDraft


class FakeResponse:
    def __init__(self, data=None, success=True, error=None):
        self.success = success
        self.data = data if data is not None else []
        self.error = error


class FakeClient:
    """Counts version calls so "which path did the view take" is observable."""

    def __init__(self, total=3, versions=None):
        self.calls = []
        self.page_kwargs = []
        self.total = total
        self.versions = versions if versions is not None else ["0.1", "0.2", "0.3"]

    def count(self, name):
        return self.calls.count(name)

    def find_repo_class_versions(self, repo_class_name):
        self.calls.append("find_repo_class_versions")
        return FakeResponse([{"version": v} for v in self.versions])

    def find_repo_class_versions_page(self, repo_class_name, q="", limit=50, offset=0):
        self.calls.append("find_repo_class_versions_page")
        self.page_kwargs.append(
            {
                "repo_class_name": repo_class_name,
                "q": q,
                "limit": limit,
                "offset": offset,
            }
        )
        matched = [v for v in self.versions if q.lower() in v.lower()]
        return FakeResponse(
            {
                "items": [{"version": v} for v in matched[offset : offset + limit]],
                "total": len(matched),
                "limit": limit,
                "offset": offset,
            }
        )


class VersionPickerTestCase(unittest.TestCase):
    def setUp(self):
        self.user = User.objects.create_user("picker", password="pw")
        self.fake = FakeClient()
        patcher = mock.patch(
            "deployments.views.get_api_client_for_request", return_value=self.fake
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = Client()
        self.client.force_login(self.user)

    def draft_with_item(self, version="0.2"):
        return ChangeSetDraft.objects.create(
            user=self.user,
            name="d",
            content=[
                {
                    "repo_instance_name": "thing",
                    "repo_class_name": "hmd-ms-test",
                    "repo_class_version": version,
                    "deployment_id": "aaa",
                    "instance_configuration": {},
                }
            ],
            status=ChangeSetDraft.Status.DRAFT,
        )

    def edit_instance(self, draft, index=0):
        return self.client.get(
            reverse(
                "deployments:changeset_edit_item_instance",
                kwargs={"draft_id": draft.pk, "index": index},
            )
        )


class TestInstanceEditorIsLazy(VersionPickerTestCase):
    def test_opening_the_editor_makes_no_version_call(self):
        response = self.edit_instance(self.draft_with_item())

        self.assertEqual(response.status_code, 200)
        # Neither the unpaged call it used to make, nor an eager paged one.
        self.assertEqual(self.fake.count("find_repo_class_versions"), 0)
        self.assertEqual(self.fake.count("find_repo_class_versions_page"), 0)

    def test_editor_renders_a_picker_not_an_option_list(self):
        html = self.edit_instance(self.draft_with_item()).content.decode()

        self.assertNotIn("<option", html)
        # The list is fetched by the picker after the panel renders.
        self.assertIn('hx-trigger="load, input changed delay:300ms, search"', html)

    def test_hidden_version_input_is_seeded_with_the_current_version(self):
        # Saving an untouched panel must keep the current version, which also
        # means that version never has to appear in the fetched page.
        html = self.edit_instance(self.draft_with_item(version="9.9")).content.decode()

        self.assertIn('name="version"', html)
        self.assertIn('id="version_input_0"', html)
        self.assertIn('value="9.9"', html)

    def test_editor_survives_a_repo_class_with_no_versions(self):
        # The old template hid the whole editor when versions could not be
        # loaded, taking Deployment ID and Configuration down with it.
        html = self.edit_instance(self.draft_with_item()).content.decode()

        self.assertIn('name="deployment_id"', html)
        self.assertIn('name="instance_configuration"', html)

    def test_untouched_panel_saves_the_original_version(self):
        draft = self.draft_with_item(version="9.9")
        response = self.client.post(
            reverse(
                "deployments:changeset_set_item_instance",
                kwargs={"draft_id": draft.pk, "index": 0},
            ),
            {"version": "9.9", "deployment_id": "aaa", "instance_configuration": ""},
        )

        self.assertEqual(response.status_code, 200)
        draft.refresh_from_db()
        self.assertEqual(draft.content[0]["repo_class_version"], "9.9")


class TestVersionOptionsFiltering(VersionPickerTestCase):
    def options(self, **params):
        return self.client.get(
            reverse("deployments:api_repo_class_versions_options"), params
        )

    def test_version_q_is_accepted_as_the_filter(self):
        # htmx submits a named search input under its own name, and both pickers
        # name it version_q; reading only ?q= ignored everything the user typed.
        self.options(repo_class="hmd-ms-test", version_q="0.3")

        self.assertEqual(self.fake.page_kwargs[-1]["q"], "0.3")

    def test_q_still_works(self):
        self.options(repo_class="hmd-ms-test", q="0.1")

        self.assertEqual(self.fake.page_kwargs[-1]["q"], "0.1")

    def test_q_wins_over_version_q_when_both_are_sent(self):
        self.options(repo_class="hmd-ms-test", q="0.1", version_q="0.3")

        self.assertEqual(self.fake.page_kwargs[-1]["q"], "0.1")

    def test_filter_reaches_the_rendered_list(self):
        html = self.options(repo_class="hmd-ms-test", version_q="0.3").content.decode()

        self.assertIn("0.3", html)
        self.assertNotIn(">0.1<", html)

    def test_only_one_page_is_requested(self):
        self.options(repo_class="hmd-ms-test")

        self.assertEqual(self.fake.page_kwargs[-1]["limit"], 50)
        self.assertEqual(self.fake.page_kwargs[-1]["offset"], 0)
        self.assertEqual(self.fake.count("find_repo_class_versions"), 0)

    def test_page_two_maps_to_an_offset(self):
        self.options(repo_class="hmd-ms-test", page="3")

        self.assertEqual(self.fake.page_kwargs[-1]["offset"], 100)


class TestPerItemIdScoping(VersionPickerTestCase):
    def options(self, **params):
        return self.client.get(
            reverse("deployments:api_repo_class_versions_options"), params
        )

    def test_item_index_scopes_the_element_ids(self):
        html = self.options(repo_class="hmd-ms-test", item_index="2").content.decode()

        self.assertIn("version_input_2", html)
        self.assertNotIn("'version_input'", html)

    def test_absent_item_index_keeps_the_add_form_ids(self):
        html = self.options(repo_class="hmd-ms-test").content.decode()

        self.assertIn("'version_input'", html)
        self.assertNotIn("version_input_", html)

    def test_a_junk_item_index_falls_back_rather_than_reflecting(self):
        # The ids are derived from the index, never taken from the query string,
        # so nothing caller-supplied can land in the markup.
        html = self.options(
            repo_class="hmd-ms-test", item_index="'); alert(1);//"
        ).content.decode()

        self.assertIn("'version_input'", html)
        self.assertNotIn("alert(1)", html)

    def test_item_index_zero_is_not_treated_as_absent(self):
        # The first ChangeSet item is index 0, which is falsy in a template.
        fake = FakeClient(versions=[f"0.{i}" for i in range(120)])
        with mock.patch(
            "deployments.views.get_api_client_for_request", return_value=fake
        ):
            html = self.options(
                repo_class="hmd-ms-test", item_index="0"
            ).content.decode()

        self.assertIn("version_input_0", html)
        self.assertIn('hx-target="#version-results-0"', html)
        self.assertIn("item_index=0", html)

    def test_pagination_carries_state_without_global_name_selectors(self):
        fake = FakeClient(versions=[f"0.{i}" for i in range(120)])
        with mock.patch(
            "deployments.views.get_api_client_for_request", return_value=fake
        ):
            html = self.options(
                repo_class="hmd-ms-test", item_index="2"
            ).content.decode()

        # [name=version_q] would match every open picker on the page at once.
        self.assertNotIn("hx-include", html)
        self.assertIn("repo_class=hmd-ms-test", html)
        self.assertIn("item_index=2", html)
        self.assertIn('hx-target="#version-results-2"', html)


if __name__ == "__main__":
    unittest.main()
