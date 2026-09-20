Creating a ChangeSet
====================

A **ChangeSet** is a portable bundle of instance definitions. You build it once
and can apply it to one or more **DeploymentSets** later. Creating a ChangeSet
never changes anything on its own — nothing is deployed until you apply it
(see :doc:`applying_a_change_set`).

There are two ways to start a ChangeSet.

Option A — From a BOM selection
-------------------------------

This is the quickest way to base a ChangeSet on instances that already exist.

#. Open an environment's BOM in **Table View** (see
   :doc:`viewing_environment_bom`).
#. Tick the checkbox next to each instance you want to include. A sticky bar at
   the top of the table shows how many are selected.
#. Type a name for the new ChangeSet in the **New ChangeSet name** field.
#. Click **Edit selected**.

.. figure:: /images/bom_select_create_changeset.png
   :alt: Selecting instances in the BOM and naming a new ChangeSet
   :width: 100%

   Select instances, name the ChangeSet, and click **Edit selected**.

The selected instances are copied into a new draft and you are taken to the
draft editor. Use **Clear selection** to start over. (The **Edit selected**
button is disabled until you have selected at least one instance and entered a
name.)

Option B — From scratch
-----------------------

#. In the sidebar, click **Change Sets**, then **Create New ChangeSet** (or use
   the **Create ChangeSet** button on a BOM page). The URL is
   ``/changeset/new/``.
#. Enter a unique **ChangeSet Name** (for example ``private-ca-bootstrap``).
#. Click **Create ChangeSet**.

.. figure:: /images/changeset_create_form.png
   :alt: Create ChangeSet form
   :width: 100%

   Naming a new, empty ChangeSet.

You are taken to the draft editor with an empty ChangeSet, ready to add
instances.

The Draft Editor
----------------

The draft editor is where you assemble the ChangeSet. The page header shows the
draft name and a status badge (**Draft**, **In Review**, **Accepted**, or
**Rejected**), plus buttons to **Clone**, start a **New ChangeSet**, and —
once the ChangeSet has content — **Review** and **Apply to DeploymentSet**.

The editor has two columns: an **Add Instance** form on the left and the
current **Changes** list on the right.

.. figure:: /images/changeset_draft_add_instance.png
   :alt: ChangeSet draft editor with the Add Instance form and Changes list
   :width: 100%

   The draft editor: add instances on the left, review the running list on the
   right.

Adding an instance
~~~~~~~~~~~~~~~~~~

Fill in the **Add Instance** form:

- **Instance Name** — the name of the instance (for example ``private-ca``).
- **Repo Class** — choose from the catalog; the list loads automatically.
- **Version** — enabled once a repo class is chosen; pick the version to deploy.
- **Deployment ID** — defaults to ``aaa`` for new instances.
- **Configuration (JSON)** — optional instance configuration as JSON; leave as
  ``{}`` if none.

When you pick a version, the **Dependencies** section loads automatically (see
below). Click **Add to ChangeSet** to append the instance to the Changes list.

.. tip::

   To base a new instance on one that already exists, use the **Search Existing
   Instances** panel below the form: enter an environment, search by name or
   repo class, and click a result to pre-fill the form.

Wiring dependencies
~~~~~~~~~~~~~~~~~~~

If the chosen repo class version declares dependency **roles**, a picker
appears with one section per role. Required roles are marked with an asterisk
(``*``).

For each role, choose the source:

- **In draft** — wire the dependency to another instance already in this
  ChangeSet. Matching instances are offered as checkboxes.
- **From BOM** — wire it to an existing instance in a chosen environment's BOM.
  Pick the environment, then select the target instance.

Roles that are no longer declared by the selected version but are still wired
are shown with an amber *"not declared by this version — kept"* note; they are
preserved on save so you don't lose an existing wiring.

The Changes list
~~~~~~~~~~~~~~~~

Each instance you add appears on the right with its name, repo class, version,
deployment ID, and any wired dependencies (shown as ``role → target``). From
here you can:

- **Edit instance** — change the version, deployment ID, or configuration
  (see :doc:`editing_instances`).
- **Edit dependencies** — reopen the dependency picker for that instance.
- **Delete** (the trash icon) — remove the instance from the ChangeSet, after a
  confirmation prompt.

When the ChangeSet has everything you want, continue to
:doc:`applying_a_change_set`.
