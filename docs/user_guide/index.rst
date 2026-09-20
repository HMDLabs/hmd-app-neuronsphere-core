User Guide
==========

The NeuronSphere Deployment GUI is a web application for viewing what is
deployed in each environment and for safely changing it. This guide walks an
operator through the day-to-day workflow, end to end:

#. **View an environment's Bill of Materials (BOM)** — see every deployed
   instance, its version, and its status.
#. **Create a ChangeSet** — assemble a portable bundle of instance definitions,
   either from scratch or by selecting instances from a BOM.
#. **Edit instances** — adjust an instance's version, deployment ID,
   configuration, and dependencies inside a ChangeSet.
#. **Apply the ChangeSet** — review it, validate it, and apply it to a
   DeploymentSet to trigger real deployments.
#. **Monitor the deployment** — follow the workflow DAG as it runs and read the
   log of any individual step.

It also covers browsing the catalog of **repo classes** and their published
**versions**.

.. note::

   Screenshots in this guide are captured against a live environment with the
   helper script ``docs/capture_screenshots.py`` (see
   ``docs/README_screenshots.md``). If images are missing, run that script and
   rebuild the docs.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   getting_started
   viewing_environment_bom
   creating_a_change_set
   editing_instances
   applying_a_change_set
   monitoring_a_deployment
   repo_classes
