"""Provider-aware group claim extraction and permission mapping.

A customer on Auth0 or their own OIDC provider must get the same permission
outcome an Okta customer gets. The failure modes these pin down are the quiet
ones: reading the wrong claim yields no groups and therefore no access, and a
mapping scoped to the wrong provider silently grants nothing.
"""
import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from deployments.adapters import extract_groups, groups_claim_for
from deployments.group_sync import sync_idp_permissions
from deployments.models import UserEnvironmentPermission

AUTH0_CLAIM = "https://neuronsphere.io/groups"


# --- claim extraction ------------------------------------------------------


@override_settings(IDP_GROUPS_CLAIMS={"acme-auth0": AUTH0_CLAIM, "corp-okta": "groups"})
def test_groups_claim_is_looked_up_per_provider():
    assert groups_claim_for("acme-auth0") == AUTH0_CLAIM
    assert groups_claim_for("corp-okta") == "groups"


@override_settings(IDP_GROUPS_CLAIMS={})
def test_groups_claim_defaults_for_unknown_provider():
    assert groups_claim_for("whoever") == "groups"


def test_extracts_namespaced_auth0_claim():
    extra = {AUTH0_CLAIM: ["transform", "platform"]}
    assert extract_groups(extra, AUTH0_CLAIM) == ["transform", "platform"]


def test_reads_claim_from_userinfo_when_absent_on_token():
    extra = {"userinfo": {"groups": ["a"]}}
    assert extract_groups(extra, "groups") == ["a"]


def test_reads_claim_from_id_token_as_last_resort():
    extra = {"userinfo": {}, "id_token": {"roles": ["admins"]}}
    assert extract_groups(extra, "roles") == ["admins"]


def test_single_valued_claim_is_normalised_to_a_list():
    """Otherwise a string claim iterates character by character downstream."""
    assert extract_groups({"groups": "solo"}, "groups") == ["solo"]


def test_wrong_claim_name_yields_nothing():
    assert extract_groups({AUTH0_CLAIM: ["transform"]}, "groups") == []


def test_missing_payloads_are_tolerated():
    assert extract_groups(None, "groups") == []
    assert extract_groups({"userinfo": None, "id_token": None}, "groups") == []


# --- permission mapping ----------------------------------------------------


@pytest.fixture
def user():
    """The conftest creates the schema and cleans between tests, so no db fixture."""
    return User.objects.create_user(username="dev@example.com", email="dev@example.com")


def _envs(user):
    return sorted(
        (p.environment, p.role)
        for p in UserEnvironmentPermission.objects.filter(user=user)
    )


@override_settings(
    IDP_GROUP_MAPPING={"acme-auth0": {"transform": {"prod": "deployer"}}},
    OKTA_GROUP_MAPPING={},
    OKTA_SUPERUSER_GROUPS=[],
    IDP_SUPERUSER_GROUPS={},
)
def test_provider_scoped_mapping_grants(user):
    sync_idp_permissions(user, ["transform"], provider="acme-auth0")
    assert _envs(user) == [("prod", "deployer")]


@override_settings(
    IDP_GROUP_MAPPING={"acme-auth0": {"transform": {"prod": "deployer"}}},
    OKTA_GROUP_MAPPING={},
    OKTA_SUPERUSER_GROUPS=[],
    IDP_SUPERUSER_GROUPS={},
)
def test_scoped_mapping_does_not_leak_to_another_provider(user):
    """The same group name may mean nothing under a different IdP."""
    sync_idp_permissions(user, ["transform"], provider="corp-okta")
    assert _envs(user) == []


@override_settings(
    IDP_GROUP_MAPPING={},
    OKTA_GROUP_MAPPING={"ns-dev-deployers": {"dev": "deployer"}},
    OKTA_SUPERUSER_GROUPS=[],
    IDP_SUPERUSER_GROUPS={},
)
def test_legacy_unscoped_mapping_applies_to_every_provider(user):
    """Preserves single-provider behaviour and eases adding a second IdP."""
    sync_idp_permissions(user, ["ns-dev-deployers"], provider="acme-auth0")
    assert _envs(user) == [("dev", "deployer")]


@override_settings(
    IDP_GROUP_MAPPING={"acme-auth0": {"shared": {"prod": "admin"}}},
    OKTA_GROUP_MAPPING={"shared": {"prod": "viewer"}},
    OKTA_SUPERUSER_GROUPS=[],
    IDP_SUPERUSER_GROUPS={},
)
def test_scoped_mapping_overrides_legacy_on_collision(user):
    sync_idp_permissions(user, ["shared"], provider="acme-auth0")
    assert _envs(user) == [("prod", "admin")]


@override_settings(
    IDP_GROUP_MAPPING={"acme-auth0": {"shared": {"prod": "admin"}}},
    OKTA_GROUP_MAPPING={"shared": {"prod": "viewer"}},
    OKTA_SUPERUSER_GROUPS=[],
    IDP_SUPERUSER_GROUPS={},
)
def test_other_providers_still_see_legacy_meaning(user):
    sync_idp_permissions(user, ["shared"], provider="corp-okta")
    assert _envs(user) == [("prod", "viewer")]


@override_settings(
    IDP_GROUP_MAPPING={},
    OKTA_GROUP_MAPPING={"g": {"dev": "deployer"}},
    OKTA_SUPERUSER_GROUPS=[],
    IDP_SUPERUSER_GROUPS={},
)
def test_no_provider_uses_unscoped_mapping(user):
    """The Robot keyword calls the two-argument form with no provider."""
    sync_idp_permissions(user, ["g"])
    assert _envs(user) == [("dev", "deployer")]


def test_legacy_alias_is_still_exported():
    """test/resources/PermissionSeed.py imports this name."""
    from deployments.group_sync import sync_okta_permissions

    assert sync_okta_permissions is sync_idp_permissions
