.. NERD002 ChangeSet Creation

NERD002 ChangeSet Creation
===========================

.. req:: Create, review, and apply ChangeSets to modify deployments through the GUI.
    :id: HMD_APP_NEURONSPHERE_NERD002
    :status: proposed

    The GUI shall allow users to build ChangeSets as portable bundles of instance definitions —
    independent of any specific environment or DeploymentSet — and apply them to one or more
    DeploymentSets via the hmd-ms-deployment API. Drafts are deployment-set-agnostic: a single
    draft can be applied to multiple DeploymentSets, and a Clone operation produces a new draft
    for cases where the bundle needs to be rewired for a different target.

Edit Mode on BOM View
---------------------

.. spec:: Click-to-modify edit mode with session-based draft tracking and color-coded review panel.
    :id: HMD_APP_NEURONSPHERE_NERD002_SPEC001
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD002

    Entering edit mode on the BOM view shall allow users to click an instance to modify it.
    Changes are tracked in a session-based ChangeSet draft (persisted via Django ``ChangeSetDraft`` model).

    A review panel shall display pending changes with color coding:

    - Green: newly added instances
    - Yellow: modified instances
    - Red: instances marked for destruction

Add Instance Wizard
-------------------

.. spec:: Add a new instance from RepoClass + version, configure it, and wire dependencies via a first-class picker.
    :id: HMD_APP_NEURONSPHERE_NERD002_SPEC002
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD002

    Adding an instance is a creation-first form on the draft page:

    1. Enter Instance Name, RepoClass, Version (with autocomplete from
       ``POST /apiop/find_repo_class_versions/<name>``), and Deployment ID
       (defaults to ``aaa`` for new instances).
    2. Configure (pre-populated with defaults from ``default_configuration``).
    3. Wire **Dependencies** through a first-class picker: for each role declared by the
       RepoClassVersion, the user may pick either (a) another instance defined within this
       same ChangeSet draft, or (b) an existing instance from a chosen DeploymentSet's BOM.

    A **Copy Instance** option shall allow cloning an existing instance with a new name,
    optionally updating the version.

Dynamic Configuration Form
--------------------------

.. spec:: Configuration form dynamically generated from default_configuration with field type inference and validation.
    :id: HMD_APP_NEURONSPHERE_NERD002_SPEC003
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD002

    The configuration form for a RepoClassVersion shall be dynamically generated from the
    ``default_configuration`` in the version's manifest. Field types shall be inferred from
    JSON schema or value types (string, boolean, number, object, array). Client-side validation
    shall be applied before submission.

ChangeSet Review and Application
--------------------------------

.. note::

    Applying a ChangeSet (steps 1-3 below) is premium-only. ``POST
    /apiop/apply_changeset`` is registered by ``hmd-ms-deployment``'s
    ``deployment_ops.py`` and is not present in the open-core
    ``hmd-ms-deployment-core`` service, so this GUI (``hmd-app-neuronsphere-core``)
    has no view, URL, or API client method that calls it. See
    ``hmd-ms-deployment``'s ``docs/proposals/NERD0015_CoreAndPremiumSplit.rst`` for
    the core/premium boundary. The open-core GUI implements drafting, validation,
    review, clone, reject, and reopen only; the flow below is implemented by the
    premium overlay, ``hmd-app-neuronsphere``.

.. spec:: Review panel displaying full ChangeSet JSON; apply via modal that chooses a DeploymentSet at apply time.
    :id: HMD_APP_NEURONSPHERE_NERD002_SPEC004
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD002

    The review panel shall display the complete ChangeSet JSON matching the
    ``hmd-lang-deployment.change_set`` schema. Applying opens a modal that prompts the user for a
    DeploymentSet (e.g. ``Admin``) and then:

    1. Upserts the ChangeSet entity to the backend via
       ``POST /api/hmd_lang_deployment.change_set``.
    2. Calls ``POST /apiop/apply_changeset`` with the chosen DeploymentSet name.
    3. Records a ``ChangeSetApplication`` row capturing the target DeploymentSet,
       the returned ChangeSetDeployment ID, and who applied it.

    Additional features:

    - **Cascade Selection**: Select an ancestor instance to automatically include all downstream
      dependents in the ChangeSet.

.. spec:: ChangeSets are deployment-set-agnostic; Apply may be invoked multiple times for different DeploymentSets, and Clone produces a content copy for editing.
    :id: HMD_APP_NEURONSPHERE_NERD002_SPEC006
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD002

    A ChangeSet draft does not carry a target environment or DeploymentSet. The same draft may be
    applied to multiple DeploymentSets; each application is recorded as a ``ChangeSetApplication``
    row. The first successful apply transitions the draft status to ``ACCEPTED``, but subsequent
    applies are still allowed for additional DeploymentSets.

    To target a different DeploymentSet with different content (e.g. re-wired dependencies for a
    different region), the user clicks **Clone**: a new draft is created with ``status=DRAFT``
    and the source draft's ``content`` copied verbatim — no BOM-based instance name remapping.

ChangeSet Validation
--------------------

.. spec:: Pre-submission validation including dependency resolution, version compatibility, and circular dependency detection.
    :id: HMD_APP_NEURONSPHERE_NERD002_SPEC005
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD002

    Before submission, the GUI shall validate the ChangeSet by calling
    ``POST /apiop/validate_changeset``. Validation checks include:

    - Dependency resolution (all required dependencies present)
    - Version compatibility (version specs satisfied)
    - Circular dependency detection

    Errors shall block submission; warnings shall be displayed but allow submission.

    *Requires new* ``POST /apiop/validate_changeset`` *endpoint in hmd-ms-deployment.*
