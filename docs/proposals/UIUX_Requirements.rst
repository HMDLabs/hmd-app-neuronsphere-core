.. _uiux-requirements:

==============================================
UI/UX Requirements & Wireframes
==============================================

This document defines the UI/UX specifications for the NeuronSphere Deployment GUI,
covering the global layout, design system, and per-NERD view requirements. All
wireframes use PlantUML Salt syntax and are intended to be rendered with
``sphinxcontrib-plantuml``.

.. contents:: Table of Contents
   :depth: 3
   :local:

--------------
Global Layout
--------------

The application uses a fixed top header with a collapsible left sidebar. The main
content area fills the remaining viewport. Authentication state determines whether
the sidebar is rendered.

Page Structure Wireframe
========================

.. uml::

   @startsalt
   {
     {/ <b>NeuronSphere Deployment GUI</b> }
     {
       {
         {T
           + [Toggle] | <b>Neuron</b><i>Sphere</i>  |  .  |  .  |  .  |  .  |  .  |  .  | user@hmd.com | [Logout]
         }
       }
       {
         {
           {T
             + <b>Dashboard</b>
             + <b>Environments</b>
             ++ All Environments
             ++ (+) dev
             ++ (!) test
             ++ (x) prod
             + <b>Change Sets</b>
             + <b>Deployments</b>
             + <b>Repo Classes</b>
           }
           |
           {
             <b>Main Content Area</b>
             .
             Page content renders here.
             Scrollable independently of sidebar.
             .
             .
             .
             ---
             <i>NeuronSphere Deployment GUI (c) 2026</i>
           }
         }
       }
     }
   }
   @endsalt

Header Bar
==========

**Left side:**

- Sidebar toggle button (hamburger icon) — only shown when authenticated
- NeuronSphere logo text (Comfortaa font): "Neuron" in ``ns-blue`` (#180075) +
  "Sphere" in ``ns-magenta`` (#A70B52)
- Logo links to Dashboard

**Right side:**

- Authenticated: user email/username display + "Logout" link
- Unauthenticated: "Login" link

**Styling:**

- Background: ``hmd-dark`` (#161718)
- Height: ``h-16`` (4rem)
- Text: ``hmd-light`` (#D7DCDD), hover ``hmd-electric`` (#3DBCD8)

Sidebar Navigation
==================

The sidebar is a dark vertical nav panel that collapses to icon-only mode (``w-14``)
or expands to full width (``w-64``). State is persisted in ``localStorage``.

**Nav items (top to bottom):**

1. **Dashboard** — Home icon, links to ``/``
2. **Environments** — Server icon, expandable section

   - "All Environments" link
   - Per-environment links with colored status dots:

     - ``dev``: green (``bg-green-500``)
     - ``test``: yellow (``bg-yellow-500``)
     - ``prod``: red (``bg-red-500``)

3. **Change Sets** — Clipboard icon, links to ``/changesets/``
4. **Deployments** — Refresh icon, links to ``/deployments/``
5. **Repo Classes** — Archive icon, links to ``/repo-classes/``

**Active state:** ``bg-hmd-medium`` background + ``text-hmd-electric`` text.

**Collapsed state:** Icons only, tooltips via ``title`` attribute. Sub-lists hidden.

------------------------------
Tailwind CSS Design System
------------------------------

Brand Colors
============

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Token
     - Hex
     - Usage
   * - ``ns-blue``
     - ``#180075``
     - Logo "Neuron", primary accent, links
   * - ``ns-magenta``
     - ``#A70B52``
     - Logo "Sphere", error/danger states, FAILED badges
   * - ``hmd-electric``
     - ``#3DBCD8``
     - Active nav items, hover states, info badges, focus rings
   * - ``hmd-lime``
     - ``#E7F2BC``
     - Success states, DEPLOYED/COMPLETED badges
   * - ``hmd-dark``
     - ``#161718``
     - Header, sidebar, footer backgrounds
   * - ``hmd-medium``
     - ``#3A4046``
     - Active sidebar items, secondary backgrounds, borders
   * - ``hmd-light``
     - ``#D7DCDD``
     - Text on dark backgrounds, DESTROYED/SKIPPED badges

Typography
==========

.. list-table::
   :header-rows: 1
   :widths: 20 30 50

   * - Token
     - Font
     - Usage
   * - ``font-title``
     - Josefin Sans
     - All headings (h1–h6)
   * - ``font-body``
     - Source Sans 3
     - Body text, tables, form labels
   * - ``font-logo``
     - Comfortaa
     - NeuronSphere logo text only

Status Badges
=============

Status badges use semi-transparent brand colors for backgrounds with high-contrast
text. Applied via CSS classes ``status-{STATUS}``:

.. list-table::
   :header-rows: 1
   :widths: 20 35 25

   * - Status
     - Background
     - Text Color
   * - DEPLOYED
     - ``#E7F2BC`` (hmd-lime)
     - ``#065f46`` (green-800)
   * - DEPLOY_NEXT
     - ``rgba(61, 188, 216, 0.2)`` (hmd-electric 20%)
     - ``#180075`` (ns-blue)
   * - FAILED
     - ``rgba(167, 11, 82, 0.15)`` (ns-magenta 15%)
     - ``#A70B52`` (ns-magenta)
   * - DESTROYED
     - ``#D7DCDD`` (hmd-light)
     - ``#3A4046`` (hmd-medium)
   * - DESTROY_NEXT
     - ``#fef3c7`` (amber-100)
     - ``#92400e`` (amber-800)
   * - SKIPPED
     - ``#D7DCDD`` (hmd-light)
     - ``#3A4046`` (hmd-medium)
   * - CREATED
     - ``rgba(24, 0, 117, 0.1)`` (ns-blue 10%)
     - ``#180075`` (ns-blue)
   * - STARTED
     - ``rgba(61, 188, 216, 0.2)`` (hmd-electric 20%)
     - ``#180075`` (ns-blue)
   * - COMPLETED
     - ``#E7F2BC`` (hmd-lime)
     - ``#065f46`` (green-800)

Spacing & Layout Conventions
=============================

- Content padding: ``px-6 py-6``
- Card components: ``rounded-lg shadow-md border border-gray-200 p-6``
- Table row hover: ``hover:bg-gray-50``
- Section spacing: ``mb-6`` between major sections
- Form field spacing: ``space-y-4`` within forms
- Button styles: ``px-4 py-2 rounded-md font-semibold text-sm``

  - Primary: ``bg-ns-blue text-white hover:bg-opacity-90``
  - Danger: ``bg-ns-magenta text-white hover:bg-opacity-90``
  - Secondary: ``bg-gray-200 text-gray-700 hover:bg-gray-300``

Loading Indicator
=================

A 3px gradient bar (``ns-blue`` → ``ns-magenta`` → ``hmd-electric``) at the top of
the viewport, animated with a sliding translation. Shown automatically during HTMX
requests via ``.htmx-request #loading-bar``.


----------------------------------------------
NERD001: Environment BOM View
----------------------------------------------

*Cross-reference:* :doc:`NERD001_Environment_BOM_View`

BOM Table View
==============

The primary view for inspecting instances deployed to an environment. Displays a
sortable, filterable table of all instances.

.. uml::

   @startsalt
   {
     <b>Environment BOM — dev</b>
     ---
     {
       [< Back to Environments] | . | . | [Refresh]
     }
     ---
     {
       Search: | "instance name   " | Status: | ^All Status^  | Repo Class: | ^All Repo Classes^ | [Filter]
     }
     ---
     {#
       <b>Instance Name</b>     | <b>Repo Class</b>  | <b>Version</b> | <b>Status</b>     | <b>Deployment ID</b> | <b>Actions</b>
       api-gateway             | hmd-ms-gateway      | 0.4             | <&check> DEPLOYED  | dep-1234              | [View]
       auth-service            | hmd-ms-auth          | 0.3             | <&check> DEPLOYED  | dep-1235              | [View]
       transform-worker        | hmd-ms-transform     | 0.2             | <&bolt> DEPLOY_NEXT | dep-1236              | [View]
       legacy-adapter          | hmd-ms-legacy        | 0.1             | <&x> FAILED        | dep-1237              | [View]
       telemetry-collector     | hmd-ms-telemetry     | 0.5             | <&minus> DESTROYED | dep-1238              | [View]
     }
     ---
     {
       Showing 1-5 of 23 | . | [< Prev] [Next >]
     }
   }
   @endsalt

**Behavior:**

- Clicking a row opens the Instance Detail slide-over panel
- Table headers are sortable (click to toggle asc/desc)
- Filter form submits via HTMX to update the table partial without full page reload
- Auto-refresh every 30 seconds via ``hx-trigger="every 30s"``
- Pagination is HTMX-driven (replaces table body only)

BOM DAG View
============

An interactive dependency graph visualization rendered with D3.js or Cytoscape.js.
Activated via a toggle button above the BOM table.

.. uml::

   @startsalt
   {
     <b>Environment BOM — dev</b>
     ---
     {
       [< Back to Environments] | [Table View] | [<b>DAG View</b>] | . | [Refresh]
     }
     ---
     {
       .
       .    [api-gateway]
       .        |
       .   +---------+
       .   |         |
       . [auth]   [transform]
       .   |
       . [legacy]
       .
       .    [telemetry] (isolated)
       .
       .
     }
     ---
     { Legend: | <&check> Deployed | <&bolt> Deploy Next | <&x> Failed | <&minus> Destroyed }
   }
   @endsalt

**Behavior:**

- Nodes are colored by deployment status using brand colors
- Click a node to open the Instance Detail panel
- Pan and zoom with mouse/touch
- Dependency arrows show direction (upstream → downstream)
- Isolated instances (no dependencies) shown separately
- Toggle between Table View and DAG View preserved in URL query param

Instance Detail Slide-Over Panel
================================

A right-side slide-over panel that shows detailed information about a single instance
without leaving the BOM view.

.. uml::

   @startsalt
   {
     { [X Close] | . | <b>Instance Detail</b> }
     ---
     {
       <b>api-gateway</b>
       Repo Class: hmd-ms-gateway
       Version: 0.4
       Status: DEPLOYED
       Deployment ID: dep-1234
     }
     ---
     <b>Configuration</b>
     {
       {T
         + replicas: 3
         + memory: 512Mi
         + cpu: 250m
         + env_vars:
         ++ LOG_LEVEL: info
         ++ DB_HOST: db.internal
       }
     }
     ---
     <b>Dependencies</b>
     {
       auth-service (v0.3) | DEPLOYED
       transform-worker (v0.2) | DEPLOY_NEXT
     }
     ---
     <b>Deployment History</b>
     {#
       <b>Date</b>        | <b>Version</b> | <b>Status</b>
       2026-03-12 14:30   | 0.4            | DEPLOYED
       2026-03-10 09:15   | 0.3            | DEPLOYED
       2026-03-08 11:00   | 0.3            | FAILED
     }
     ---
     {
       [Add to ChangeSet] | [View Full Detail]
     }
   }
   @endsalt

**Behavior:**

- Opens from the right side with a slide animation (Alpine.js ``x-transition``)
- Semi-transparent overlay on the BOM table behind it
- Configuration displayed as a collapsible JSON tree
- "Add to ChangeSet" opens a dropdown to select an existing draft or create new
- "View Full Detail" navigates to the dedicated instance detail page
- RBAC: "Add to ChangeSet" only visible to Deployer/Admin roles

Environment Comparison View
============================

Side-by-side comparison of two environments to identify differences in deployed
instances and versions.

.. uml::

   @startsalt
   {
     <b>Environment Comparison</b>
     ---
     {
       Compare: | ^dev^ | vs | ^prod^ | [Compare]
     }
     ---
     {#
       <b>Instance</b>       | <b>dev</b>      | <b>prod</b>     | <b>Diff</b>
       api-gateway           | v0.4 DEPLOYED    | v0.3 DEPLOYED    | Version mismatch
       auth-service          | v0.3 DEPLOYED    | v0.3 DEPLOYED    | —
       transform-worker      | v0.2 DEPLOY_NEXT | — (not present)  | Only in dev
       legacy-adapter        | v0.1 FAILED      | v0.1 DEPLOYED    | Status mismatch
       billing-service       | — (not present)  | v0.2 DEPLOYED    | Only in prod
     }
     ---
     {
       [Generate ChangeSet from Diff]
     }
   }
   @endsalt

**Behavior:**

- Dropdown selectors populated from available environments
- Diff column highlights: version mismatch (amber), only-in-one (blue), status
  mismatch (magenta)
- "Generate ChangeSet from Diff" creates a new ChangeSet draft pre-populated with the
  selected items — the draft itself is deployment-set-agnostic; the user picks a target
  DeploymentSet at apply time
- Rows with no differences can be hidden via a "Show differences only" toggle

Component Specifications
========================

**BOM Table:**

- Container: ``overflow-x-auto`` for horizontal scroll on narrow viewports
- Header cells: ``bg-gray-50 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider px-4 py-3``
- Body cells: ``px-4 py-3 text-sm text-gray-700``
- Row hover: ``hover:bg-gray-50 cursor-pointer``
- Status badges: ``inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium``

**Slide-over Panel:**

- Width: ``w-96`` (24rem) on desktop, full-width on mobile
- Background: white with ``shadow-xl``
- Overlay: ``bg-black bg-opacity-25``
- Transition: ``transform transition-transform duration-300``


----------------------------------------------
NERD002: ChangeSet Creation
----------------------------------------------

*Cross-reference:* :doc:`NERD002_ChangeSet_Creation`

ChangeSet List / Drafts View
=============================

Displays all ChangeSet drafts for the current user, with an option to create new ones.

.. uml::

   @startsalt
   {
     <b>Change Set Drafts</b>
     ---
     {
       . | . | . | . | [+ Create New ChangeSet]
     }
     ---
     {#
       <b>Name</b>                 | <b>Target Env</b> | <b>Deployment Set</b> | <b>Changes</b> | <b>Last Updated</b>    | <b>Actions</b>
       upgrade-api-gateway        | dev                | default               | 3               | 2026-03-12 14:30        | [Edit] [Review]
       add-billing-service        | test               | billing               | 1               | 2026-03-11 09:00        | [Edit] [Review]
       prod-rollback-auth         | prod               | default               | 2               | 2026-03-10 16:45        | [Edit] [Review]
     }
     ---
     {
       Showing 1-3 of 3
     }
   }
   @endsalt

**Behavior:**

- "Create New ChangeSet" opens the creation form
- "Edit" navigates to the draft editor
- "Review" navigates to the review panel
- Empty state: illustration with prompt "No change sets yet. Create one to get started."

Add Instance Wizard (Multi-Step)
================================

A multi-step wizard for adding a new instance to a ChangeSet. Steps are presented
as a horizontal stepper with HTMX-powered transitions.

.. uml::

   @startsalt
   {
     <b>Add Instance to ChangeSet</b>
     ---
     {
       (<b>1. Repo Class</b>) -- (2. Version) -- (3. Configure) -- (4. Dependencies) -- (5. Review)
     }
     ===
     <b>Step 1: Select Repo Class</b>
     ---
     {
       Search: | "search repo classes...  "
     }
     ---
     {#
       <b>Name</b>             | <b>Type</b>        | <b>Latest Version</b> | <b>Select</b>
       hmd-ms-gateway          | microservice       | 0.4                    | (X)
       hmd-ms-auth             | microservice       | 0.3                    | ( )
       hmd-ms-transform        | microservice       | 0.2                    | ( )
       hmd-lib-common          | library            | 1.0                    | ( )
     }
     ---
     {
       . | . | . | [Next →]
     }
   }
   @endsalt

.. uml::

   @startsalt
   {
     <b>Add Instance to ChangeSet</b>
     ---
     {
       (<b>1. Repo Class</b>) -- (<b>2. Version</b>) -- (3. Configure) -- (4. Dependencies) -- (5. Review)
     }
     ===
     <b>Step 2: Select Version</b>
     ---
     Selected Repo Class: <b>hmd-ms-gateway</b>
     ---
     {#
       <b>Version</b> | <b>Status</b>   | <b>Created</b>      | <b>Select</b>
       0.4            | Active          | 2026-03-01           | (X)
       0.3            | Active          | 2026-02-15           | ( )
       0.2            | Deprecated      | 2026-01-20           | ( )
     }
     ---
     {
       [← Back] | . | . | [Next →]
     }
   }
   @endsalt

.. uml::

   @startsalt
   {
     <b>Add Instance to ChangeSet</b>
     ---
     {
       (1. Repo Class) -- (2. Version) -- (<b>3. Configure</b>) -- (4. Dependencies) -- (5. Review)
     }
     ===
     <b>Step 3: Configuration</b>
     ---
     Instance Name: | "my-api-gateway       "
     Deployment ID: | "dep-auto-generated   "
     ---
     <b>Configuration (from default_configuration)</b>
     {
       replicas:   | "3          "
       memory:     | "512Mi      "
       cpu:        | "250m       "
       log_level:  | ^info^
     }
     ---
     <i>Or paste raw JSON:</i>
     {SI
       {
         "replicas": 3,
         "memory": "512Mi"
       }
     }
     ---
     {
       [← Back] | . | . | [Next →]
     }
   }
   @endsalt

.. uml::

   @startsalt
   {
     <b>Add Instance to ChangeSet</b>
     ---
     {
       (1. Repo Class) -- (2. Version) -- (3. Configure) -- (<b>4. Dependencies</b>) -- (5. Review)
     }
     ===
     <b>Step 4: Dependencies</b>
     ---
     <i>Select instances this service depends on:</i>
     ---
     {#
       <b>Instance</b>          | <b>Repo Class</b>    | <b>Version</b> | <b>Include</b>
       auth-service             | hmd-ms-auth           | 0.3             | [X]
       transform-worker         | hmd-ms-transform      | 0.2             | [ ]
       telemetry-collector      | hmd-ms-telemetry      | 0.5             | [ ]
     }
     ---
     {
       [← Back] | . | . | [Next →]
     }
   }
   @endsalt

.. uml::

   @startsalt
   {
     <b>Add Instance to ChangeSet</b>
     ---
     {
       (1. Repo Class) -- (2. Version) -- (3. Configure) -- (4. Dependencies) -- (<b>5. Review</b>)
     }
     ===
     <b>Step 5: Review & Confirm</b>
     ---
     {
       Instance Name: | my-api-gateway
       Repo Class:    | hmd-ms-gateway
       Version:       | 0.4
       Deployment ID: | dep-auto-generated
       Action:        | DEPLOY
     }
     ---
     <b>Configuration</b>
     {T
       + replicas: 3
       + memory: 512Mi
       + cpu: 250m
       + log_level: info
     }
     ---
     <b>Dependencies</b>
     {
       auth-service (v0.3)
     }
     ---
     {
       [← Back] | . | [Add to ChangeSet]
     }
   }
   @endsalt

**Behavior:**

- Steps are navigable via the horizontal stepper (can go back to completed steps)
- Each step validates before allowing progression
- "Copy Instance" shortcut: pre-fills steps 1–4 from an existing instance
- HTMX swaps step content without full page reload
- Step indicators show completed (filled), current (outlined bold), future (gray)

Edit Mode Overlay on BOM
=========================

When editing a ChangeSet, the BOM view enters an "edit mode" with visual overlays
indicating pending changes.

.. uml::

   @startsalt
   {
     <b>Environment BOM — dev</b> | <i>Editing: upgrade-api-gateway</i> | [Exit Edit Mode]
     ---
     {#
       <b>Instance Name</b>     | <b>Repo Class</b>  | <b>Version</b>  | <b>Status</b>       | <b>Change</b>
       api-gateway             | hmd-ms-gateway      | 0.3 → <b>0.4</b> | DEPLOYED → DEPLOY   | (!) UPGRADE
       auth-service            | hmd-ms-auth          | 0.3              | DEPLOYED             | —
       transform-worker        | hmd-ms-transform     | 0.2              | DEPLOY_NEXT          | —
       legacy-adapter          | hmd-ms-legacy        | 0.1              | DEPLOYED → DESTROY   | (x) REMOVE
       <i>billing-service</i>  | <i>hmd-ms-billing</i>| <i>0.1</i>      | <i>— → DEPLOY</i>   | (+) ADD
     }
     ---
     {
       [+ Add Instance] | . | . | [Review Changes (3)]
     }
   }
   @endsalt

**Behavior:**

- Changed rows highlighted with left border color: green (add), amber (modify), red (remove)
- New instances shown in italic
- "Review Changes" badge shows count of pending changes
- Floating action bar pinned to bottom of content area

Review Panel with Color-Coded Changes
======================================

A summary view of all changes in a ChangeSet before applying.

.. note::

    The "Apply ChangeSet" action in this wireframe is premium-only and does not
    apply to the open-core GUI (``hmd-app-neuronsphere-core``) -- see
    ``hmd-ms-deployment``'s ``docs/proposals/NERD0015_CoreAndPremiumSplit.rst`` for
    the core/premium boundary. This mockup is kept as historical/premium reference.

.. uml::

   @startsalt
   {
     <b>Review ChangeSet: upgrade-api-gateway</b>
     ---
     {
       Deployment Set: | default
       Target Environment: | dev
       Total Changes: | 3
     }
     ===
     {
       (+) <b>ADD</b> billing-service
       Repo Class: hmd-ms-billing | Version: 0.1
       Config: {"replicas": 2, "memory": "256Mi"}
     }
     ---
     {
       (!) <b>UPGRADE</b> api-gateway
       Repo Class: hmd-ms-gateway | Version: 0.3 → 0.4
       Config: no changes
     }
     ---
     {
       (x) <b>REMOVE</b> legacy-adapter
       Repo Class: hmd-ms-legacy | Version: 0.1
       Will be destroyed in next deployment
     }
     ===
     {
       <b>(!) Warning:</b> Applying this ChangeSet will trigger a deployment.
       This action cannot be undone.
     }
     ---
     {
       [← Back to Edit] | . | [Apply ChangeSet]
     }
   }
   @endsalt

**Behavior:**

- Changes grouped by action type (ADD, UPGRADE/MODIFY, REMOVE)
- Each change card shows full details (repo class, version diff, config diff)
- Config diffs highlighted inline (added lines green, removed lines red)
- "Apply ChangeSet" requires confirmation modal
- Validation errors (dependency conflicts, circular deps) shown as red alert banners

Dynamic Configuration Form
===========================

Configuration forms are dynamically generated from the ``default_configuration``
of the selected RepoClassVersion.

**Form generation rules:**

- String values → text input
- Numeric values → number input
- Boolean values → checkbox
- Enum/list values → dropdown select
- Nested objects → collapsible fieldset with recursive generation
- Unknown types → raw JSON textarea fallback

**Validation:**

- Required fields marked with red asterisk
- Inline validation messages below each field
- JSON mode toggle for advanced users (raw JSON textarea)


----------------------------------------------
NERD003: Deployment History
----------------------------------------------

*Cross-reference:* :doc:`NERD003_Deployment_History`

Deployment List with Filters
=============================

Paginated list of deployments with filtering by Deployment Set, status, environment,
and date range.

.. uml::

   @startsalt
   {
     <b>Deployments</b>
     ---
     {
       Deployment Set: | ^All Sets^  | Status: | ^All Status^ | [Filter]
     }
     ---
     {
       <i>Jump to a specific deployment by entering a CSD ID</i>
       CSD ID: | "                    " | [Go]
     }
     ---
     {#
       <b>CSD ID</b>             | <b>Deployment Set</b> | <b>Environment</b> | <b>Status</b>         | <b>Started</b>           | <b>Actions</b>
       csd-2026-0312-001        | default               | dev                 | <&check> COMPLETED     | 2026-03-12 14:30          | [View]
       csd-2026-0312-002        | billing               | test                | <&media-record> STARTED | 2026-03-12 14:35          | [View]
       csd-2026-0311-001        | default               | prod                | <&x> FAILED            | 2026-03-11 09:00          | [View]
       csd-2026-0310-001        | default               | dev                 | <&check> COMPLETED     | 2026-03-10 16:45          | [View]
     }
     ---
     {
       [Load More]
     }
   }
   @endsalt

**Behavior:**

- Filters submit via HTMX, replacing the table partial
- "Load More" appends next page of results (``hx-swap="beforeend"``)
- "Jump to Deployment" for direct CSD ID navigation
- Status column uses brand status badges
- Active deployments (STARTED) show a pulsing indicator
- Auto-refresh active deployments every 5 seconds

Deployment Detail with Status Timeline
========================================

Detailed view of a single deployment showing per-environment and per-instance
breakdown with a visual timeline.

.. uml::

   @startsalt
   {
     <b>Deployment: csd-2026-0312-001</b>
     ---
     {
       [< Back to Deployments]
     }
     ---
     {
       Deployment Set: | default
       Environment:    | dev
       Status:         | STARTED
       Started:        | 2026-03-12 14:30
       Duration:       | 4m 23s (in progress)
     }
     ===
     <b>Timeline</b>
     {T
       + 14:30:00 — ChangeSet applied, deployment initiated
       + 14:30:05 — Dependency resolution completed
       + 14:30:10 — api-gateway: building image...
       + 14:32:15 — api-gateway: image built, deploying to cluster
       + 14:33:00 — auth-service: deploying to cluster
       + 14:34:23 — <b>api-gateway: health check passed</b>
       + 14:34:23 — auth-service: waiting for health check...
     }
     ===
     <b>Instance Status</b>
     {#
       <b>Instance</b>       | <b>Status</b>          | <b>Duration</b> | <b>Actions</b>
       api-gateway           | <&check> DEPLOYED       | 4m 13s           | [Logs]
       auth-service          | <&media-record> STARTED  | 1m 23s           | [Logs]
       legacy-adapter        | <&clock> PENDING         | —                | [Logs]
     }
     ---
     {
       [View Logs]
     }
   }
   @endsalt

**Behavior:**

- Timeline updates in real-time via HTMX polling (every 5 seconds)
- Instance status table shows per-instance progress
- Click "Logs" to open the log viewer for that specific instance
- Duration auto-updates for in-progress deployments
- Completed deployments show final duration and summary

Log Viewer
==========

A dedicated log viewing panel with syntax highlighting, pod/step selection, and
streaming support.

.. uml::

   @startsalt
   {
     <b>Deployment Logs: csd-2026-0312-001</b>
     ---
     {
       [< Back to Deployment]
     }
     ---
     {
       Pod/Step: | ^api-gateway-build^ | Lines: | ^100^ | [Refresh]
     }
     ---
     {SI
       [14:30:10] INFO  Starting build for api-gateway v0.4
       [14:30:11] INFO  Pulling base image: python:3.11-slim
       [14:30:45] INFO  Installing dependencies from requirements.txt
       [14:31:20] INFO  Running unit tests...
       [14:31:55] INFO  Tests passed (42/42)
       [14:32:00] INFO  Building Docker image...
       [14:32:10] INFO  Pushing image to registry...
       [14:32:15] INFO  Image pushed: registry.hmd.io/api-gateway:0.4
       [14:32:16] INFO  Deploying to kubernetes cluster dev-cluster
       [14:33:00] INFO  Pod api-gateway-7d8f9 running
       [14:34:23] INFO  Health check passed
     }
     ---
     {
       [Download Full Log]
     }
   }
   @endsalt

**Behavior:**

- Pod/Step dropdown populated from deployment metadata (build, deploy, test steps)
- Lines selector: 50, 100, 500, 1000 (tail of log)
- Log content refreshes via HTMX when pod/step or line count changes
- Monospace font (``font-mono``) with syntax highlighting:

  - INFO: default text
  - WARN: ``text-yellow-600``
  - ERROR: ``text-red-600 font-semibold``

- "Download Full Log" fetches from S3/Argo artifact storage
- For active deployments, auto-refresh log content every 5 seconds

Real-Time Update Behavior
===========================

- **HTMX polling** is the primary mechanism: ``hx-trigger="every 5s"``
- Polling targets specific partials (status badge, timeline, log content) to
  minimize data transfer
- Active deployments poll every 5 seconds; completed deployments stop polling
- Future enhancement: WebSocket upgrade for true streaming (not in MVP)
- Loading indicators shown during poll requests (small spinner, not full loading bar)


----------------------------------------------
NERD004: RepoClass Discovery
----------------------------------------------

*Cross-reference:* :doc:`NERD004_RepoClass_Discovery`

RepoClass Browser (Search + Cards)
====================================

A searchable, paginated list of available RepoClasses.

.. uml::

   @startsalt
   {
     <b>Repo Classes</b>
     ---
     {
       Search: | "search repo classes...        " | [Search]
     }
     ---
     {#
       <b>Name</b>              | <b>Type</b>       | <b>Latest Version</b> | <b>Instances</b> | <b>Actions</b>
       hmd-ms-gateway          | microservice       | 0.4                    | 5                 | [View Versions]
       hmd-ms-auth             | microservice       | 0.3                    | 3                 | [View Versions]
       hmd-ms-transform        | microservice       | 0.2                    | 2                 | [View Versions]
       hmd-ms-billing          | microservice       | 0.1                    | 1                 | [View Versions]
       hmd-lib-common          | library            | 1.0                    | —                 | [View Versions]
       hmd-inf-networking      | infrastructure     | 0.5                    | 3                 | [View Versions]
     }
     ---
     {
       Showing 1-6 of 12 | . | [< Prev] [Next >]
     }
   }
   @endsalt

**Behavior:**

- Search filters by name (partial match) via HTMX
- "Instances" column shows count of deployed instances across all environments
- "View Versions" navigates to the version detail page
- Type column could use colored badges (microservice=blue, library=green,
  infrastructure=purple)

RepoClass Detail with Versions
================================

Detailed view of a single RepoClass showing all registered versions.

.. uml::

   @startsalt
   {
     <b>Repo Class: hmd-ms-gateway</b>
     ---
     {
       [< Back to Repo Classes]
     }
     ---
     {
       Type: microservice
       Description: API gateway service for NeuronSphere platform
       Total Versions: 3
     }
     ===
     <b>Versions</b>
     {#
       <b>Version</b> | <b>Status</b>  | <b>Created</b>     | <b>Deployed To</b>              | <b>Actions</b>
       0.4            | Active          | 2026-03-01          | dev (2), test (1)                | [View Config]
       0.3            | Active          | 2026-02-15          | prod (1), test (1)               | [View Config]
       0.2            | Deprecated      | 2026-01-20          | —                                | [View Config]
     }
     ===
     <b>Default Configuration (v0.4)</b>
     {T
       + replicas: 3
       + memory: 512Mi
       + cpu: 250m
       + env_vars:
       ++ LOG_LEVEL: info
       ++ PORT: 8080
     }
     ===
     <b>Dependencies (v0.4)</b>
     {
       hmd-ms-auth ~= 0.3
       hmd-lib-common ~= 1.0
     }
     ===
     <b>Instances Across Environments</b>
     {#
       <b>Environment</b> | <b>Instance Name</b> | <b>Version</b> | <b>Status</b>
       dev               | api-gateway-dev       | 0.4             | DEPLOYED
       dev               | api-gateway-canary    | 0.4             | DEPLOYED
       test              | api-gateway-test      | 0.3             | DEPLOYED
       prod              | api-gateway-prod      | 0.3             | DEPLOYED
     }
   }
   @endsalt

**Behavior:**

- "View Config" expands inline to show default_configuration and dependencies
- "Deployed To" links to respective environment BOM views
- Instance list allows quick navigation to any instance detail
- Version status: Active (green badge), Deprecated (gray badge), Latest (blue badge)

Version Registration Form (Admin)
==================================

Admin-only form for registering new RepoClassVersions.

.. uml::

   @startsalt
   {
     <b>Register New Version</b>
     ---
     {
       [< Back to Repo Class]
     }
     ---
     {
       Repo Class:    | <b>hmd-ms-gateway</b> (read-only)
       Version:       | "0.5            "
       Status:        | ^Active^
     }
     ---
     <b>Default Configuration</b>
     {SI
       {
         "replicas": 3,
         "memory": "512Mi",
         "cpu": "250m",
         "env_vars": {
           "LOG_LEVEL": "info",
           "PORT": "8080"
         }
       }
     }
     ---
     <b>Dependencies</b>
     {
       { "dep name  " | "version spec " | [+ Add] }
       hmd-ms-auth | ~= 0.3 | [Remove]
       hmd-lib-common | ~= 1.0 | [Remove]
     }
     ---
     {
       [Cancel] | [Register Version]
     }
   }
   @endsalt

**Behavior:**

- Only accessible to Admin role users
- Version field validates semver format
- Default configuration pre-populated from previous version (editable)
- Dependencies can be added/removed dynamically
- JSON configuration validated on submit
- Success redirects to the RepoClass detail page


----------------------------------------------
NERD005: Service Health & Telemetry
----------------------------------------------

*Cross-reference:* :doc:`NERD005_Service_Health_Telemetry`

Health Dashboard with Traffic Lights
=====================================

A dashboard showing health status of all instances in an environment using
traffic-light indicators.

.. uml::

   @startsalt
   {
     <b>Service Health — dev</b>
     ---
     {
       Environment: | ^dev^  | Auto-refresh: | [X] On | [Refresh Now]
     }
     ===
     <b>Health Overview</b>
     {#
       <b>Instance</b>        | <b>Status</b>    | <b>Health</b>  | <b>Uptime</b>  | <b>Last Check</b>      | <b>Actions</b>
       api-gateway            | DEPLOYED          | (+) Healthy     | 99.9%           | 2026-03-12 14:34        | [Details]
       auth-service           | DEPLOYED          | (+) Healthy     | 99.7%           | 2026-03-12 14:34        | [Details]
       transform-worker       | DEPLOYED          | (!) Degraded    | 98.2%           | 2026-03-12 14:34        | [Details]
       legacy-adapter         | DEPLOYED          | (x) Unhealthy   | 45.3%           | 2026-03-12 14:34        | [Details]
       telemetry-collector    | DEPLOYED          | (+) Healthy     | 100%            | 2026-03-12 14:34        | [Details]
     }
     ---
     {
       Summary: 3 Healthy | 1 Degraded | 1 Unhealthy
     }
   }
   @endsalt

**Traffic light indicators:**

- (+) **Healthy**: all health checks passing, no errors
- (!) **Degraded**: partial failures, elevated error rates, or slow responses
- (x) **Unhealthy**: health check failing, service down, or critical errors

**Behavior:**

- Auto-refresh every 30 seconds when enabled
- Click "Details" to open the full diagnostic view
- Summary bar shows aggregate counts
- Sortable by health status (unhealthy first by default)
- Navigable from BOM view via instance context menu

Error Summary & Performance Metrics
=====================================

Detailed error and performance panel for a single service instance.

.. uml::

   @startsalt
   {
     <b>Service Diagnostics: transform-worker</b>
     ---
     {
       [< Back to Health Dashboard] | . | [Open in HyperDX ↗]
     }
     ---
     {
       Status: DEPLOYED | Health: (!) Degraded | Uptime: 98.2% | Version: 0.2
     }
     ===
     <b>Error Summary (last 24h)</b>
     {#
       <b>Error Type</b>           | <b>Count</b> | <b>First Seen</b>      | <b>Last Seen</b>       | <b>Trend</b>
       TimeoutError                | 23           | 2026-03-12 08:00        | 2026-03-12 14:30        | ↑ increasing
       ConnectionRefusedError      | 5            | 2026-03-12 12:00        | 2026-03-12 13:45        | ↓ decreasing
       ValidationError             | 2            | 2026-03-12 14:00        | 2026-03-12 14:15        | → stable
     }
     ===
     <b>Performance Metrics</b>
     {#
       <b>Metric</b>              | <b>Value</b>  | <b>p50</b>  | <b>p95</b>  | <b>p99</b>
       Response Time              | 245ms          | 120ms        | 890ms        | 2.1s
       Throughput                 | 1,234 req/min  | —            | —            | —
       Error Rate                 | 2.3%           | —            | —            | —
       CPU Usage                  | 67%            | 45%          | 82%          | 91%
       Memory Usage               | 412Mi / 512Mi  | —            | —            | —
     }
     ===
     <b>Severity-Categorized Findings</b>
     {T
       + (x) CRITICAL
       ++ TimeoutError rate exceeding threshold (>20/hr)
       ++ Memory usage approaching limit (80%)
       + (!) WARNING
       ++ p99 response time above SLA (>2s)
       ++ CPU usage elevated during peak hours
       + (+) INFO
       ++ ConnectionRefusedError trend decreasing
     }
   }
   @endsalt

**Behavior:**

- Error table sortable by count, trend
- "Open in HyperDX" links to the external observability platform with pre-filtered
  query for this service
- Performance metrics refreshed every 30 seconds
- Trend indicators: ↑ increasing (red), ↓ decreasing (green), → stable (gray)
- Findings auto-generated from metric thresholds

Trace/Log Explorer with Time Picker
=====================================

Interactive trace and log exploration with time range selection and filtering.

.. uml::

   @startsalt
   {
     <b>Trace & Log Explorer: transform-worker</b>
     ---
     {
       Time Range: | ^Last 1 hour^ | From: | "2026-03-12 13:30" | To: | "2026-03-12 14:30" | [Apply]
     }
     ---
     {
       Level: | ^All Levels^ | Search: | "timeout                    " | [Search]
     }
     ===
     <b>Traces</b>
     {#
       <b>Trace ID</b>          | <b>Operation</b>       | <b>Duration</b> | <b>Status</b>  | <b>Timestamp</b>
       abc-123-def              | POST /api/transform     | 2.3s             | ERROR           | 14:28:45
       ghi-456-jkl              | POST /api/transform     | 890ms            | OK              | 14:28:40
       mno-789-pqr              | GET /api/health         | 12ms             | OK              | 14:28:35
     }
     ===
     <b>Logs</b>
     {SI
       [14:28:45] ERROR transform-worker: TimeoutError processing job-4521
         Traceback: ...
         Duration: 2.3s, Threshold: 1.0s
       [14:28:40] INFO  transform-worker: Successfully processed job-4520
         Duration: 890ms
       [14:28:35] INFO  transform-worker: Health check passed
     }
   }
   @endsalt

**Behavior:**

- Time picker with preset ranges (15m, 1h, 6h, 24h, 7d) and custom range
- Log level filter (DEBUG, INFO, WARN, ERROR)
- Full-text search across log messages
- Trace table links to detailed span view
- Logs auto-tail when viewing "now" (auto-scroll to bottom)
- Error traces highlighted with red left border

Integration with BOM View Navigation
======================================

The health/telemetry views are accessible from multiple entry points:

1. **BOM Table**: right-click context menu on any instance → "View Health"
2. **Instance Detail Panel**: "Health & Telemetry" tab
3. **Sidebar**: dedicated "Health" section (future enhancement)
4. **Dashboard**: environment health summary cards link to health dashboard

Navigation maintains context (environment + instance selection) when switching
between BOM and Health views.


----------------------------------------------
Responsive Behavior
----------------------------------------------

Mobile & Tablet Breakpoints
============================

**Breakpoints (Tailwind defaults):**

- ``sm`` (640px): single-column layout, sidebar hidden by default
- ``md`` (768px): sidebar available as overlay, two-column tables
- ``lg`` (1024px): full layout with persistent sidebar
- ``xl`` (1280px): wider content area, more table columns visible

**Mobile (< 640px):**

- Sidebar becomes a full-screen overlay triggered by hamburger menu
- Tables switch to card-based layout (each row becomes a stacked card)
- Slide-over panel becomes full-screen modal
- Wizard steps stack vertically instead of horizontal stepper
- DAG view simplified to list with indentation

**Tablet (640px–1024px):**

- Sidebar collapses to icon-only by default
- Tables remain tabular but with horizontal scroll
- Slide-over panel width reduces to ``w-80``
- Two-column grid for dashboard cards

**Desktop (> 1024px):**

- Full sidebar expanded by default
- All table columns visible
- Slide-over panel at ``w-96``
- Three-column grid for dashboard cards

**General responsive rules:**

- Touch targets minimum 44x44px on mobile
- Font sizes scale: body 14px (mobile) → 16px (desktop)
- Padding reduces: ``px-4 py-4`` (mobile) → ``px-6 py-6`` (desktop)
- Loading bar visible at all breakpoints
