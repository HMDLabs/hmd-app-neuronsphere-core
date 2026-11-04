.. NERD014 Data Product Tools

NERD014 Data Product Tools
==========================

.. req:: Data product tools on the NeuronSphere MCP server
    :id: HMD_APP_NEURONSPHERE_NERD014
    :links: HMD_APP_NEURONSPHERE_NERD012
    :status: proposed

    The NeuronSphere MCP server shall offer the control-plane tools that agents
    need to review data product changes and migrate consumers:
    ``check_product_change``, ``product_consumers`` and
    ``consumer_migration_context``. They run with the caller's identity, return
    structured JSON with documented schemas, and change nothing.

*Stub.* This NERD is a placeholder from ``hmd-core-arch-docs`` NEP050 (*Agent
support for agents the customer brings*). Specs are to be written before
implementation.

Scope
-----

* ``check_product_change(product, candidate_contract, candidate_sql?)``: the change
  report from ``HMD_LIB_QUERY_PROMOTION_NERD001`` against the deployed version,
  marked as run under the caller's authorization.
* ``product_consumers(product, version?)``: declared consumers (``hmd-ms-deployment``
  NERD0022), dashboard consumers (Superset metadata) and observed consumers
  (``HMD_MS_LIBRARIAN_QUERY_NERD002``), each with the columns it uses. Observed
  principals are listed only to callers allowed to see them.
* ``consumer_migration_context(consumer_repo_class, product, to_version)``: the
  consumer's SQL that references the product, the column mapping, the contract diff
  and the consumer's expectations.
* Results are bounded and paged; every tool has a CLI equivalent with the same
  output.

Acceptance sketch
-----------------

* For a fixture product with one declared consumer, one chart and one ad-hoc user,
  ``product_consumers`` lists all three with their columns.
* ``check_product_change`` returns the same report as the CLI for the same inputs.
* A caller without access to an environment gets no results for it
  (``HMD_APP_NEURONSPHERE_NERD012``).

Open items
----------

* Whether ``consumer_migration_context`` should return file contents or only paths
  and line ranges, given that agents usually have the repository checked out.
