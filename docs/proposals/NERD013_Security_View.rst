.. NERD013 Security View

NERD013 Security View
===============================================================

.. req:: Show a repo class version's scan summary and let users download its SBOM
    :id: HMD_APP_NEURONSPHERE_NERD013
    :status: proposed

    The repo class version page must show the security scan results for that version and offer the
    full SBOM for download, reading them from the artifact librarian's cached objects and not from
    the deployment service.

``repo_class_version_detail`` (``deployments/views.py``) renders sections built by
``build_repo_class_version_detail_sections`` in ``services/repo_class_detail.py``, from data fetched
by ``DeploymentAPIClient`` over REST. The app has no storage access today. Scan results are
published to the librarian's security route at ingest (``NERD0020_HMD_MS_DEPLOYMENT``) and are
intentionally not part of the deployment service's data. The view therefore reads the small
``summary.json`` directly from storage.

.. spec:: Security section on the version page
    :id: HMD_APP_NEURONSPHERE_NERD013_SPEC001
    :links: HMD_APP_NEURONSPHERE_NERD013
    :status: proposed

    Add a Security section showing the scan time and status, the scanner versions, the component
    count, and vulnerability counts by severity, rendered from ``summary.json``. A version with no
    scan data shows that fact plainly, and a ``partial`` or ``skipped`` status is shown as such, not
    as a clean result. Large lists (components, individual findings) are not rendered from the SBOM
    in the first iteration.

.. spec:: Server-side read with caching
    :id: HMD_APP_NEURONSPHERE_NERD013_SPEC002
    :links: HMD_APP_NEURONSPHERE_NERD013
    :status: proposed

    A function in ``services/`` reads ``security/<repo_name>/<repo_version>/summary.json`` from the
    librarian bucket with boto3, using the session and bucket-from-environment pattern already used
    for storage reads elsewhere in the platform. Results are cached with the existing
    ``cache_key``/``cache_ttl`` mechanism. Storage credentials stay in the server; the browser never
    receives them.

.. spec:: SBOM download
    :id: HMD_APP_NEURONSPHERE_NERD013_SPEC003
    :links: HMD_APP_NEURONSPHERE_NERD013
    :status: proposed

    A download action returns the version's ``sbom.cdx.json``, either as a short-lived presigned URL
    or streamed by the view, after the same authorization check as the page. Downloading the
    vulnerability report is offered the same way.

.. spec:: Out of scope for the first iteration
    :id: HMD_APP_NEURONSPHERE_NERD013_SPEC004
    :links: HMD_APP_NEURONSPHERE_NERD013
    :status: proposed

    An MCP tool for questions such as "which versions have critical findings", and an aggregate SBOM
    for a whole environment BOM (the union of its versions' SBOMs), are follow-ups.
