Editing Instances
=================

Once an instance is part of a ChangeSet draft you can adjust it without removing
and re-adding it. Editing happens inline in the **Changes** list of the draft
editor (see :doc:`creating_a_change_set`).

Each item in the Changes list has two edit actions: **Edit instance** and
**Edit dependencies**.

Editing an instance's definition
--------------------------------

Click **Edit instance** on the item you want to change. An inline editor opens
beneath the item.

.. figure:: /images/instance_editor_inline.png
   :alt: Inline instance editor with version, deployment ID and configuration fields
   :width: 100%

   The inline instance editor.

You can change:

- **Version** — pick a different published version of the instance's repo
  class, using the same searchable version picker as the Add Instance form
  (see below).
- **Deployment ID** — the deployment identifier for this instance.
- **Configuration (JSON)** — the instance configuration, edited as JSON.

Click **Save instance** to apply the change; the Changes list refreshes with
the updated values. Click **Cancel** (or **Close**) to discard your edits.

Choosing a version
------------------

The editor opens immediately and then loads versions in the background, so
repo classes with a long release history do not hold the panel up.

Versions are fetched one page at a time rather than all at once:

- Type in the **Search versions** box to filter the list. Filtering happens on
  the server, so it searches every version of the repo class, not just the ones
  currently on screen.
- Use **Prev** / **Next** beneath the list to move through the pages. The
  footer shows which versions you are looking at and how many there are in
  total.
- Click a version to select it. The selected version is shown above the list
  and marked with a check.

The instance's current version stays selected until you pick another one, so you
can edit the Deployment ID or Configuration alone without touching the version
— there is no need to find the current version in the list first.

.. note::

   The instance **name** and **repo class** cannot be changed here. To change
   either one, delete the instance from the ChangeSet and add it again with the
   new values.

.. warning::

   The configuration must be valid JSON. If it is not — or if no version is
   selected — the save is rejected and the editor stays open so you can fix it.

Editing an instance's dependencies
-----------------------------------

Click **Edit dependencies** on the item to reopen the dependency picker for that
instance. It works exactly like the picker used when adding an instance: for
each declared role, choose **In draft** or **From BOM** and select the target
(see the *Wiring dependencies* section of :doc:`creating_a_change_set`).

Click **Save dependencies** to apply, or **Cancel** to discard. Roles that the
current version no longer declares but that are still wired are kept and flagged
with an amber note so you don't lose an existing connection.

Removing an instance
--------------------

To take an instance out of the ChangeSet entirely, click the trash icon on its
row and confirm. This only edits the draft — nothing is deployed or undeployed
until the ChangeSet is applied.

When your edits are complete, continue to :doc:`applying_a_change_set`.
