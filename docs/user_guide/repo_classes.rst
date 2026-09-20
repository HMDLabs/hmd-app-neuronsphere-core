Browsing Repo Classes and Versions
==================================

A **repo class** is a deployable component type. The **Repo Classes** area lets
you browse the full catalog of repo classes and inspect the versions published
for each one — useful when you are deciding which class and version to add to a
ChangeSet.

Listing Repo Classes
--------------------

In the sidebar, click **Repo Classes** (the URL is ``/repo-classes/``). The
page lists the available repo classes.

.. figure:: /images/repo_class_list.png
   :alt: Repo Classes list with name, type, latest version and actions
   :width: 100%

   The repo class catalog.

Each row shows the class **Name** (with its type beneath), a one-paragraph
**Summary** of what the class does — taken from the latest version's manifest,
with a count of the capabilities it declares — and its **Latest Version**. To
find a specific class, type into the search box and click **Search**; the list
filters by name, type or summary. Long catalogs are paginated — use the
**Previous** / **Next** controls at the bottom, which preserve your search
term.

Click a class **Name** (or its **View Versions** link) to see its versions.

Finding a Repo Class by Capability
----------------------------------

When you know what you need done but not which class does it, use the **Find
by capability** panel on the same page. Every repo class's latest version
declares its capabilities — the endpoints it serves, the CLI commands, functions
and classes it provides, and the operations it performs — in its manifest's
``discovery`` section, and this panel searches all of them at once.

Type a few words describing what you need (for example ``rotate logs`` or
``provision vpc``) and click **Find**. Every word must appear somewhere in a
class's summary, a capability's name or description, or an entry point, so if
nothing matches try fewer or broader words. Pick a **kind** from the drop-down
to narrow to one kind of capability; changing it re-runs the search
immediately.

Results appear beneath the form as one row per matching capability, showing the
**Repo Class**, the **Version** it was found in, the **Capability** name, its
**Kind**, a **Description** and, where the manifest recorded one, the source
**Location** (``path:line``). Click the class to see its versions, or the
version to open that version's detail page. Classes whose *summary* matched but
which declared no matching capability are listed separately below the table.
Results are paginated when there are many.

The same search is available to AI agents through the MCP server's
``search_capabilities`` tool.

Viewing Repo Class Versions
---------------------------

The detail page for a repo class (``/repo-classes/<name>/``) lists every
published version.

.. figure:: /images/repo_class_versions.png
   :alt: Repo class versions with expandable default configuration
   :width: 100%

   Each version can expose its default configuration.

For each version you see the **Version** number and its **Default
Configuration**. Where a default configuration exists, click **Show** to expand
it and view the configuration as formatted JSON. Use the breadcrumb at the top
of the page to return to the full **Repo Classes** list.

Click a version to open its detail page
(``/repo-classes/<name>/versions/<version>/``). Its **Discovery** card shows the
version's summary, entry points, capabilities and related docs from the
manifest; the capabilities table includes each capability's **Kind** and, where
recorded, its source **Location**.
