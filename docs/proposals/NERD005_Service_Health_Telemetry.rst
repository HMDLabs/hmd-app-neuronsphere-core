.. NERD005 Service Health and Telemetry

NERD005 Service Health and Telemetry
=====================================

.. req:: Display service health and telemetry for deployed instances by calling hmd-ms-telemetry-debug APIs.
    :id: HMD_APP_NEURONSPHERE_NERD005
    :status: proposed

    The GUI shall provide a service health and telemetry view that displays health checks,
    diagnostics, error summaries, performance metrics, and trace exploration for deployed instances.
    All data is sourced from hmd-ms-telemetry-debug REST API endpoints. The instance selector is
    populated from the BOM view (NERD001).

Health Check Dashboard
----------------------

.. spec:: Per-instance health check display with traffic-light status indicators.
    :id: HMD_APP_NEURONSPHERE_NERD005_SPEC001
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD005

    The health check dashboard shall display per-instance health status via
    ``POST /apiop/health_check`` (hmd-ms-telemetry-debug).

    Traffic-light indicators shall show health status:

    - Green: healthy
    - Yellow: degraded
    - Red: unhealthy

Full Diagnostic View
--------------------

.. spec:: Comprehensive diagnostic results categorized by severity.
    :id: HMD_APP_NEURONSPHERE_NERD005_SPEC002
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD005

    The diagnostic view shall run comprehensive diagnostics via
    ``POST /apiop/run_diagnostic`` (hmd-ms-telemetry-debug).

    Findings shall be categorized and displayed by severity level.

Error Summary Panel
-------------------

.. spec:: Error counts, types, and trends with HyperDX deep links when available.
    :id: HMD_APP_NEURONSPHERE_NERD005_SPEC003
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD005

    The error summary panel shall display error counts, types, and trends via
    ``POST /apiop/error_summary`` (hmd-ms-telemetry-debug).

    When HyperDX integration is available, deep links shall be provided for further investigation.

Service Performance Metrics
---------------------------

.. spec:: Aggregate statistics, slow operations, and failed operations display.
    :id: HMD_APP_NEURONSPHERE_NERD005_SPEC004
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD005

    The performance metrics view shall display:

    - Aggregate service statistics via ``POST /apiop/service_statistics`` (hmd-ms-telemetry-debug)
    - Slow operations via ``POST /apiop/slow_operations`` (hmd-ms-telemetry-debug)
    - Failed operations via ``POST /apiop/failed_operations`` (hmd-ms-telemetry-debug)

Service Analysis and Trace Exploration
--------------------------------------

.. spec:: Detailed service analysis, trace querying, and log querying with time range picker.
    :id: HMD_APP_NEURONSPHERE_NERD005_SPEC005
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD005

    The analysis and trace exploration view shall provide:

    - Detailed service analysis via ``POST /apiop/analyze_service`` (hmd-ms-telemetry-debug)
    - Trace querying via ``POST /apiop/query_traces`` (hmd-ms-telemetry-debug)
    - Log querying via ``POST /apiop/query_logs`` (hmd-ms-telemetry-debug)
    - Time range picker for all queries

Integration with BOM View
--------------------------

.. spec:: Instance selector populated from BOM with navigation from BOM to telemetry view.
    :id: HMD_APP_NEURONSPHERE_NERD005_SPEC006
    :status: proposed
    :links: HMD_APP_NEURONSPHERE_NERD005

    The telemetry instance selector shall be populated from the BOM data (see
    HMD_APP_NEURONSPHERE_NERD001). A "View Health" action on the BOM view shall navigate
    to the telemetry view filtered by the selected service's telemetry profile.
