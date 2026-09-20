Viewing an Environment BOM
==========================

An environment's **Bill of Materials (BOM)** lists every instance currently
deployed in that environment, along with its repo class, version, and
deployment status. It is the starting point for understanding what is running
and for building a ChangeSet to change it.

Opening a BOM
-------------

In the sidebar, expand **Environments** and click the environment you want to
inspect. (The URL is ``/bom/<environment>/``.) The page header shows the
environment name and the heading *Bill of Materials*.

.. figure:: /images/bom_table.png
   :alt: Environment BOM in Table View
   :width: 100%

   The BOM opens in **Table View**, listing the deployed instances.

Two buttons appear at the top right:

- **Compare with...** — compare this environment's BOM against another
  environment.
- **Create ChangeSet** — start a new ChangeSet scoped to this environment
  (only shown if you have deploy permission).

The BOM has two views, selected with the tabs beneath the header: **Table View**
(the default) and **DAG View**.

Table View
----------

Table View shows one row per instance with its **Instance Name**, **Repo
Class**, **Version**, **Status**, and **Deployment ID**.

Use the filter bar to narrow the list:

.. figure:: /images/bom_filters.png
   :alt: BOM table filter bar with search, status and repo class filters
   :width: 100%

   Filter the table by free-text search, status, or repo class.

- **Search** — type to filter by instance name; the table updates as you type.
- **Status** — restrict to a single deployment status (for example
  ``DEPLOYED`` or ``FAILED``).
- **Repo Class** — restrict to a single repo class.
- **Refresh** — reload the table with the current filters.

Long lists are paginated; use the page controls at the bottom of the table.

DAG View
--------

Switch to **DAG View** to see the instances as an interactive dependency graph.
Nodes are colored by status, and you can pan and zoom around the graph.

.. figure:: /images/bom_dag.png
   :alt: BOM DAG View showing instances as a dependency graph
   :width: 100%

   DAG View renders the environment's instances and their dependencies.

- **Filter by type** — limit the graph to a single repo class type.
- **Reset filter** — clear the type filter.
- The legend (top right) shows the node colors: **Deployed** (green),
  **Failed** (red), and **Deploy Next** (blue).

Click any node to open that instance's detail panel.

Instance Detail Panel
---------------------

Clicking an instance name (in Table View) or a node (in DAG View) opens a
slide-over panel on the right with the instance's details.

The panel shows the instance's configuration and its recent deployment history.
Close it with the close button (**X**), by clicking outside the panel, or by
pressing **Esc**.

Next step
---------

To change what is deployed, select instances here and build a ChangeSet — see
:doc:`creating_a_change_set`.
