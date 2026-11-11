.. NERD016 Navigation Sections and Service View Placement

NERD016 Navigation Sections and Service View Placement
========================================================

.. req:: Navigation sections built from a registry, with services placing their own views
    :id: HMD_APP_NEURONSPHERE_NERD016
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD007, HMD_BASE_SERVICE_NERD003

    The NeuronSphere GUI's left-hand navigation shall be organised into task-oriented
    sections (Home, People, Environments, Catalog, Operations, Services) and built from a
    navigation registry instead of a hand-written template. Core, extension apps and deployed
    services all contribute to the registry. A service places each of its views in a
    section through its ``views.yaml``, may define a section of its own, and may keep a view
    out of the menu. One environment picker in the page header sets the environment every
    section works in, and a service declares when its views belong to the control plane
    and not to the selected environment. Services may also contribute cards to the Home
    dashboard.

Motivation
----------

The sidebar is one template, ``deployments/templates/deployments/partials/sidebar.html``,
with ten flat entries: Dashboard, Environments, Change Sets, Repo Classes, Bundles,
Releases, Resources, Architecture, Services, plus a ``sidebar_nav`` extension slot where the
premium image adds Deployments and Cost. Which entry is active comes from an ``if/elif``
chain on the URL in ``deployments/context_processors.py``. Adding a section (Bundles in
NERD009, Releases in NERD011, Models in NERD010) has meant editing both by hand.

Services can't add an entry at all. Their views (``HMD_BASE_SERVICE_NERD003``) are reached
only through **Services → environment → instance**, so managing users means opening
*Services*, choosing *admin*, choosing *ms-identity*, then *Users*. People think of that as
"Users", not as a property of a microservice instance. The browser also lists every declared
view in its in-page menu, including views that only make sense for one chosen record (a
user's detail page, a group's members), which then open with nothing chosen.

``NERD007_SPEC010`` proposed a navbar registration hook for extension apps but was never
built. This NERD replaces it with a registry that also covers services, and settles the
layout and the environment model the registry serves.

Current entries map to the new sections like this:

====================  ==================  ==========================================
Today                 Section             Note
====================  ==================  ==========================================
Dashboard             Home
Environments, BOM     Environments        per environment, under the picker
Change Sets           Environments
Deployments           Environments        premium
Repo Classes          Catalog
Bundles               Catalog
Releases              Catalog
Resources             Catalog
Architecture          Catalog
Cost                  Operations          premium
(identity views)      People              placed by hmd-ms-identity
Services              Services            browser; fallback for unplaced views
====================  ==================  ==========================================

.. spec:: Navigation registry
    :id: HMD_APP_NEURONSPHERE_NERD016_SPEC001
    :links: HMD_APP_NEURONSPHERE_NERD016
    :status: proposed

    The sidebar shall be rendered from a navigation registry, built per request, holding
    **sections** and **entries**:

    - a section has ``id``, ``title``, ``icon`` and ``order``;
    - an entry has ``section``, ``label``, ``url``, ``icon``, ``order``,
      ``required_permissions`` and an ``active_prefix`` (the URL prefix that marks it
      active).

    Three sources contribute, in this order:

    1. **core**: the built-in sections (SPEC002) and core's own pages;
    2. **extension apps** in ``EXTRA_APPS``: an app's ``nav.py`` exposes
       ``entries(request)`` returning entries, as ``slots.context(request)`` works today;
    3. **services**: placements and sections from the selected environment's (and the
       control plane's) ``view-set`` Resources (SPEC003-SPEC005).

    The active section and entry are derived from the registry: the entry with the longest
    ``active_prefix`` matching the request path. The ``if/elif`` chain in
    ``sidebar_context`` and the ``EXTENSION_SECTIONS`` setting are removed. The
    ``sidebar_nav`` extension slot keeps rendering for one release, so an extension that
    hasn't moved to ``nav.py`` still shows, and is then removed.

    This supersedes ``HMD_APP_NEURONSPHERE_NERD007_SPEC010``.

.. spec:: Built-in sections
    :id: HMD_APP_NEURONSPHERE_NERD016_SPEC002
    :links: HMD_APP_NEURONSPHERE_NERD016, HMD_APP_NEURONSPHERE_NERD016_SPEC001
    :status: proposed

    Core shall define these sections, in this order:

    ==============  ======  ============================================================
    id              order   holds
    ==============  ======  ============================================================
    home            10      Dashboard
    people          20      users, groups and access; empty until a service places
                            views here
    environments    30      the selected environment's BOM, Change Sets, Deployments
    catalog         40      Repo Classes, Bundles, Releases, Resources, Architecture
    operations      50      Cost and operational views placed by services
    services        90      the service browser (NERD007) and every view whose service
                            declares no placement
    ==============  ======  ============================================================

    A section with no entry the user may see is not rendered. Section titles and icons are
    core's; a service can add entries to a built-in section but can't rename it.

.. spec:: Service view placement
    :id: HMD_APP_NEURONSPHERE_NERD016_SPEC003
    :links: HMD_APP_NEURONSPHERE_NERD016, HMD_BASE_SERVICE_NERD003_SPEC008
    :status: proposed

    A view declaration in ``views.yaml`` shall accept an optional ``nav`` field::

        - id: users-list
          title: Users
          path: /views/users
          nav: {section: people, label: Users, order: 10}

        - id: user-detail
          title: User
          path: /views/users/detail
          nav: false

    - ``nav: {section, label?, order?}`` places the view as an entry in that section.
      ``label`` defaults to ``title``; ``order`` to the view's ``order``.
    - ``nav: false`` keeps the view out of every menu, the section sidebar and the service
      browser's in-page menu alike. The view stays routable: links and forms inside other
      views reach it through the proxy exactly as now. Use it for views about one chosen
      record.
    - no ``nav`` keeps today's behaviour: the view is listed in the service browser under
      Services, and nowhere else.

    A placed view is still listed in the service browser, so Services remains the complete
    inventory of a service's views.

.. spec:: Service-defined sections
    :id: HMD_APP_NEURONSPHERE_NERD016_SPEC004
    :links: HMD_APP_NEURONSPHERE_NERD016, HMD_APP_NEURONSPHERE_NERD016_SPEC003
    :status: proposed

    A service may define sections of its own in ``views.yaml``::

        sections:
          - {id: data-products, title: Data products, icon: cube, order: 45}

    and place views in them as in SPEC003. Rules:

    - **Built-in ids win.** A service section whose ``id`` is a built-in one is ignored,
      with a warning at synth and in the GUI log; the service's placements still land in the
      built-in section.
    - **First declaration wins across services.** When two services define the same ``id``,
      the definition from the instance whose name sorts first is used and the other is
      logged; both services' placements land in it. Services sharing a section is the
      point, so this is not an error.
    - ``order`` is a number like the built-ins'. A section without ``order`` sorts after
      every ordered one, by title.
    - A section with no visible entries is not rendered, the same as SPEC002.

    ``icon`` comes from the curated set of ``NERD007_SPEC006``.

.. spec:: Environment picker in the header
    :id: HMD_APP_NEURONSPHERE_NERD016_SPEC005
    :links: HMD_APP_NEURONSPHERE_NERD016
    :status: proposed

    The page header shall carry one environment picker listing the environments the user
    may view. The selected environment:

    - is carried in the URL as ``?env=<name>`` on every page that depends on it, so a link
      or bookmark opens the same environment;
    - is remembered in the session as the default for pages opened without ``env``;
    - falls back to the user's first viewable environment.

    Environment-scoped pages read it from the request (one helper, replacing the
    ``/bom/<env>/`` path parsing in ``sidebar_context`` and the ``?environment=`` query in
    ``ns_service_views``). Existing ``/bom/<env>/`` URLs redirect to their ``?env=`` form.

    Service placements come from the selected environment's ``view-set`` Resources, so the
    People or Operations entries follow the picker unless the service is control-plane
    scoped (SPEC006). Changing environment re-renders the sidebar.

    The picker is **hidden** on pages that don't depend on an environment: Catalog pages
    (Repo Classes, Bundles, Releases, Resources, Architecture) are platform-wide. A registry
    entry declares ``environment_scoped`` (default true for Environments, Operations and
    service placements, false for Catalog), and the header shows the picker only when the
    active entry is environment scoped. The session keeps the selection while it's hidden.

.. spec:: Control-plane scoped services
    :id: HMD_APP_NEURONSPHERE_NERD016_SPEC006
    :links: HMD_APP_NEURONSPHERE_NERD016, HMD_APP_NEURONSPHERE_NERD016_SPEC005
    :status: proposed

    Some services run once, in the control plane, and act on every environment.
    hmd-ms-identity is one: users and their access across all environments are managed from
    its admin instance. Their views shall not depend on the picker.

    ``views.yaml`` shall accept a top-level ``scope``::

        scope: control-plane   # or: environment (the default)

    - The GUI shall discover control-plane view-sets in its own control-plane environment,
      named by the ``CONTROL_PLANE_ENVIRONMENT`` setting (``admin`` in the hosted platform,
      the local environment under nsctl), as well as in the selected environment.
    - A control-plane service's placements are shown whatever environment is selected, and
      its entries are proxied to the control-plane instance.
    - Each of its views declares whether it works on one environment, with
      ``uses_environment`` (default false for a control-plane service)::

          - id: groups-list
            path: /views/groups
            nav: {section: people, label: Access groups}
            uses_environment: true

      A view with ``uses_environment: true`` (identity's Access groups, App access) shows
      the picker, and the GUI adds the picked environment to the proxied request as its
      ``environment`` query parameter. A view without it (identity's Users: the same people
      whatever is picked) hides the picker, as Catalog pages do (SPEC005). The sidebar marks
      the latter as applying to all environments.
    - In the service browser, a control-plane service appears under the control-plane
      environment only, not once per environment.

.. spec:: Section URLs for service views
    :id: HMD_APP_NEURONSPHERE_NERD016_SPEC007
    :links: HMD_APP_NEURONSPHERE_NERD016, HMD_APP_NEURONSPHERE_NERD007_SPEC003
    :status: proposed

    A placed view shall have a URL in its section that doesn't name the instance:
    ``/<section>/<service>/<view-id>/`` (for example ``/people/identity/users-list/``),
    where ``service`` is the repo class without its ``hmd-ms-`` prefix. The page mounts the
    view through the existing proxy (``NERD007_SPEC003``), with the same permission checks
    and the same rule that only inventory-listed paths are forwarded.

    The instance is resolved from the inventory: the control-plane instance for a
    control-plane service, otherwise the service's instance in the selected environment.
    When an environment has several instances of one repo class with placed views, each
    gets its own entry, labelled ``<label> (<instance>)``, and the section URL takes
    ``?instance=``.

    Service browser URLs (``/services/<environment>/<instance>/``) keep working.

.. spec:: Declaration and Resource changes
    :id: HMD_APP_NEURONSPHERE_NERD016_SPEC008
    :links: HMD_APP_NEURONSPHERE_NERD016, HMD_BASE_SERVICE_NERD003_SPEC008, HMD_BASE_SERVICE_NERD003_SPEC005
    :status: proposed

    The new fields travel the same path as today's view metadata:

    - **hmd-base-service:** ``ViewDeclaration`` gains ``nav`` (``false`` or
      ``{section, label?, order?}``), ``uses_environment`` and ``dashboard`` (SPEC011);
      ``ViewsFile`` gains ``sections`` and ``scope``. Both
      models forbid unknown fields, so a service can't use the new fields until it builds on
      a base-service release that has them. ``/views/manifest`` returns them. The
      both-direction binding check (``NERD003_SPEC005``) also checks that a ``nav.section``
      names a built-in section or one declared in ``sections``.
    - **hmd-lib-cdktf-factories:** ``PUBLISHED_KEYS`` gains ``nav``, ``uses_environment`` and
      ``dashboard``, and the ``view-set``
      output gains ``sections`` and ``scope``.
    - **hmd-ms-deployment-core:** ``ui.neuronsphere.io/view-set`` 0.2.0 adds ``nav``,
      ``uses_environment`` and ``dashboard`` to each view, and ``sections`` and ``scope`` to the output. All are optional, so 0.1.0
      outputs stay valid.
    - **hmd-app-neuronsphere-core:** ``ServiceViews.from_output`` reads the new fields;
      absent ones mean today's behaviour.

    Release order: deployment-core, base-service, factories, app-core, then services. A GUI
    without this NERD ignores the new fields, so a service that already uses them still
    shows under Services.

.. spec:: Premium and extension apps move to the registry
    :id: HMD_APP_NEURONSPHERE_NERD016_SPEC009
    :links: HMD_APP_NEURONSPHERE_NERD016, HMD_APP_NEURONSPHERE_NERD016_SPEC001
    :status: proposed

    ``deployments_premium`` (hmd-app-neuronsphere) shall contribute Deployments to
    ``environments`` and Cost to ``operations`` through ``nav.py``, with the same gating as
    today: Deployments when the premium probe passes, Cost for superusers. Its
    ``sidebar_nav`` slot template and the ``EXTENSION_SECTIONS`` setting in its Dockerfile
    are then removed.

.. spec:: hmd-ms-identity places its views under People
    :id: HMD_APP_NEURONSPHERE_NERD016_SPEC010
    :links: HMD_APP_NEURONSPHERE_NERD016, HMD_APP_NEURONSPHERE_NERD016_SPEC003, HMD_APP_NEURONSPHERE_NERD016_SPEC006
    :status: proposed

    The first service to use placement, and the acceptance case for this NERD:

    - ``scope: control-plane``;
    - Users, Access groups and App access placed in ``people``; Access groups and App
      access declare ``uses_environment: true``, Users doesn't;
    - Add user and Edit trigger group placed in ``people`` for admins
      (their ``required_permissions`` already hide them from readers);
    - User, Deactivate user and Group members declared ``nav: false``.

    With admin selected or with dev selected in the picker, **People → Users** opens
    identity's users list served by the admin instance, without visiting Services, and
    the Home dashboard shows identity's users summary card (SPEC011).

.. spec:: Dashboard cards from services
    :id: HMD_APP_NEURONSPHERE_NERD016_SPEC011
    :links: HMD_APP_NEURONSPHERE_NERD016, HMD_APP_NEURONSPHERE_NERD016_SPEC003, HMD_APP_NEURONSPHERE_NERD016_SPEC006
    :status: proposed

    A service may contribute cards to the Home dashboard. A view declaration accepts an
    optional ``dashboard`` field::

        - id: users-summary
          title: Users
          path: /views/users/summary
          nav: false
          dashboard: {order: 20, size: small}

    - The view is a small HTML fragment (counts, a short list, a link into its section),
      rendered through the same proxy and permission checks as any view. ``size`` is
      ``small`` (one grid cell) or ``wide`` (two); ``order`` sorts cards after core's own.
    - Cards load independently and lazily (``hx-trigger="load"``), each with a timeout, so a
      slow or failing service shows a placeholder in its card and never delays the
      dashboard. The GUI's own dashboard content renders first.
    - Card discovery follows SPEC005 and SPEC006: an environment-scoped service's cards come
      from the selected environment; a control-plane service's cards appear whatever is
      selected.
    - A user sees only cards whose ``required_permissions`` they hold.
    - The registry's Home section lists the dashboard; cards are not menu entries.
    - A card may ask to refresh with ``dashboard: {refresh: 60}`` (seconds, at least 30).
      The GUI reloads just that card's fragment on that interval
      (``hx-trigger="load, every 60s"``), and only while the browser tab is visible, so an
      idle tab costs nothing. Without ``refresh`` a card loads once per visit.

    hmd-base-service, the factories and the ``view-set`` definition carry ``dashboard`` the
    same way as ``nav`` (SPEC008). hmd-ms-identity's first card, a users summary (active,
    staged and deactivated counts, with a link to People → Users), is part of SPEC010's
    acceptance.
