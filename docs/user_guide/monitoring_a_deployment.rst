Monitoring a Deployment
=======================

Applying a ChangeSet creates a **ChangeSetDeployment** and submits an Argo
workflow that deploys each instance in dependency order. The deployment detail
page at ``/deployments/<id>/`` is where you watch that run and read the output
of any individual step.

Open it from the **Deployments** page in the sidebar, from the link you are
taken to after a successful apply, or by pasting a ChangeSetDeployment id into
the **Jump to Deployment** box.

The Status tab
--------------

The Status tab shows the deployment's overall status and its workflow as a
**DAG** — one box per instance being deployed, wired together by the same
dependencies the Argo workflow itself uses. Reading order follows execution
order: with the default left-to-right layout, the first steps to run are on the
left and each arrow points at a step that waits on the one before it.

Every box names the **RepoInstance** it deploys, with its repo class and version
underneath, so it is always clear which part of the deployment a given step is.

The panel refreshes every five seconds, so colours track the deployment as it
progresses.

Reading the colours
~~~~~~~~~~~~~~~~~~~

Each box is a uniform white rectangle whose border encodes the status of that
instance's deployment — the same convention the environment BOM's DAG view uses:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Border
     - Meaning
   * - Green
     - Deployed. The step finished successfully.
   * - Blue
     - Running. The step has started and has not finished.
   * - Grey
     - Pending. The step is queued behind its dependencies.
   * - Red
     - Failed. The step errored; open its log to see why.
   * - Amber
     - Skipped. The step was not run for this deployment.
   * - Dark grey
     - Destroyed. The instance was torn down rather than deployed.

Statuses come from the RepoInstanceDeployment records rather than from Argo, so
they stay accurate for old deployments long after Argo has discarded the
workflow object.

Viewing a step's log
~~~~~~~~~~~~~~~~~~~~

Click any box to load that step's log into the panel below the graph. The panel
sits outside the auto-refreshing region, so an open log stays put while the
deployment continues to update around it.

A box marked ``no log`` has no archived log to show. That normally means the
step has not run yet. It can also mean the deployment predates step-log
tracking, or that it ran locally and never produced Argo pod logs.

The **View Logs** button in the page header still opens the full logs page,
which lists every pod for the workflow and lets you pick one directly. Use it
when you want to browse raw pod output rather than follow the graph.

Changing the layout
~~~~~~~~~~~~~~~~~~~

The controls above the graph switch between left-to-right and top-to-bottom
layout, and zoom or fit the graph to the width of the panel. Top-to-bottom is
usually easier to read for deployments that are long and narrow; left-to-right
suits wide, shallow ones.

The Timeline tab
----------------

The Timeline tab shows the same deployment as a Gantt chart, with one row per
instance and bars spanning each step's start and end times. Use the DAG when you
care about *ordering and dependencies*, and the Timeline when you care about
*duration* — which steps dominated the deployment's wall-clock time.
