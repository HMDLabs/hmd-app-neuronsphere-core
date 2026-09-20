.. NERD001 Environment BOM View

NERD001 Environment BOM View
=============================

.. req:: Display deployed instances in an environment with BOM, dependency diagrams, and instance details.
    :id: HMD_APP_NEURONSPHERE_NERD001
    :status: proposed

    The GUI shall provide an Environment BOM (Bill of Materials) view that shows all currently deployed
    instances in a given Environment. Users can view instances as a sortable table or interactive dependency
    graph, drill into instance details, and compare environments side-by-side. All data is sourced from
    hmd-ms-deployment REST API endpoints.

Table View
----------

.. spec:: Sortable, filterable table of deployed instances with key metadata columns.
    :id: HMD_APP_NEURONSPHERE_NERD001_SPEC001
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD001

    The BOM table view shall display deployed instances with the following columns:

    - Instance Name
    - RepoClass
    - Version (RepoClassVersion)
    - Status (DEPLOYED, DEPLOY_NEXT, FAILED, etc.)
    - Last Deployed timestamp
    - Deployment ID link

    All columns shall be sortable and filterable. Data is fetched via
    ``GET /apiop/get_deployment_bom/<environment_type>``.

DAG View
--------

.. spec:: Interactive dependency graph visualization with status-colored nodes and click-to-detail.
    :id: HMD_APP_NEURONSPHERE_NERD001_SPEC002
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD001

    The BOM DAG view shall render an interactive dependency graph using D3.js or Cytoscape.js.
    Data is fetched via ``GET /apiop/get_deployment_info/<environment_type>``.

    Features:

    - Nodes colored by deployment status
    - Click node to view instance details
    - Zoom/pan navigation
    - Filter by RepoClass type

Instance Detail Panel
---------------------

.. spec:: Instance detail panel showing merged config, dependencies, history, and RBAC-gated actions.
    :id: HMD_APP_NEURONSPHERE_NERD001_SPEC003
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD001

    Clicking an instance (in either table or DAG view) shall open a detail panel displaying:

    - Current configuration (merged default + instance config) via ``get_deployment_config``
    - Dependency list with versions
    - Deployment history via ``GET /apiop/get_deployment_history/<environment_type>/<instance_name>``
    - Quick actions (Edit, Redeploy, Destroy) gated by RBAC role

Environment Comparison
----------------------

.. spec:: Side-by-side environment comparison with config diff and ChangeSet generation from differences.
    :id: HMD_APP_NEURONSPHERE_NERD001_SPEC004
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD001

    The GUI shall provide an Environment Comparison view using ``POST /apiop/compare_environments``.

    Features:

    - Environment selector (source vs target)
    - Diff display showing instances only in source, only in target, and version/config differences
    - Side-by-side JSON configuration diff with highlighting
    - Generate ChangeSet from selected differences with options:

      - Configuration only (same version, different config)
      - Full sync (update version and config)
      - Include dependencies (cascading updates)

    - Generated ChangeSets are deployment-set-agnostic; the user picks a target
      DeploymentSet when applying.
