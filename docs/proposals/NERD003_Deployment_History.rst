.. NERD003 Deployment History

NERD003 Deployment History
===========================

.. req:: View deployment history, monitor active deployments, and inspect deployment logs.
    :id: HMD_APP_NEURONSPHERE_NERD003
    :status: proposed

    The GUI shall provide a deployment history view listing recent ChangeSetDeployments with filtering,
    a detail view showing per-environment and per-instance status, a log viewer for deployment output,
    and real-time status updates for in-progress deployments.

Recent Deployments List
-----------------------

.. spec:: Paginated list of ChangeSetDeployments filtered by DeploymentSet, Environment, status, and date range.
    :id: HMD_APP_NEURONSPHERE_NERD003_SPEC001
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD003

    The recent deployments list shall display a paginated list of ChangeSetDeployments with filters for:

    - DeploymentSet
    - Environment
    - Status (CREATED, STARTED, COMPLETED, FAILED, SKIPPED)
    - Date range

    Status badges shall visually distinguish deployment states.

    *Requires new* ``GET /apiop/list_change_set_deployments`` *endpoint in hmd-ms-deployment.*

Deployment Detail View
----------------------

.. spec:: Deployment detail showing CSD header, per-environment breakdown, per-instance status DAG, and timeline.
    :id: HMD_APP_NEURONSPHERE_NERD003_SPEC002
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD003

    The deployment detail view shall display:

    - ChangeSetDeployment header with overall status
    - Per-Environment breakdown (ChangeSetEnvDeployment)
    - Individual RepoInstanceDeployment status in a list or DAG visualization
    - Timeline visualization showing deployment progression

    The Status panel polls ``GET /apiop/get_deployment_logs`` every 5s. The Timeline tab is
    powered by the new ``GET /apiop/get_deployment_timeline/<csd_id>`` op (added 2026-04-28),
    which returns per-RepoInstanceDeployment ``{repo_instance_name, repo_class_name, environment,
    status, start, end, deployment_id}`` records rendered with vis-timeline.

Log Viewer
----------

.. spec:: Deployment log viewer with syntax highlighting, fetched from S3 or streaming from Argo, with download option.
    :id: HMD_APP_NEURONSPHERE_NERD003_SPEC003
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD003

    The log viewer shall fetch logs via ``GET /apiop/get_deployment_logs/<csd_id>``.

    Features:

    - Syntax highlighting for deployment output
    - Completed deployments fetch logs from S3
    - In-progress deployments may stream from Argo pod logs
    - Download log option

Real-time Status Updates
------------------------

.. spec:: Real-time deployment status via HTMX polling or optional WebSocket with Django Channels.
    :id: HMD_APP_NEURONSPHERE_NERD003_SPEC004
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD003

    In-progress deployments shall update status in real-time using HTMX polling
    (``hx-trigger="every 5s"``). An optional enhancement may use WebSocket connections
    via Django Channels for lower-latency updates.
