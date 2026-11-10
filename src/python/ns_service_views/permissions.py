"""Which views a caller may see (NERD007 SPEC005).

A service publishes ``group_permissions`` (real group name -> permissions) in its
view-set, resolved at deploy time; the service itself checks callers with
hmd-lib-auth's ``permissions_for`` and that same map. ``permissions_for`` here
is a copy, not an import: this app depends on no hmd library. The two must
resolve identically, so tests hold this copy to hmd-lib-auth's test cases.
"""

import logging
from typing import Dict, Iterable, List, Mapping, Optional, Set, Union

from django.conf import settings

logger = logging.getLogger(__name__)


def permissions_for(
    groups: Optional[Union[str, Iterable[str]]],
    group_permissions: Optional[Mapping[str, Iterable[str]]],
) -> Set[str]:
    """The union of the permissions granted by each of ``groups``; exact names;
    a bare string is one group. Mirrors ``hmd_lib_auth.permissions``."""
    if not groups or not group_permissions:
        return set()
    if isinstance(groups, str):
        groups = [groups]
    granted = set()
    for group in groups:
        granted.update(group_permissions.get(group, ()))
    return granted


def enforcing() -> bool:
    """Filter by permission only when users sign in through an IdP. Without
    one (local development) services skip their own check too, under
    AUTHORIZATION=NONE, so hiding views here would hide what they serve."""
    default = bool(getattr(settings, "SOCIALACCOUNT_PROVIDERS", None))
    return getattr(settings, "SERVICE_VIEWS_ENFORCE_PERMISSIONS", default)


def missing_permissions(view: Dict, granted: Set[str]) -> List[str]:
    return [p for p in view.get("required_permissions") or [] if p not in granted]


def visible_views(service, groups, enforce: Optional[bool] = None) -> List[Dict]:
    if enforce is None:
        enforce = enforcing()
    if not enforce:
        return list(service.views)
    granted = permissions_for(groups, service.group_permissions)
    return [v for v in service.views if not missing_permissions(v, granted)]


def user_groups(user) -> List[str]:
    """The caller's IdP groups, from the claims stored at sign-in."""
    from deployments.adapters import extract_groups, groups_claim_for
    from deployments.services.auth import get_okta_social_account

    account = get_okta_social_account(user)
    if account is None:
        return []
    return extract_groups(account.extra_data or {}, groups_claim_for(account.provider))


def user_bearer_token(user) -> Optional[str]:
    """The caller's own IdP access token, forwarded so the service authorizes
    the end user, never the GUI's service account (NERD007 SPEC003)."""
    from deployments.services.auth import get_okta_social_token

    token = get_okta_social_token(user)
    return token.token if token is not None else None
