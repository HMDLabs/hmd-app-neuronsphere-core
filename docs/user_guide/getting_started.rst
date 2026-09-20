Getting Started
===============

Logging In
----------

Open the Deployment GUI in your browser. If you are not signed in you are
redirected to the login page.

.. figure:: /images/login.png
   :alt: NeuronSphere Deployment GUI login page
   :width: 100%

   The login page. Use **Sign in with** your identity provider for normal
   access; the username/password form is only available in local development.

Most deployments use single sign-on (SSO) through an identity provider such as
Okta. Click the **Sign in with <provider>** button and complete your
provider's login (including any multi-factor prompt). In local development a
**Username or Email** / **Password** form is also shown.

After signing in you land on the **Dashboard**, and your email address and a
**Logout** link appear in the top bar.

Navigating the App
------------------

Every page shares the same layout: a top bar with the NeuronSphere logo and a
sidebar-toggle button (the "hamburger" icon), and a collapsible sidebar on the
left.

.. figure:: /images/sidebar_nav.png
   :alt: Sidebar navigation with Dashboard, Environments, Change Sets, Deployments and Repo Classes
   :width: 100%

   The sidebar is the primary way to move between the app's main areas.

The sidebar contains:

- **Dashboard** — environment status and recent deployments (the landing page).
- **Environments** — expands to **All Environments** plus a shortcut to the BOM
  of each environment you can access. If you see *"None available. Ask an admin
  for Okta group access,"* your account has not been granted access to any
  environment yet.
- **Change Sets** — list and create ChangeSets.
- **Deployments** — deployment history and status.
- **Repo Classes** — browse the catalog of repo classes and their versions.

Use the hamburger button in the top bar to collapse or expand the sidebar; the
choice is remembered between visits.

Roles and Permissions
---------------------

Access is granted per environment. Your role in an environment determines what
you can do:

- **Viewer** — can view the BOM, instance details, deployment history, and the
  repo class catalog.
- **Deployer** — everything a viewer can do, plus create ChangeSets, edit
  instances, and apply ChangeSets to DeploymentSets they are permitted to use.
- **Admin** — full access.

Actions you are not permitted to take are hidden. For example, the **Create
ChangeSet** button and the BOM selection controls only appear when you have
deploy permission for that environment. Environment access is typically synced
from your identity provider's groups; if you need access to an environment or a
DeploymentSet, ask an administrator.
