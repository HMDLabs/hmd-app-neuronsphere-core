.. NERD017 Environment Roles From Identity

NERD017 Environment Roles From Identity
=======================================

.. req:: The GUI and the MCP gateway read what a person may reach in each environment from identity, and every environment enforces it
    :id: HMD_APP_NEURONSPHERE_NERD017
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD012, HMD_APP_NEURONSPHERE_NERD006, HMD_MS_IDENTITY_NERD004

    The GUI and the MCP gateway shall learn a person's roles in each environment from
    ``hmd-ms-identity``, in place of the ``UserEnvironmentPermission`` table that the GUI
    fills from the identity provider's groups when someone signs in. They shall show a person
    only the environments where they hold a role, show a platform administrator
    distinctly, and treat a refusal from an environment as final. Where the gateway forwards
    the person's own token, the upstream environment shall decide access
    (``HMD_MS_IDENTITY_NERD004``), and the gateway shall not rely on its own check alone.

Motivation
----------

``HMD_APP_NEURONSPHERE_NERD012`` was written for a platform in which an environment trusts
every token the shared identity provider tenant issues, and the GUI is the one place that
decides who may reach which environment. Its upstream lockdown (``SPEC007``) says that every
environment shares one tenant, so a user's own token verifies against every environment's
keys, and its closing paragraph allows ``passthrough`` for "upstreams that enforce their own
per-user authorization".

Two things in that picture are no longer enough.

**The role source is local to the GUI.** ``assert_environment_access`` consults
``UserEnvironmentPermission`` (``HMD_APP_NEURONSPHERE_NERD006``), rows that the GUI creates
from an ``OKTA_GROUP_MAPPING`` the first time and every time a person signs in through the
web. Consequences:

- a person who uses only the MCP endpoint with a bearer token, and has not signed in to the
  web recently, has whatever the last web login wrote, and loses nothing until they next
  sign in. A removal in the provider takes effect at the person's next web login;
- the table is the second record of who holds which role, next to identity's view of the
  provider's groups (``HMD_MS_IDENTITY_NERD002``, ``HMD_MS_IDENTITY_NERD003``);
- the mapping names only ``viewer``, ``deployer`` and ``admin`` per environment. It cannot
  name the roles of individual services, which is what ``HMD_MS_IDENTITY_NERD004`` enforces;
- a Django superuser, whose flag is reconciled from provider groups, short-circuits every
  check and sees every environment.

**A valid token is not authority.** With ``passthrough``, the gateway forwards the caller's
token, and the upstream has to authorize it. Today that works only inside one environment,
because an environment accepts a person's token only from its own client or a trusted
client. As soon as an environment accepts tokens minted for the control plane's app, a
signature check passes for every person who can sign in. The statement "``passthrough`` is
safe for upstreams that enforce per-user authorization" is true only if upstreams really do
enforce it, per environment, from the person's roles in that environment. That is what
``HMD_MS_IDENTITY_NERD004`` adds. This NERD changes the app side to match.

Principles
----------

- **One source.** A person's roles in an environment come from identity. The GUI keeps no
  second table that decides access.
- **Trust is not access.** The GUI and the gateway may rely on a token's signature. They never
  treat it as permission, and they do not assume a token that verifies in one environment is
  welcome in another.
- **The environment has the last word.** For a call that carries the person's token, the
  environment that owns the service decides. The gateway's own check is an earlier, friendlier
  refusal. It is never the only one, except for ``service``-mode upstreams, where the
  gateway's check is the control and is held to the same standard.
- **Fail closed.** If roles cannot be read, or are stale, the person sees no environment and
  makes no call.
- **Say who refused.** A refusal is shown as a refusal by a named environment, not as an
  error that invites a retry.

.. spec:: Roles are read from identity
    :id: HMD_APP_NEURONSPHERE_NERD017_SPEC001
    :links: HMD_APP_NEURONSPHERE_NERD017, HMD_MS_IDENTITY_NERD003_SPEC008, HMD_MS_IDENTITY_NERD003_SPEC006
    :status: proposed

    ``user_has_environment_access``, ``assert_environment_access`` and
    ``get_user_environments`` shall obtain a person's roles in an environment from
    ``hmd-ms-identity`` and not from ``UserEnvironmentPermission``.

    - The call is ``GET /apiop/me/access`` (``HMD_MS_IDENTITY_NERD003_SPEC008``), made with the
      caller's own token. It returns the person's roles for every environment in one answer,
      each with the oldest ``observed_at`` behind it.
    - The answer is cached per person for a short time, not longer than 60 seconds, and is
      never cached across people. A refresh is made on a cache miss and is shared by
      concurrent requests from the same person. The cache is held in the shared cache where
      one is configured, so gunicorn workers do not each ask.
    - A person holds a role in an environment when the answer lists at least one role
      group (``kind`` ``app-role``) of any service in it. Access to an environment is
      therefore "holds a role there". ``HMD_APP_NEURONSPHERE_NERD006``'s ``viewer``,
      ``deployer`` and ``admin`` are mapped from role names by a deploy-time setting, see
      the open questions.
    - If identity cannot be reached, or returns an answer older than the same freshness
      limit the environments use, the person has no access to any environment and sees an
      error that says the roles could not be confirmed. Previously cached answers are used
      for no longer than their cache time and are never used to extend access past that.
    - The gateway and the GUI share one implementation, so the two cannot disagree.

.. spec:: Environment list
    :id: HMD_APP_NEURONSPHERE_NERD017_SPEC002
    :links: HMD_APP_NEURONSPHERE_NERD017, HMD_APP_NEURONSPHERE_NERD017_SPEC001, HMD_APP_NEURONSPHERE_NERD012_SPEC003
    :status: proposed

    Every place that lists environments for a person shall list only the environments where
    they hold a role. That covers the environment switcher and the pages that start from it,
    the ``environment`` argument's ``enum`` on each gateway tool
    (``HMD_APP_NEURONSPHERE_NERD012_SPEC003``), the discovery listing and
    ``list_mcp_servers``, and the native MCP tools.

    - An environment where the person holds no role is not listed, and a request that names
      it is refused as if it did not exist, so the existence of an environment is not
      disclosed to someone with no role in it.
    - A person with no role in any environment sees an empty list and a plain message saying
      so, and the name of whom to ask is a deploy-time setting. They are not shown an error.
    - The list comes from the intersection of the environments the deployment service knows
      and the environments identity reports. A role in an environment that is not deployed
      is ignored.

.. spec:: Platform administrator
    :id: HMD_APP_NEURONSPHERE_NERD017_SPEC003
    :links: HMD_APP_NEURONSPHERE_NERD017, HMD_MS_IDENTITY_NERD004_SPEC008, HMD_MS_IDENTITY_NERD003_SPEC006
    :status: proposed

    A person who is a member of an environment's ``platform-admin`` role group
    (``HMD_MS_IDENTITY_NERD004_SPEC008``) has ``platform_admin`` set for that environment in
    identity's answer. The GUI and the gateway shall:

    - show that person that environment in the list, marked as reached as platform
      administrator, so that it is never mistaken for an ordinary grant. The marking is
      shown wherever the environment's name is shown in a switcher, not only in a settings
      page;
    - treat ``platform_admin`` as applying to that environment only. Holding it in one
      environment gives nothing in any other;
    - record in the audit entry of every action (``AuditLog``, ``transport: mcp-gateway`` or
      web) whether it was authorized by an ordinary role or by ``platform_admin`` alone. An
      action that an ordinary role also allows is recorded as ordinary;
    - never grant ``platform_admin`` from a Django superuser flag or from a local table
      (see ``HMD_APP_NEURONSPHERE_NERD017_SPEC006``).

.. spec:: Passthrough is safe because environments enforce
    :id: HMD_APP_NEURONSPHERE_NERD017_SPEC004
    :links: HMD_APP_NEURONSPHERE_NERD017, HMD_APP_NEURONSPHERE_NERD012_SPEC004, HMD_APP_NEURONSPHERE_NERD012_SPEC007, HMD_MS_IDENTITY_NERD004_SPEC001
    :status: proposed

    This corrects two statements in ``HMD_APP_NEURONSPHERE_NERD012_SPEC007``.

    *One tenant does not mean one trust domain for access.* Every environment still shares
    one identity provider tenant, and a person's token still verifies against each
    environment's keys. That is **trust**: it shows the token is authentic. It does not show
    that the person may use the environment. Nothing in the gateway, or in an upstream, shall
    treat a token that verifies as permission. Permission is a role in the environment that
    owns the service.

    *Passthrough is safe only because the upstream enforces.* A ``passthrough`` upstream
    receives the person's own bearer. That is safe when, and only when, the upstream
    environment enforces access for human tokens from the person's roles in *that*
    environment (``HMD_MS_IDENTITY_NERD004_SPEC001``) and refuses a token with no such role.
    A server whose upstream does not enforce shall not be registered as ``passthrough``. The
    registry shall refuse the setting for an upstream not marked as enforcing, and the
    marking comes from the deployment record of the service's access mode
    (``HMD_MS_IDENTITY_NERD004_SPEC004``) and not from the producer's own output.

    *Service mode stays gateway-enforced.* A ``service`` upstream accepts the gateway's own
    token, which the platform's IdP issued to the gateway's client, and trusts ``X-NS-User``
    (``HMD_APP_NEURONSPHERE_NERD012_SPEC007``). The gateway's check is the control. It shall
    therefore use the same identity roles as above. It shall refuse a call for a person
    whose roles cannot be confirmed, and shall not fall back from ``passthrough`` to
    ``service`` mode to make a refused call succeed.

.. spec:: A refusal from an environment
    :id: HMD_APP_NEURONSPHERE_NERD017_SPEC005
    :links: HMD_APP_NEURONSPHERE_NERD017, HMD_APP_NEURONSPHERE_NERD012_SPEC004, HMD_MS_IDENTITY_NERD004_SPEC007
    :status: proposed

    When an upstream answers a forwarded call with 403, or with 401 for a token that
    verifies, the gateway shall treat it as a final decision by that environment:

    - The caller receives a tool error that names the server and the environment, and says
      the environment refused the person's roles. It says so with the same words whether the
      gateway or the upstream refused, and it carries the audit correlation id. It does not
      include the upstream's body, which may name internals.
    - The gateway shall not retry the call, shall not retry it with the gateway's own
      credential in ``service`` mode, and shall not retry it as a different user or with a
      different token.
    - The cached roles for that person are dropped, so the next call sees current data,
      since a 403 after the gateway allowed the call means the two disagree. The
      disagreement is logged with the person, environment and server, and no token.
    - The 403 is not a signal to open a circuit or to mark the upstream unhealthy. It is a
      healthy answer.
    - A 5xx or a timeout is not a refusal. It is reported as an upstream error, and may be
      retried by the caller.
    - The audit row (``HMD_APP_NEURONSPHERE_NERD012_SPEC003``) records the outcome as
      ``refused-by-environment``, distinct from ``denied`` by the gateway's own check.

    In the web GUI the same refusal appears as an access-denied page for that environment,
    with the same text, and never as a blank or generic error.

.. spec:: Migration from the local table
    :id: HMD_APP_NEURONSPHERE_NERD017_SPEC006
    :links: HMD_APP_NEURONSPHERE_NERD017, HMD_APP_NEURONSPHERE_NERD006_SPEC003, HMD_APP_NEURONSPHERE_NERD006_SPEC004
    :status: proposed

    The change ships in stages, and no stage lets a person see an environment they could not
    see before without an explicit grant.

    1. **Shadow.** The GUI reads identity alongside the table and records every difference
       (an environment the table allows and identity does not, and the reverse), per person
       and without token material. The table still decides. A report of differences is
       available to administrators. Nothing changes for users.
    2. **Resolve differences.** Operators remove access that is only in the table, or add the
       person to the role group in identity. A ``manual`` row
       (``HMD_APP_NEURONSPHERE_NERD006_SPEC003``) has no equivalent in the provider unless it is
       recreated as a ``direct`` membership, so the report lists each one for conversion.
       ``okta``-sourced rows need no action: the group they came from is the same group
       identity reads.
    3. **Cut over.** ``ENVIRONMENT_ROLES_SOURCE`` changes from ``table`` to ``identity``
       (one setting, changed in a ChangeSet, so each environment can go over separately and
       back). Identity decides. The table is still written for one release, so a rollback
       needs no data repair, and is read by nothing.
    4. **Remove.** The group sync on login (``HMD_APP_NEURONSPHERE_NERD006_SPEC004``) and the
       table's role use are removed. The ``OKTA_GROUP_MAPPING`` setting is deprecated. The
       table's historic rows stay in the audit trail.

    **Existing superusers.** A Django superuser (``is_superuser`` is reconciled from the
    provider's ``*_SUPERUSER_GROUPS``) today sees every environment. After cut-over:

    - the flag keeps its Django meaning: access to Django's own admin and the GUI's
      administrative pages that are not about environments;
    - it grants no environment access. A superuser who holds no role in an environment does
      not see it;
    - to keep operational access, a person is made a member of the ``platform-admin`` role
      group in each environment they need, through identity (``HMD_MS_IDENTITY_NERD004_SPEC008``).
      Stage 1's report lists every superuser and the environments they could reach, so the
      operator knows whom to enrol before the cut-over;
    - a local bootstrap account (one with no provider account, created for local development)
      keeps its table-based access only while ``ENVIRONMENT_ROLES_SOURCE`` is ``table``, and
      the ``table`` value is available only in the development settings module. A cloud
      deployment cannot select it.

    ``DeploymentSetPermission`` and ``deploy`` rights beyond viewing are not changed by this
    NERD. See the open questions.

.. spec:: Verification
    :id: HMD_APP_NEURONSPHERE_NERD017_SPEC007
    :links: HMD_APP_NEURONSPHERE_NERD017, HMD_MS_IDENTITY_NERD004_SPEC009
    :status: proposed

    Unit tests shall cover: a person with a role in one environment and none in another; no
    roles at all; identity unreachable; identity data older than the limit; a cache that
    never serves one person's roles to another; a superuser with no role seeing nothing;
    ``platform_admin`` applying to one environment; a 403 from an upstream, which is not
    retried, is reported with the environment's name and drops the cache; and a 5xx, which
    is not reported as a refusal.

    Before any change is deployed to a cloud environment, a local end-to-end run on two
    ``nsctl`` environments, A and B, shall show, with one signed-in person who holds a role
    in A only:

    - the environment switcher, the MCP ``environment`` enum and ``list_mcp_servers`` list A
      and not B;
    - a gateway call naming A succeeds and one naming B is refused before anything leaves the
      gateway;
    - a ``passthrough`` call made straight to B with the same token (bypassing the gateway's
      check) is refused by B with 403, and the gateway reports that as a refusal by B;
    - granting the person a role in B through identity and reconciling makes B appear within
      the freshness limit, with no web login in between;
    - removing the role from A and reconciling makes A disappear and refuses new calls, again
      with no web login;
    - making the person ``platform-admin`` in B alone lists B marked as platform administrator
      and leaves A as before, and the audit rows show which authority applied;
    - with identity stopped, the person sees no environment and receives the "roles could not
      be confirmed" message;
    - a superuser with no role anywhere sees no environment.

Open questions
--------------

- How ``viewer``, ``deployer`` and ``admin`` are derived from identity roles. The simplest
  rule maps role names (``admin`` to ``admin``, ``writer`` to ``deployer``, anything else to
  ``viewer``) per environment from a deploy-time setting. A better one has the deployment
  service declare which service's roles carry deploy rights.
- Whether the app calls identity with the person's own token (``GET /apiop/me/access``) or with
  its own service identity and the admin-restricted query. The first needs no extra privilege.
  The second lets the gateway read roles for an API key's owner, who has no token to forward.
  How API-key callers are given roles at all is not settled here.
- Whether ``DeploymentSetPermission`` follows the same path, and how deployment sets relate
  to environments in identity.
- How long the person's roles may be cached. Sixty seconds is a proposal. A shorter time
  costs identity more calls. A longer one lengthens the window after a removal.
- Whether the environment list should show an environment where the person holds only a role
  for one unrelated service (for example, only the telemetry reader), or whether a separate
  "may see this environment" role is needed.
- Whether the time-bound grant for ``platform-admin`` that ``HMD_MS_IDENTITY_NERD004_SPEC008``
  leaves open should be shown to the person, with an expiry, in the switcher.
