.. NERD006 Okta Group-to-Role Mapping

NERD006 Okta Group-to-Role Mapping
===================================

.. req:: Map Okta group claims to environment-level RBAC permissions via deploy-time configuration.
    :id: HMD_APP_NEURONSPHERE_NERD006
    :status: proposed

    The GUI shall support Okta OIDC group-based role assignment for cloud deployments. When a user
    logs in via Okta, their OIDC ``groups`` claim is resolved against a deploy-time configuration
    mapping (``OKTA_GROUP_MAPPING``) to assign environment-level permissions. Local development
    continues to use email/password authentication with manually-assigned permissions.

Authentication Modes
--------------------

.. spec:: Dual authentication: Okta OIDC for cloud, email/password for local development.
    :id: HMD_APP_NEURONSPHERE_NERD006_SPEC001
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD006

    The application supports two authentication modes:

    - **Cloud (production):** Okta OIDC via django-allauth. ``SOCIALACCOUNT_ONLY = True`` disables
      local username/password login. Users authenticate through Okta's hosted login page.
    - **Local (development):** Django's ``ModelBackend`` provides email/password login.
      No Okta integration required.

    The authentication mode is determined by the Django settings module
    (``deployment_gui.settings.production`` vs ``deployment_gui.settings.development``).

Group-to-Permission Configuration
---------------------------------

.. spec:: Deploy-time JSON configuration mapping Okta group names to environment+role pairs.
    :id: HMD_APP_NEURONSPHERE_NERD006_SPEC002
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD006

    The ``OKTA_GROUP_MAPPING`` environment variable provides a JSON object mapping Okta group names
    to environment-role pairs. Okta groups are provisioned via CDKTF; this mapping is set at deploy
    time (Helm values / ConfigMap).

    **Format:**

    .. code-block:: json

        {
            "ns-dev-deployers": {"dev": "deployer"},
            "ns-prod-admins": {"prod": "admin", "dev": "admin"},
            "ns-viewers": {"dev": "viewer", "test": "viewer", "prod": "viewer"}
        }

    **Rules:**

    - Each key is an Okta group name as it appears in the OIDC ``groups`` claim.
    - Each value maps environment names to roles (``viewer``, ``deployer``, ``admin``).
    - When a user belongs to multiple groups granting different roles for the same environment,
      the highest role wins (admin > deployer > viewer).
    - If ``OKTA_GROUP_MAPPING`` is empty or not set, group sync is a no-op.

Permission Source Tracking
--------------------------

.. spec:: UserEnvironmentPermission tracks whether a permission was manually assigned or synced from Okta.
    :id: HMD_APP_NEURONSPHERE_NERD006_SPEC003
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD006

    The ``UserEnvironmentPermission`` model includes a ``source`` field with values:

    - ``manual`` — Assigned directly by an administrator (default).
    - ``okta`` — Synced from Okta group claims on login.

    The unique constraint is ``(user, environment, source)``, allowing a user to have both a manual
    and an Okta-sourced permission for the same environment. Permission checks query all records
    for the user regardless of source; the highest role across all sources is effective.

Okta Group Sync on Login
-------------------------

.. spec:: On Okta login, sync user's group claims to Okta-sourced environment permissions.
    :id: HMD_APP_NEURONSPHERE_NERD006_SPEC004
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD006

    When a user logs in via Okta OIDC, the following sync occurs:

    1. Extract the ``groups`` claim from the OIDC token (``sociallogin.account.extra_data``).
    2. Resolve groups against ``OKTA_GROUP_MAPPING`` to determine target permissions.
    3. Delete all existing ``UserEnvironmentPermission`` records with ``source=okta`` for the user.
    4. Create new records for the resolved permissions with ``source=okta``.
    5. Log the sync operation to ``AuditLog`` with action ``group_sync``.

    **Authoritative behavior:** Okta sync replaces only Okta-sourced permissions. Manually-assigned
    permissions are never modified by the sync process. If a user is removed from an Okta group,
    their next login will remove the corresponding Okta-sourced permission.

    **Graceful degradation:** If the ``groups`` claim is absent from the token (Okta authorization
    server not configured), the sync is skipped. If ``OKTA_GROUP_MAPPING`` is empty, the sync is
    a no-op. Existing permissions are not affected in either case.

Okta Authorization Server Prerequisites
----------------------------------------

.. spec:: Okta authorization server must include a groups claim in the ID token.
    :id: HMD_APP_NEURONSPHERE_NERD006_SPEC005
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD006

    The following must be configured in Okta (typically via CDKTF):

    - A custom claim named ``groups`` on the authorization server, returning group names.
    - The ``groups`` scope added to the application's allowed scopes.
    - Okta groups created and users assigned to them.

    The OIDC client configuration in Django requests the ``groups`` scope via
    ``SOCIALACCOUNT_PROVIDERS`` token parameters.

Audit Logging
-------------

.. spec:: All Okta group sync operations are logged to the audit trail.
    :id: HMD_APP_NEURONSPHERE_NERD006_SPEC006
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD006

    Each Okta group sync creates an ``AuditLog`` entry with:

    - ``action``: ``group_sync``
    - ``target``: ``user:<username>``
    - ``details``: JSON containing matched Okta groups, permissions deleted count,
      and permissions created (environment + role pairs).
    - ``ip_address`` and ``user_agent`` from the login request.
