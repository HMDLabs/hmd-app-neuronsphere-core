.. NERD015 Docs and Scan History Views

NERD015 Docs and Scan History Views
===============================================================

.. req:: The repo class version page links to a version's PDF, renders its HTML documentation, and shows scan results over time
    :id: HMD_APP_NEURONSPHERE_NERD015
    :status: proposed

    A user must be able to open any registered version's Bartleby documentation (rendered HTML in
    the app, or a PDF download) and see that version's build-time and re-scan vulnerability results
    side by side, reading the version's sidecars (``HMD_CLI_BUILD_NERD002``,
    ``NERD0026_HMD_MS_DEPLOYMENT``) and never unpacking the build zip per request.

Sidecars are addressable librarian items at ``<repo>/<version>/<repo>_<version>_<name>``, delivered
by ``NERD0025_HMD_MS_DEPLOYMENT``. ``HMD_APP_NEURONSPHERE_NERD013`` already specifies the
server-side read pattern for the scan summary; this requirement adds documentation and history on
the same pattern.

.. spec:: PDF download and docs entry point
    :id: HMD_APP_NEURONSPHERE_NERD015_SPEC001
    :links: HMD_APP_NEURONSPHERE_NERD015
    :status: proposed

    The version page shows a Documentation section with a PDF download (presigned or streamed after
    the page's authorization check) and an "Open documentation" link. A version with no docs
    sidecar says so plainly. A version picker for the same repo class lists every version that has
    documentation, so earlier versions stay reachable.

.. spec:: HTML served from a content-addressed cache
    :id: HMD_APP_NEURONSPHERE_NERD015_SPEC002
    :links: HMD_APP_NEURONSPHERE_NERD015
    :status: proposed

    On first view of a version's HTML, the server downloads ``_docs.tar.gz``, verifies its sha256
    against ``_sidecars.json``, and extracts it once into a cache directory keyed by
    ``<repo>/<version>/<sha256>/``. A docs view route serves files from that directory with
    path-traversal protection, correct content types, and a restrictive
    ``Content-Security-Policy``/sandboxed ``iframe`` because the HTML is build output. Because the
    key contains the hash and documentation is immutable per version, nothing needs invalidating
    and the cache is safe to delete; eviction is by total size and last access.

    Open question: the cache location and size on the Django deployment (local disk of the pod
    versus a shared volume), given several replicas each hold their own copy.

.. spec:: Scan history on the Security section
    :id: HMD_APP_NEURONSPHERE_NERD015_SPEC003
    :links: HMD_APP_NEURONSPHERE_NERD015
    :status: proposed

    The Security section of ``HMD_APP_NEURONSPHERE_NERD013`` shows the build-time summary labelled
    "At build" and the latest re-scan summary labelled "Latest re-scan", each with its date and
    scanner/database versions, and the change in counts by severity between them. Older dated
    results are listed with their dates and downloads. A version with no re-scan shows only the
    build-time result and says no re-scan has run.
