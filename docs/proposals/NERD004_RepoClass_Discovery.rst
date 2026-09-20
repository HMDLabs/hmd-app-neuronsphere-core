.. NERD004 RepoClass Discovery

NERD004 RepoClass Discovery
=============================

.. req:: Search, browse, and manage RepoClasses and versions for deployment.
    :id: HMD_APP_NEURONSPHERE_NERD004
    :status: proposed

    The GUI shall provide a RepoClass discovery interface allowing users to browse all available
    RepoClasses, view version details and default configurations, see where instances are deployed
    across environments, and register new versions.

RepoClass Browser
-----------------

.. spec:: Searchable list of all available RepoClasses.
    :id: HMD_APP_NEURONSPHERE_NERD004_SPEC001
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD004

    The RepoClass browser shall display a searchable, filterable list of all RepoClasses
    showing name, description, latest version, and repo type.

    *Requires new* ``GET /apiop/list_repo_classes`` *endpoint in hmd-ms-deployment.*

Version Listing and Details
---------------------------

.. spec:: Version listing via find_repo_class_versions with detail view showing default configuration and dependencies.
    :id: HMD_APP_NEURONSPHERE_NERD004_SPEC002
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD004

    Selecting a RepoClass shall display available versions via
    ``POST /apiop/find_repo_class_versions/<name>``.

    A version detail view shall show:

    - Default configuration
    - Dependencies with version specs
    - Configuration schema (if available)

    *Detail view requires new* ``GET /apiop/get_repo_class_version/<name>/<version>``
    *endpoint in hmd-ms-deployment.*

Instance Overview per RepoClass
-------------------------------

.. spec:: View deployed instances of a RepoClass across environments.
    :id: HMD_APP_NEURONSPHERE_NERD004_SPEC003
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD004

    The RepoClass detail page shall show all deployed instances across environments via
    ``GET /apiop/get_repo_class_instances/<name>/<type>``. This provides a cross-environment
    view of where a given RepoClass is deployed and at which versions.

Version Registration
--------------------

.. spec:: Admin form to register new RepoClassVersions via add_repo_class_version.
    :id: HMD_APP_NEURONSPHERE_NERD004_SPEC004
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD004

    Admin users shall be able to register new RepoClassVersions through a form that submits to
    ``POST /apiop/add_repo_class_version``. This action shall be gated by the Admin RBAC role.

Capability Search
-----------------

.. spec:: Find repo classes by what they can do, from their BACON discovery metadata.
    :id: HMD_APP_NEURONSPHERE_NERD004_SPEC005
    :status: completed
    :links: HMD_APP_NEURONSPHERE_NERD004

    The Repo Classes page shall let a user answer "which repo class can do X?" from the
    ``discovery`` block each class's latest version carries (``hmd-ms-deployment`` NERD0013),
    without opening each version in turn:

    - the catalog table shall show each class's discovery **summary** (with its capability
      count) beside its name, and the existing search box shall match the summary as well as
      the name and type -- both from the ``summary`` / ``capability_count`` fields
      ``list_repo_classes`` now returns;
    - a **Find by capability** form shall search every class's declared capabilities and
      entry points through ``GET /apiop/search_discovery``, with a free-text query and a
      capability **kind** select (``endpoint``, ``cli_command``, ``function``, ``class``,
      ``operation``), rendering one row per matching capability -- class, version, name, kind,
      description and source location -- each linking to the version's detail page, plus the
      classes that matched on summary alone. Results load as an HTMX partial
      (``/repo-classes/capabilities/``), paginate, and make no backend call until a query or
      kind is given;
    - the version detail page's Discovery card shall show each capability's ``location``.

    The row shaping is a pure service function (``build_capability_rows``) shared with the MCP
    ``search_capabilities`` tool (NERD008 SPEC015), so the two surfaces cannot drift. A
    catalog read: ``login_required`` only, no environment scoping.
