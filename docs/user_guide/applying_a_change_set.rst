Applying a ChangeSet
====================

Applying a ChangeSet is what actually triggers deployments. A ChangeSet is
applied to a **DeploymentSet**, and the same ChangeSet can be applied to more
than one DeploymentSet. Before applying, review and validate the changes.

.. warning::

   Applying a ChangeSet triggers **real deployments** and cannot be undone.
   Review the changes carefully first.

Reviewing the ChangeSet
-----------------------

From the draft editor, click **Review** (available once the ChangeSet has
content). The review page collects everything you need to confirm before
applying.

.. figure:: /images/changeset_review.png
   :alt: ChangeSet review page with summary, changes, and validation
   :width: 100%

   The review page summarizes the ChangeSet and lists the changes to apply.

The page contains:

- **ChangeSet Summary** — name, status, total number of changes, and how many
  times it has been applied.
- **Changes to Apply** — each instance tagged **DEPLOY**, with its repo class,
  version, deployment ID, and configuration.
- **Validation** — pre-apply checks that run automatically (dependencies,
  duplicates, and required fields). Wait for these to finish before applying.

Previewing BOM impact
~~~~~~~~~~~~~~~~~~~~~

To see how the ChangeSet would affect a specific environment, use the **BOM
Impact Preview**: type an environment name and click **Preview**. The preview
shows which instances would be added, changed, or left as-is in that
environment.

Applying to a DeploymentSet
---------------------------

When you are satisfied, click **Apply to DeploymentSet** (on either the review
page or the draft editor). An apply dialog opens.

.. figure:: /images/apply_modal.png
   :alt: Apply ChangeSet to a DeploymentSet dialog
   :width: 100%

   Choose the target DeploymentSet and confirm.

#. Enter the target **DeploymentSet** name (for example ``Admin``). You must
   have deploy permission for that DeploymentSet.
#. Click **Apply** and confirm the prompt.

The dialog shows a progress indicator while the request is in flight — leave the
tab open until it finishes. On success, the ChangeSet is recorded as applied
and you are taken to the resulting deployment's detail page, where you can
follow its progress. If the apply fails, an error message is shown and the
failed attempt is recorded so you can retry.

After the first successful apply, the ChangeSet's status moves to **Accepted**.
You can apply the same ChangeSet again to another DeploymentSet; each apply is
recorded as a separate application.

Rejecting and reopening
-----------------------

If a ChangeSet should not be applied, click **Reject** on the review page,
enter a reason, and confirm. The ChangeSet's status becomes **Rejected** and
the reason is recorded.

A rejected ChangeSet can be brought back for further editing: open it and click
**Reopen**, which returns it to **Draft** status.
