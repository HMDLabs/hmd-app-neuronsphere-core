# hmd-app-neuronsphere-core

The core of the NeuronSphere deployment GUI (Django + HTMX): environments and BOMs,
ChangeSet drafting, validation and comparison, repo classes and versions, the
ResourceDefinition catalogue, discovery search, and the MCP server -- everything
that works against the registry-and-resolver core of the deployment service
(`hmd-ms-deployment-core`). This is the image `nsctl` runs locally.

Run observability (ChangeSetDeployments, timeline, DAG, pod logs) and
apply-to-DeploymentSet are the **premium overlay**, `hmd-app-neuronsphere`, whose
image is `FROM` this one. See NERD0015 in `hmd-ms-deployment`.

## The extension seam

The core never references a premium view, URL name or template. An overlay
plugs in through three things, all read from the environment so an image `FROM`
this one sets them with `ENV`:

- `DJANGO_EXTRA_APPS` -- comma-separated Django apps to install; each app's `urls`
  module (if any) is included at the root.
- `DEPLOYMENT_API_CLIENT_CLASS` -- a dotted path to a `DeploymentAPIClient`
  subclass, for routes only the overlay's service serves.
- `{% extension_slot "name" %}` -- core pages render named slots
  (`sidebar_nav`, `dashboard_cards`, `changeset_actions`,
  `changeset_review_actions`, `changeset_modals`, `changeset_applications`,
  `changeset_application_count`); every extra app shipping
  `<app>/slots/<name>.html` renders there with the page's context plus what its
  `<app>.slots.context(request)` returns.
- `EXTENSION_SECTIONS` -- `section=/path-prefix` pairs so the sidebar highlights
  an overlay's section.

## Licence

BUSL 1.1 for the application code, Apache 2.0 for the deploy descriptor
(`meta-data/`, `src/cdktf/`, `src/helm/`) -- see `LICENSE.txt`.
