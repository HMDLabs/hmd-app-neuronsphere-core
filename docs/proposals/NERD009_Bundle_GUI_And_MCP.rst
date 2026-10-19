.. NERD009 Bundle GUI and MCP Surface

NERD009 Bundle GUI and MCP Surface
========================================================

.. req:: Bundle GUI and MCP Surface
    :id: HMD_APP_NEURONSPHERE_NERD009
    :status: proposed

    ``NERD0010_HMD_MS_DEPLOYMENT`` introduces a **Bundle** — a versioned grouping of RepoClasses
    that resolves against an environment and expands into a ``ChangeSet`` in one operation. Add
    the GUI views to browse Bundles and their declared roles, a "Deploy Bundle" action that turns
    a resolved Bundle into a reviewable ``ChangeSet``, and three read-only MCP tools so an agent
    can discover, describe, and dry-run-preview a Bundle's resolution without ever triggering a
    deploy.

    GUI mutation — creating and applying a ``ChangeSet`` from a Bundle — shall reuse the existing
    ``ChangeSetDraft`` review/validate/apply pipeline unmodified rather than introducing a second
    apply path. The MCP surface shall preserve the read-only invariant established by
    ``HMD_APP_NEURONSPHERE_NERD008``: no Bundle tool creates, validates, or applies a
    ``ChangeSet``, no matter how convenient a one-call "just deploy it" tool would be for an
    agent to use.

Revision 2026-10-05: reuse is a decision, and the open-core split
-----------------------------------------------------------------

``NERD0010_HMD_MS_DEPLOYMENT`` is now implemented, and two things it settled change this
document.

**Reuse is a decision the operator makes, not a default the GUI reviews.** The service no longer
auto-reuses. A deployed instance that overlaps a role -- the same ``repo_class_name``, or providing
the role's ``resource`` -- is a *candidate*, and the role is ``decision_required`` until the caller
passes ``overrides.<role>.reuse`` (an instance) or ``overrides.<role>.new`` (deploy anyway,
optionally under ``instance_name``). ``POST /apiop/find_bundle_reuse`` reports, per role, the
candidates (each with ``matched_by`` -- ``repo_class`` / ``resource`` -- version and status), the
roles awaiting a decision, and the reusable ones, without generating anything. Roles also carry
``provision`` (``"false"``: reuse-only shared infrastructure, never provisioned, its single
candidate taken), ``dedicated`` (``"true"``: the bundle's own bucket or credentials, no
candidates) and list-valued ``bind``. Consequently:

- **SPEC002 gains a decision step.** ``bundle_deploy_preview`` first calls ``find_bundle_reuse``
  and renders a *decisions* form -- one row per role with candidates: reuse which instance, or
  deploy new under what name -- pre-filled for roles that need none (own-name reuse, a reuse-only
  role's single candidate). Only when every ``decision_required`` role is answered does it call
  ``generate_bundle_changeset`` with those ``overrides`` and create the ``ChangeSetDraft``. A
  required reuse-only role with no candidate (a lower layer not yet deployed) is shown as
  blocking, naming the bundle that provides it, rather than offered as "deploy new".
- **SPEC003 records decisions instead of offering to undo auto-reuse.** ``bundle_metadata`` stores
  the ``overrides`` the operator chose alongside the ``resolution``; the review partial shows them
  as the operator's decisions. Changing one returns to SPEC002's decision step -- the draft's
  definition is regenerated, not edited by hand.
- **SPEC005** adds ``find_bundle_reuse``; registration moved from per-bundle ``hmd-bundle-*`` repos
  to ``hmd-bundle-core`` (``meta-data/bundles/*.json``, ``upsert_bundle_versions``) and remains
  outside the GUI.
- **SPEC006/SPEC007:** ``describe_bundle`` shows ``provision`` and ``dedicated`` per role, and a new
  read-only, environment-scoped MCP tool ``find_bundle_reuse`` (``environment_arg="environment"``)
  returns the service's answer verbatim. ``preview_bundle_changeset`` takes ``overrides``; called
  without them on an environment with overlaps it returns the ``decision_required`` errors, which
  is the agent's cue to ask the human.

**The GUI is split like the service** (``NERD0015_HMD_MS_DEPLOYMENT``): ``hmd-app-neuronsphere-core``
holds the catalog and read views, and this repository is the premium overlay (``deployments_premium``)
that adds views needing premium routes. The paths above (``deployments/views.py``,
``deployments/services/api_client.py``) now live in core. Placement follows the route each view
calls: the bundle catalog and detail views (SPEC001) and ``find_bundle_reuse`` are core;
``bundle_deploy_preview`` (SPEC002), which calls the premium ``generate_bundle_changeset``, is
overlay, hidden when the service serves only the core routes.

Releases, which build on bundles, are specified in ``HMD_APP_NEURONSPHERE_NERD011``.

A Bundle is only useful here if resolving one looks, to both a human and a reviewer, exactly like
resolving any other ``ChangeSet`` — because it *is* one, generated rather than hand-assembled.
The GUI additions below therefore add a discovery surface (list/detail views) and one new
producer of a ``ChangeSetDraft`` (the deploy-preview action); they add no new apply code. The MCP
additions mirror ``NERD008``'s existing tools one level up, at Bundle scope, and stop exactly
where a write would begin.

.. spec:: Bundle catalog and detail views
    :id: HMD_APP_NEURONSPHERE_NERD009_SPEC001
    :links: HMD_APP_NEURONSPHERE_NERD009
    :status: proposed

    Add ``bundle_list``, ``bundle_detail``, and ``bundle_version_detail`` views in
    ``deployments/views.py``, with routes in ``deployments/urls.py``, mirroring
    ``resource_definition_list``/``resource_definition_detail``/``repo_class_detail``
    (``views.py:1529-1720``). ``bundle_version_detail`` shall render the declared role table —
    named-class suggestion, resource requirement, required/optional, ``version_spec``,
    ``tag_selector`` — and the raw ``config_schema``. All three are platform-wide catalog reads,
    decorated with ``@login_required`` only, not environment-scoped.

.. spec:: Deploy Bundle preview action
    :id: HMD_APP_NEURONSPHERE_NERD009_SPEC002
    :links: HMD_APP_NEURONSPHERE_NERD009
    :status: proposed

    Add a ``bundle_deploy_preview`` view — ``@login_required``, ``@require_POST``, and
    ``@require_environment_access("viewer", param="environment")`` (never bare
    ``@login_required``; see ``HMD_APP_NEURONSPHERE_NERD008_SPEC013`` for the class of bug this
    guards against), audited the same way changeset-creating views already are — mirroring
    ``environment_compare_create_changeset`` (``views.py:946-990``). It reads ``environment``,
    ``version``/``version_spec``, and a ``configuration`` payload from the POST body, calls a new
    ``client.generate_bundle_changeset(...)`` API-client method wrapping
    ``NERD0010_HMD_MS_DEPLOYMENT_SPEC0006``'s operation, and on success creates a
    ``ChangeSetDraft`` (``deployments/models.py:222``) from the returned ``definition``, then
    redirects into the existing ``changeset_draft``/``changeset_review``/``changeset_validate``/
    ``changeset_apply`` pipeline (``views.py:547-735``). No new apply code path is introduced — a
    Bundle deploy is reviewed and applied exactly as any hand-built ``ChangeSet`` is.

.. spec:: Bundle resolution surfaced on ChangeSet review
    :id: HMD_APP_NEURONSPHERE_NERD009_SPEC003
    :links: HMD_APP_NEURONSPHERE_NERD009
    :status: proposed

    Add a nullable ``bundle_metadata`` JSON field to ``ChangeSetDraft`` (a small additive
    migration), populated by SPEC0002 with ``{"bundle_name", "version", "resolution": [...]}`` —
    the same per-role resolution ``generate_bundle_changeset`` returns. Extend
    ``changeset_review.html`` with a partial that renders the reuse-vs-new decision per role when
    ``bundle_metadata`` is present. This is where a human reviews and can override the
    resolution — reject a reused instance, force a fresh one — before ``changeset_apply`` runs,
    satisfying ``NERD0010``'s requirement that auto-reuse always be surfaced for review before
    anything is applied.

.. spec:: Sidebar navigation
    :id: HMD_APP_NEURONSPHERE_NERD009_SPEC004
    :links: HMD_APP_NEURONSPHERE_NERD009
    :status: proposed

    Add a "Bundles" entry to ``deployments/templates/deployments/partials/sidebar.html``,
    adjacent to the existing "Repo Classes" and "Resources" entries, linking to ``bundle_list``.

.. spec:: API client methods
    :id: HMD_APP_NEURONSPHERE_NERD009_SPEC005
    :links: HMD_APP_NEURONSPHERE_NERD009
    :status: proposed

    Add ``list_bundles``, ``get_bundle``, ``list_bundle_versions``, ``get_bundle_version``, and
    ``generate_bundle_changeset`` to ``deployments/services/api_client.py``, following the
    existing ``list_resource_definitions``/``get_resource_definition`` request/response
    conventions. No new upsert method is needed on this side — Bundle *registration*
    (``upsert_bundle_version``) is performed by an ``hmd-bundle-*`` repo's own CI deploy step
    directly against ``hmd-ms-deployment``, not through this GUI.

.. spec:: MCP tools -- list_bundles and describe_bundle
    :id: HMD_APP_NEURONSPHERE_NERD009_SPEC006
    :links: HMD_APP_NEURONSPHERE_NERD009
    :status: proposed

    Add a new ``ns_mcp/tools/bundles.py`` module. ``list_bundles`` and ``describe_bundle`` are
    platform-wide, read-only tools carrying no ``environment_arg`` — mirroring
    ``list_resource_definitions``/``find_resource_providers`` in ``ns_mcp/tools/resources.py``.
    ``describe_bundle`` returns a bundle version's ``config_schema``, ``default_configuration``,
    and full role table by calling the same ``deployments/services/`` helper
    ``bundle_version_detail`` (SPEC0001) calls, per ``HMD_APP_NEURONSPHERE_NERD008_SPEC001``'s
    rule that no MCP tool reimplements a query the GUI already performs.

.. spec:: MCP tool -- preview_bundle_changeset
    :id: HMD_APP_NEURONSPHERE_NERD009_SPEC007
    :links: HMD_APP_NEURONSPHERE_NERD009
    :status: proposed

    Add ``preview_bundle_changeset``, an environment-scoped read-only tool declaring
    ``environment_arg="environment"`` so ``assert_environment_access`` gates it exactly as it
    gates ``find_resource_candidates``. It calls the same ``generate_bundle_changeset`` operation
    the GUI's ``bundle_deploy_preview`` calls (SPEC0002) and returns its ``resolution`` and
    ``definition`` verbatim. It shall never create a ``ChangeSetDraft``, never persist a
    ``ChangeSet``, and never call ``apply_changeset`` — it is the dry-run counterpart to the
    GUI's mutating preview action. The GUI mutates because a human is about to act on the result
    next; the MCP tool does not, because nothing here should let an agent trigger a deploy by
    calling a "preview" tool.

.. spec:: Registration
    :id: HMD_APP_NEURONSPHERE_NERD009_SPEC008
    :links: HMD_APP_NEURONSPHERE_NERD009
    :status: proposed

    Add ``"ns_mcp.tools.bundles"`` to ``MCP_TOOL_MODULES``
    (``deployment_gui/settings/base.py:265-278``); ``register(mcp)`` returns
    ``["list_bundles", "describe_bundle", "preview_bundle_changeset"]``. No change to
    ``server.py`` is required, per the registry's existing extension contract.

.. spec:: Test coverage
    :id: HMD_APP_NEURONSPHERE_NERD009_SPEC009
    :links: HMD_APP_NEURONSPHERE_NERD009
    :status: proposed

    Tests shall cover: view-level authorization (the catalog views require login only;
    ``bundle_deploy_preview`` denies a viewer without environment access, exercising the same
    regression class ``HMD_APP_NEURONSPHERE_NERD008_SPEC013`` closed); ``ChangeSetDraft``
    creation from a ``generate_bundle_changeset`` response feeding unmodified into the existing
    review/validate/apply views; and MCP-level authorization parity with
    ``HMD_APP_NEURONSPHERE_NERD008_SPEC003`` for all three new tools, including the structural
    "any tool taking an ``environment`` parameter must declare ``environment_arg``" test that
    already covers every module listed in ``MCP_TOOL_MODULES``.

Related proposals
------------------

``NERD0010_HMD_MS_DEPLOYMENT`` (in ``hmd-ms-deployment``) defines the ``Bundle``/``BundleVersion``
data model, the dependency-role resolution and reuse policy, and the
``generate_bundle_changeset``/``upsert_bundle_version`` operations this NERD's views and tools
call.
