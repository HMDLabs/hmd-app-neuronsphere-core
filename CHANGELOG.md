# Changelog

All notable changes to this project will be documented in this file.

## 2026-09-20

- feat: split out of hmd-app-neuronsphere as the core GUI (NERD0015): every view
  except run observability and apply, plus the extension seam (`DJANGO_EXTRA_APPS`,
  `DEPLOYMENT_API_CLIENT_CLASS`, `{% extension_slot %}`, `EXTENSION_SECTIONS`) the
  premium overlay plugs into. History before this date is hmd-app-neuronsphere's.

## 2026-09-16

### Added

- feat: **Find by capability** on the Repo Classes page (NERD004 SPEC005). A free-text query plus a capability-kind select searches every repo class's latest-version BACON `discovery` block through the new `GET /apiop/search_discovery` (hmd-ms-deployment NERD0013) and renders one row per matching capability -- class, version, name, kind, description, source location -- each linking to the version's detail page, with summary-only hits listed beneath. Loads as an HTMX partial (`/repo-classes/capabilities/`, registered before the `<repo_class_name>/` route so the word is not taken for a class), paginates, and makes no backend call until a query or kind is given. The catalog table gains a **Summary** column (with capability count) and the existing search box matches it; the version detail Discovery card gains a **Location** column and colours the kind badges.

- feat: MCP `search_capabilities` tool (NERD008 SPEC015) -- "which repo class can do X?" for agents. One `search_discovery` call, `kind` validated locally, rows shaped by the same `build_capability_rows` the GUI renders so the two cannot drift; `repo_classes` lists every ranked hit including summary-only ones for a `describe_repo_class` follow-up. Also a templated `neuronsphere://repo-classes/{repo_class_name}/discovery` resource (exact-name pick over the backend's prefix filter, so `hmd-ms-deploy` does not answer for `hmd-ms-deployment`) and a `find_capability` prompt recording the call order.

### Fixed

- fix: MCP `search_repo_classes` emitted a `description` that was always empty, because `list_repo_classes` never carried one. It is now the latest version's discovery summary (with `latest_version` and `capability_count`), and the query matches it.

## 2026-09-11

### Added

- feat: the GUI is no longer Okta-only. `OAUTH_PROVIDERS` is a JSON list of identity providers -- Okta, Auth0, Entra, or a customer's own -- each registered as one allauth `openid_connect` app, so adding an IdP is configuration rather than a code change. Group-to-environment-role mappings and superuser groups gain provider-scoped forms (`IDP_GROUP_MAPPING`, `IDP_SUPERUSER_GROUPS`, keyed by `provider_id`) so two providers can use the same group name for different things, and each provider names the claim that carries its group membership, because the name is not universal -- Auth0 commonly namespaces it and Entra may use `roles`.

  Backward compatible: the single-provider `OAUTH_PROVIDER_URL` form synthesises one `okta` provider, the unscoped `OKTA_GROUP_MAPPING` / `OKTA_SUPERUSER_GROUPS` still apply to every provider, and `sync_okta_permissions` remains as an alias of `sync_idp_permissions`.

- feat: `idpProvidersSecret` chart value, backed by a new `idp-providers` ExternalSecret, so the provider list -- which carries client secrets -- comes from the secret store rather than the ConfigMap.

### Fixed

- fix: the `uid` lookup that maps a verified bearer token to a Django user searched every provider's accounts. `SocialAccount` is unique on *(provider, uid)*, not on `uid` alone, so with two IdPs configured a shared `uid` could resolve a token minted by one provider onto the other provider's user. The lookup is now scoped by the provider the verified issuer names, falling back to the unscoped search when no configured provider matches -- which is the case for every single-provider deployment.

- fix: `MCP_OKTA_ISSUER` was read from `OAUTH_PROVIDER_URL` alone. A deployment that moved to `OAUTH_PROVIDERS` has no such variable, so the issuer came out empty and `MCP_OKTA_ENABLED` gated itself off -- MCP bearer auth silently disabled rather than failing loudly. It now resolves from the configured provider list. JWKS derivation stays unconditional: an Okta org fronted by its own domain is not recognisable from its issuer, and refusing to derive would break exactly those deployments.

- fix: `get_okta_social_token` selected a row with no ordering, so a user who had linked two IdPs could have an expired token forwarded downstream while a live one sat beside it. Latest expiry now wins, with rows carrying no expiry sorted last.

## 2026-09-04

### Fixed

- fix: opening **Edit instance** on a ChangeSet item hung while the version list loaded, and the resulting dropdown was unusable for repo classes with many releases. The panel blocked on `find_repo_class_versions`, which fetches *every* version in one request and -- because it was called without `include_deps=false` -- also made the microservice resolve dependencies per version, work the editor renders none of. It was uncached too, so every open paid the full cost again. The panel now renders with no API call at all and pulls one 50-item page afterwards through `find_repo_class_versions_page`, the same searchable, paginated, cached path the Add Instance form has used all along. The hidden version input is pre-seeded with the item's current version, so editing only the Deployment ID or Configuration needs no trip through the list and the current version never has to appear on the fetched page.

- fix: the version search box filtered nothing. htmx submits a named search input under its own name, so the Add Instance picker sent `version_q=`, while `api_repo_class_versions_options` read only `?q=` -- every keystroke re-fetched an unfiltered page 1. The view now accepts either spelling. This was invisible while only the Add form used the endpoint; the new Edit instance picker would have shipped a dead search box too.

- fix: the Add Instance dependency cascade included its fields with `[name=version]`, which also matched the hidden version input of every open Edit instance panel (as it previously matched their `<select name="version">`). With several panels open, the version htmx sent was whichever one happened to come last in the document. The cascade now includes by id, and the version picker's pagination carries its state in the request URL rather than an `hx-include` of `[name=...]` selectors that reach across panels. Picker element ids are suffixed with the ChangeSet item index, derived server-side from `?item_index=` rather than reflected from the query string.

## 2026-09-03

### Added

- feat: The deployment detail page's Status tab now shows the workflow as a colour-coded DAG instead of a flat list of Argo pod names. Steps are labelled by the RepoInstance they deploy, wired by the same dependencies the Argo DAG tasks use, and laid out server-side with graphviz (`dot -Tjson` for geometry only; the SVG is emitted by `partials/deployment_dag.html` so each node can carry its own `hx-get`). Clicking a node swaps that step's archived log into a panel below the graph -- deliberately outside the 5s status poll, which would otherwise wipe an open log mid-read. Layout toggles between left-to-right and top-to-bottom. Node colours come from RepoInstanceDeployment status, so they stay correct long after Argo has discarded the workflow. Falls back to a plain step list if the image was built without graphviz.

### Fixed

- fix: the GUI pod OOMKilled on startup in every cloud environment (CrashLoopBackOff). `gunicorn.conf.py` sized its worker pool with `multiprocessing.cpu_count() * 2 + 1`, and `cpu_count()` reports the host node's cores while ignoring the container's cgroup CPU quota -- so a pod limited to `cpu: 500m` forked 33 workers on a 16-vCPU node. `configmap.yaml` already carried a guard for exactly this, and a comment naming this exact OOM, but it emits `GUNICORN_WORKERS` only `if .Values.config.gunicornWorkers` and that key existed solely in `config_local.json`. The guard therefore fired on local k3s and never once in the cloud -- a gap open since the cap was added in response to the same OOM locally. What made it fatal was the MCP server: since `915d4ef` every worker imports Django *and* builds the FastMCP app independently (`asgi.py`, no `preload_app`), so per-worker RSS rose sharply against a `512Mi` limit last set in May, before any of it existed. All N workers boot at once, which is why the pod died during startup rather than under load. `gunicornWorkers` is now set in the manifest's cloud defaults, and the limit raised to `1Gi` to match what local already used. Independently, `gunicorn.conf.py` no longer trusts `cpu_count()`: the default derives from the cgroup quota (v2 `cpu.max`, v1 `cfs_quota_us`/`cfs_period_us`, host cores only as a last resort) and clamps to `max(2, min(cpus * 2 + 1, 8))`, so a missing config key can never reproduce this. `GUNICORN_WORKERS` still takes precedence. Verified by rendering the chart from the real manifest defaults -- it now emits `GUNICORN_WORKERS: "3"` and `memory: 1Gi`, where the pre-change values emitted no `GUNICORN_WORKERS` line at all.

- fix: `configmap.yaml`'s derived `DEPLOYMENT_API_URL` fallback (used whenever `config.deploymentApiUrl` is not explicitly overridden -- every cloud deploy) ended its variable assignment with a trailing `-}}`, which trims trailing whitespace *including the next line's leading indentation*. With nothing after it to reintroduce that whitespace, `DEPLOYMENT_API_URL` rendered glued onto the previous key's line, which `helm upgrade` rejected as invalid YAML ("did not find expected key"). Every existing render test's fixture set `config.deploymentApiUrl` explicitly, which takes the sibling `if` branch and never touched this code path -- `test_deployment_api_url_falls_back_to_the_derived_cloud_url` now exercises it directly.

## 2026-09-02

### Fixed

- fix: six views accepted an environment named by the caller behind only `@login_required`, and fetched that environment's data without checking the caller could see it: `api_search_instances`, `api_search_instances_html`, `api_dep_candidates`, `api_repo_class_version_resources`, `changeset_bom_impact`, and `environment_compare_create_changeset`. The last is the one that matters most and was not on the list of known gaps -- it is a POST that copies the named environments' instance records into a persisted ChangeSet draft, so the data did not merely get displayed, it got kept. Its single-environment sibling `bom_create_changeset` carries `@require_environment_access("deploy")`, which is what marks the omission as an oversight rather than a decision. `api_search_instances` also defaulted to `environment="dev"`, so a request naming no environment searched one anyway; the parameter is now required.
- fix: `require_deployment_set_access` called the view unconditionally when it found no deployment set in kwargs, POST, or GET. Applied to a view that carried the set anywhere it did not look, it would have protected nothing while appearing to. It now denies by default, and opting out is something a view has to say (`when_missing="defer"`). It is still applied to zero views: `changeset_apply`, the only view taking a deployment set, checks inline so it can redirect with a message rather than render a 403 at a POSTed form -- but it now calls `user_has_deployment_set_access` instead of reaching into the model.

### Changed

- refactor: `require_environment_access` grew the three options those six views needed, rather than having each hand-roll a check. `param` accepts a tuple so a view spanning two environments authorizes both, first failure wins -- mirroring `@read_tool`'s `environment_arg`. `when_missing="defer"` hands off to the view when no environment is named, which is what the HTMX partials that render a "pick an environment" hint require, and is safe precisely because no environment means no environment data is fetched. `response` selects the denial shape: `access_denied.html` extends `base.html`, so returning it to a caller expecting JSON, or swapping it into an HTMX target, turns a correct 403 into a broken page. Defaults are unchanged, so the five existing call sites are untouched.
- refactor: `environment_compare`, `resource_list`, and `changeset_apply` call `services/authz` instead of the permission models directly, so every surface shares one definition of the decision. **Correcting the record:** earlier notes described these inline checks as missing the superuser short-circuit. They did not -- `UserEnvironmentPermission.user_can_view` and its `DeploymentSetPermission` counterparts short-circuit on `is_superuser` themselves. This is a single-definition change with no behavioral effect, and the tests below pass against the code both before and after it.

### Added

- feat: Okta bearer tokens are now a credential the MCP server accepts, which is what makes it usable in cloud at all. `OktaUserVerifier` validates the token against the same authorization server the GUI logs in against -- JWKS at `{OAUTH_PROVIDER_URL}/v1/keys`, so no new secret -- and then does the part that is specific to this application: resolving it to the NeuronSphere account whose environment permissions the tools apply. The join is on the access token's `uid` claim against `SocialAccount.uid`, *not* `sub`: allauth stores the ID token's `sub` (the Okta user id, `00u...`) there, while an access token's `sub` is the email, so matching on `sub` first would have missed every user. A `sub`-to-email fallback covers an authorization server that does not emit `uid`, and is safe because issuer and audience are verified before it runs. A token that verifies but belongs to nobody here is deliberately not a 401 -- it comes back tagged and without a user id, which `resolve_principal` turns into "sign in to the Deployment GUI once", an answer the caller can act on.
- feat: the protected-resource metadata document (RFC 9728), served at the host root rather than under the mount. `MultiAuth(server=RemoteAuthProvider(...), verifiers=[ApiKeyVerifier()])` accepts either credential, and the Okta side goes in as `server=` rather than as a second verifier because `MultiAuth` delegates `get_routes` only to its server -- an Okta side passed as a verifier would authenticate but never advertise itself. `asgi.py` splices those routes in above the Django catch-all, since a route registered by the FastMCP app alone would only ever be reachable at `/mcp/.well-known/...`, where no client looks.
- feat: `check_mcp_token`, a management command that answers the one question the code cannot. hmd-ms-deployment verifies a *human* caller against `api://neuronsphere`, but only when the token's `cid` is a trusted human client there; anything else is treated as a service token and checked against a different audience entirely. So forwarding the caller's own bearer works or does not work depending on a fact about the other service. Point this at a real token and read the `cid` line. If the client is not trusted downstream, the fix is to register it (hmd-lib-auth NERD001), not to switch `MCP_DOWNSTREAM_TOKEN_MODE`.
- feat: the rest of the read-only MCP tool surface, taking it from five tools to eleven. `get_instance_configuration` is the cheap sibling of `describe_instance` -- one `get_deployment_config` and no role classification -- and can narrow what it returns before returning it: `keys_only=true` reports each key with its type instead of its value, and `path` drills in with a dotted path that indexes lists (`dependencies.db.0.instance_name`), so a several-hundred-key config is navigable in two cheap steps rather than one expensive one. `search_repo_classes` and `describe_repo_class` cover the catalog of what can be deployed and what each version declares. `list_resource_definitions` is the vocabulary of dependency roles, and `find_resource_candidates` answers "what is already deployed here that could satisfy this role" -- the environment-scoped half deliberately left out of `find_resource_providers` in `5a7eb51`, now settled by making `environment` required rather than optional, so the null case that blocked it cannot arise. `compare_environments` exposes the diff the environment-compare page renders.
- feat: MCP `resources` and `prompts`, the other two halves of the protocol. Four resources under `neuronsphere://` address the same reads by URI -- `environments`, `resource-definitions`, and templated `environment/{environment}/bom` and `environment/{environment}/instance/{instance_name}/config` -- and are wrapped in the same `@read_tool` decorator, so a resource read is authorized and audited exactly like the tool call it delegates to. Four prompts (`deployment_overview`, `dependency_impact`, `find_provider_for_role`, `environment_drift`) encode the call *orders* the tools are meant to be used in: summary before full, edges before classification, catalog before producers.
- feat: `test/12_mcp.robot` and `test/resources/MCPSeed.py`, the first non-browser acceptance suite in the repo. It speaks JSON-RPC to `/mcp/` over `urllib` -- no new pip dependency -- covering the bearer challenge, the initialize handshake, every advertised tool, resource, and prompt, and the tool calls against the seeded BOM. It is also the acceptance check on the ASGI entry point: if the app ever falls back to WSGI the endpoint disappears and the whole suite fails.
- feat: `config.createLocalMcpKey` mints a fixed MCP bearer key from the migrate initContainer, mirroring the `createLocalSuperuser` branch beside it. The protocol suite has no browser to log in with, and `create_mcp_api_key` prints its key exactly once, so the key is supplied (`--key`, new) rather than generated and read back by the test from the same instance configuration that set it -- one declaration, no stdout parsing, no `docker exec`. Only the hash is stored either way, the plaintext is never echoed into deploy logs, and the flag is absent from the cloud defaults.

### Changed

- fix: a cloud deploy could not boot. Cloud sets `mcpEnabled: "true"` and `mcpApiKeysEnabled: "false"`, and with `DEBUG` false `build_auth_provider()` found zero verifiers and raised -- from `asgi.py`, at *import*, so the ASGI process died on start rather than degrading. API keys were correctly off (they are a local/test credential) but nothing had replaced them yet. `MCP_OKTA_ENABLED` now follows the same `config.oktaAuth` switch as the rest of Okta, so the cloud configuration has a credential and starts. An incomplete Okta configuration still refuses to start, and says which setting is missing instead of surfacing a bare `ValueError` from inside FastMCP; quietly falling back to the weaker credential would turn a misconfiguration into a less protected server.
- refactor: `_get_resource_url` is overridden on both composed providers so the resource URL is the public one, not the inner mount path. The MCP app is served internally at `/` and mounted at `/mcp`, so FastMCP's default composition advertises `<origin>/mcp/` -- a trailing slash the endpoint does not have, and worse, a metadata path the 401 challenge and the metadata route would compute *differently*, leaving discovery pointing at a 404.
- feat: `MCP_DOWNSTREAM_TOKEN_MODE` makes explicit what was hard-coded. `passthrough` (the default, and the existing behaviour) forwards an Okta caller's own token so hmd-ms-deployment applies its RBAC to the user; `service` forces every call onto the service account. Note the service account has no working credentials in cloud today -- `SERVICE_CLIENT_ID`/`SERVICE_CLIENT_SECRET` are read by `AuthTokenManager` but set by no chart template, ExternalSecret, or cdktf stack -- so the server now logs loudly at boot if `service` mode is selected without them, rather than sending unauthenticated requests downstream.
- refactor: `@read_tool` accepts a tuple of `environment_arg`s and authorizes every one of them, first failure wins. `compare_environments` needs two, and doing that check in the tool body is exactly what the GUI's own `environment_compare` does -- inline `UserEnvironmentPermission.user_can_view` calls that miss the superuser short-circuit in `services/authz.py`. Keeping it in the decorator keeps authorization structural.
- refactor: the tool registry generalized to a capability registry. `register_resource_modules` / `register_prompt_modules` join `register_tool_modules` behind one `_register_modules`, driven by new `MCP_RESOURCE_MODULES` / `MCP_PROMPT_MODULES` settings; `/health/` now reports resources and prompts as their own counts, so a capability that failed to register cannot hide inside the tool count.
- refactor: `filter_resource_definitions` extracted from `resource_definition_list` into `services/resource_query.py`, and the new `services/config_projection.py` holds the path/keys-only shaping. Both keep the rule from `26708c3` -- the MCP surface reimplements no query or shaping logic the GUI already has.
- fix: `MCP_ALLOWED_ORIGINS` no longer hardcodes `https://`. bender reaches the local deploy over plain HTTP, so an https origin was one that no client would ever send; the scheme now follows `config.localHttp`, from the same `alb.hostname` the rest of the block derives from.

### Tests

- test: `test_view_authz.py`, 13 tests covering every view that takes an environment from the request: an ungranted user is refused, a granted user is not, a superuser is not, and the refusal lands *before* any backend call (asserted against a fake client that records what it was asked for). The denial shape is asserted too -- the JSON endpoint refuses in JSON, and the HTMX partials refuse with a fragment carrying no `<html>` or `<body>`. Run against the pre-fix code, 6 of the 13 fail; the 7 that pass either way are the ones covering behavior that was already correct, which is the evidence for the correction noted above.
- test: 46 more tests (348 -> 394), in a new `test_mcp_okta_auth.py` plus an end-to-end `TestOktaTransport`. Tokens are minted with FastMCP's own `RSAKeyPair` and verified against a static public key, so nothing touches a JWKS endpoint. The mapping is covered in both directions -- `uid` wins over an email naming a *different* user, and an Okta user id in `sub` is never matched against `User.email` -- and the composition matrix pins the shape the routing depends on: Okta must be `MultiAuth`'s server, not a verifier. Two assertions pin what would otherwise be guesswork about FastMCP's URL composition: the metadata route is at `/.well-known/oauth-protected-resource/mcp` with no trailing slash, and the 401 challenge's `resource_metadata=` is the same absolute URL, so discovery cannot point at a document that is not there.
- test: `ns_auth_mode` is asserted present on *every* token the Okta verifier returns. `resolve_principal` defaults a missing mode to `apikey`, so forgetting it on one branch would silently route an Okta caller's downstream request as the service account -- a failure that authenticates fine and is invisible until someone reads an audit row.
- test: the helm render covers that cloud enables the Okta path while keeping API keys off (the pairing that makes it bootable), that the local render leaves Okta off and keeps its bender key, and that `MCP_BASE_URL` follows the deploy scheme the way `MCP_ALLOWED_ORIGINS` already does.
- test: 58 more unit tests (290 -> 348). Every new tool is held to a call budget the way `describe_environment` already was: `get_instance_configuration` must cost one `get_deployment_config` and zero classification calls, `describe_repo_class` must use the paged `find_repo_class_versions_page` and never the unpaged variant that resolves dependencies per version, and `compare_environments` must read no BOM at all.
- test: the structural authorization invariant in `test_mcp_registry` now matches any parameter named `environment` *or* ending in `_environment`, and covers resources as well as tools. Matching only the bare name would have let `compare_environments` past unlooked-at -- which is the exact class of gap the test exists to close.
- test: `test_mcp_server` drives `resources/list`, `resources/templates/list`, `resources/read`, `prompts/list` and `prompts/get` over the real ASGI app, asserts a resource read is audited like a tool call, and proves a caller permitted on the source environment is still refused on an unpermitted target.
- test: `test_helm_render` covers the `createLocalMcpKey` branch (idempotent, non-fatal, key passed by env rather than argv), that the cloud render leaves the migrate initContainer alone, and that the allowed-origin scheme follows the deploy.

## 2026-09-01

### Fixed

- fix: build `linux/arm64` images alongside `linux/amd64` by dropping the `docker.build.platforms` pin. That key only ever opts *out* of arm64 -- `ImageBuildConfig` already defaults to `["linux/amd64", "linux/arm64"]` -- so the pin, copied in wholesale with the initial Django scaffolding (`a13433d`), silently left arm64 users with no image. Nothing here required amd64: both `python:3.11-slim` stages are multi-arch upstream, every compiled wheel (`psycopg2-binary`, `cryptography`, `uvloop`/`httptools`) ships `manylinux aarch64` builds, and the builder stage carries `gcc`/`libpq-dev` for anything that must compile from source. `publish_image` now pushes both arch tags plus a real manifest list for `:<version>` and `:latest`, and the Helm chart pins no architecture (only `kubernetes.io/os: linux`), so the kubelet selects the matching arch.

## 2026-08-31

### Fixed

- fix: `k8sDbSecretName` now sanitizes the db-credentials fallback name, so a `db_name` containing an underscore no longer renders an ExternalSecret the API server rejects. The local BOM names the GUI's database `deployment_gui`, which produced `...-hmdtr1-deployment_gui` for both the `ExternalSecret` and every `secretKeyRef` in the Deployment; Kubernetes requires an RFC 1123 subdomain, so the release failed validation and was rolled back by `--atomic` — taking the rest of the deployment DAG with it, since the runner aborts on the first failed node. Mirrors the fix already carried by `hmd-inf-hive-metastore`: `| replace "_" "-" | lower`, applied only to the Kubernetes object name. `awsDbSecretName` keeps its raw underscores, so the Secrets Manager key is unchanged, and the transformation is a no-op for names that were already valid — cloud behavior does not change.

### Added

- feat: four more read-only MCP tools, taking the surface from one tool to five. `describe_environment` answers "what's deployed here" — `detail="summary"` returns counts by status and repo class plus the values available to filter on, `detail="full"` the filtered, sorted, paginated instance list. `describe_instance` returns one instance's metadata, the full merged effective configuration `hmd deploy` would use, and its dependency wiring with each role tagged by kind. `get_instance_dependencies` returns an instance's edges in either direction; the reverse direction is new surface, since the GUI only exposes it visually through the DAG. `find_resource_providers` fuses what `resource_definition_detail` and `api_repo_class_version_resources` show — the definition, its isa ancestry, the effective output schema, and the producing repo class versions — into the single question "what could satisfy this dependency role".
- feat: `clamp_limit` in `ns_mcp/tooling.py` finally reads `MCP_DEFAULT_PAGE_SIZE`/`MCP_MAX_PAGE_SIZE`, which were defined in Phase 1 and unused. An oversized `limit` is clamped rather than rejected: a truncated answer is more useful to a model than an error.

### Changed

- refactor: every tool is a thin adapter over the `deployments/services/` functions extracted in `26708c3`, which the GUI views already call — `summarize_bom`, `bom_facets`, `filter_bom`, `sort_bom`, `build_pagination`, `reverse_dependency_index`, `build_instance_detail_sections`, `resolve_resource_definition`. No query or shaping logic is reimplemented for MCP, so the two surfaces cannot drift.
- refactor: `find_resource_providers` deliberately takes no `environment` and declares no `environment_arg`. A resource definition and its producers are platform-wide facts and none of its four service calls are environment-scoped; an optional environment argument would instead reach `assert_environment_access` with `None`. Listing the instances currently *providing* a resource in one environment is left as separate follow-on work.
- refactor: the server `INSTRUCTIONS` now steer a caller through the surface — summary before full, `get_instance_dependencies` rather than `describe_instance` when walking many instances.

### Tests

- test: `test_mcp_tools.py` drives the tool bodies directly against a `FakeClient` that records every call it receives, so each tool is held to a call budget as well as an output shape. The headline assertion is that `describe_environment` costs exactly one `get_deployment_bom` and **zero** `find_repo_class_versions`/`suggest_resource_dependencies` at either detail level — the regression guard for the DAG gateway timeouts fixed in `e4de1e1`. `describe_instance` is asserted to classify exactly one `(repo_class, version)` pair, which is the one place that cost is legitimate.
- test: `test_mcp_registry.py` now drives `register_tool_modules` over `settings.MCP_TOOL_MODULES` instead of importing one module by name. The structural invariant — a tool taking an `environment` must declare it to `@read_tool` — was previously only applied to whatever that one import pulled in, so a new module could have skipped its permission check without being looked at.
- test: `test_mcp_server.py` covers the decorator's authorization path end to end for the first time: until `describe_environment` existed no tool took an environment, so nothing exercised it over the real transport. A caller with no grants is refused before any request reaches `hmd-ms-deployment`, and the refusal is still audited with `success=False`.

## 2026-08-28

### Added

- feat: a read-only Model Context Protocol (MCP) server at `/mcp`, so AI agents can query NeuronSphere deployment state. Built on `fastmcp` (Apache-2.0) and mounted beside the Django app by a new ASGI entry point (`deployment_gui/asgi.py`) rather than as a Django view, because it is a complete ASGI application with its own transport and authentication. Shape follows `HMD_MS_BASE_NERD001` (single `/mcp` endpoint over Streamable HTTP, bearer auth) so this server and the future `hmd-ms-base` transport are the same protocol surface. This first phase ships one tool, `list_environments`; the rest of the surface follows.
- feat: `MCPApiKey` — a bearer credential for the MCP server bound to a Django user, for local development, bender, and CI where no Okta token is available. Only the SHA-256 hash is stored; the plaintext is shown once by the new `create_mcp_api_key` management command. Okta JWT verification is deliberately deferred to a later phase.
- feat: every MCP tool goes through a single `@read_tool` decorator that resolves the caller, authorizes the environment against `UserEnvironmentPermission`, hops to a worker thread for all Django and HTTP work, and writes an `AuditLog` row. Authorization is opt-out rather than opt-in: a tool declares which parameter names an environment and the decorator performs the check, so the surface cannot inherit the pattern seen in several GUI endpoints that accept an arbitrary `?environment=` behind only `@login_required`.
- feat: `/health/` now reports whether the MCP server initialised and which tools it registered, giving probes and acceptance tests an unauthenticated way to confirm `/mcp` came up (the endpoint itself requires a token).

### Changed

- refactor: the container now serves `deployment_gui.asgi:application` through gunicorn's `uvicorn_worker.UvicornWorker` instead of `deployment_gui.wsgi:application` with sync workers. Django 5 runs the existing sync views and middleware unchanged under ASGI. `wsgi.py` is retained: setting `GUNICORN_WORKER_CLASS=sync` and pointing the CMD back at it restores the previous serving path exactly, and `MCP_ENABLED=false` serves Django alone.

### Fixed

- fix: `record_audit` no longer raises on a caller that omits `correlation_id` or `target`. Both are non-null `CharField`s, so passing `None` produced an `IntegrityError` instead of an audit row; they are now coerced to `""` and `"N/A"`. Not previously reachable — the view decorator always supplied both.
- fix: absorbed three schema-drift operations that were pending before this work (an index rename and two `AutoField` to `BigAutoField` changes), split into their own migration so they are reviewable separately from the MCP one.

### Tests

- test: added `tests/conftest.py` and a `deployment_gui.settings.test` module so tests that need the ORM run against an in-memory SQLite database. Most of the suite remains deliberately Django-free; the MCP tests are not, because model-backed authentication and per-environment authorization are the point. Isolation is a flush rather than a wrapping transaction, since the MCP layer does its database work in a worker thread that an open transaction would deadlock against.
- test: `test_mcp_server.py` drives the real ASGI application over MCP's JSON-RPC — the regression test for the WSGI-to-ASGI switch. It asserts Django is still served, that `/mcp` challenges unauthenticated and invalid tokens with `WWW-Authenticate`, that tools advertise descriptions, that the injected context does not leak into the input schema, that `list_environments` returns only the caller's grants, and that each call is audited against the calling user.
- test: `test_mcp_registry.py` asserts the structural invariant that any tool accepting an `environment` argument declares it to `@read_tool`, so a future tool cannot silently skip its permission check.
- test: added `test_mcp_api_key.py` covering key generation, hash-only storage, and that unknown, revoked, expired, and malformed keys are all indistinguishable to the caller.
- test: `test_authz_service.py` and `test_audit_service.py` now run against the real models instead of stubs.

## 2026-07-23

### Added

- feat: the ChangeSet item "Edit dependencies" picker can now remove a wired dependency. Each non-required role gets a "Remove" toggle (with "Undo") that disables the role's inputs — including HTMX-injected BOM candidates — via a `disabled` `<fieldset>`, so no `dep_<role>` field is submitted and the dependency is dropped on save. Previously BOM-sourced and "stale" (not-declared-by-version) dependencies were held in always-submitted hidden inputs with no way to detach them. Required dependencies intentionally offer no Remove control, and `changeset_set_item_deps` now guards the save path (`_preserve_required_deps`): if a required role would end up empty it is restored from the item's prior wiring, so a required dependency cannot be removed even via a crafted POST (re-wiring it to a different target still works).

### Fixed

- fix: the ChangeSet draft header now refreshes when items are added or removed. Adding a RepoInstance previously left the "Apply to DeploymentSet" button, the "Review" link, and the "Changes (N)" count stale until a full page reload, because the add/remove HTMX forms only swap `#changeset-items` while those controls live in the page header (gated on `draft.content`) outside that target. `changeset_add_item` and `changeset_remove_item` now return `changeset_items_response.html`, which re-emits the header actions (`#cs-header-actions`) and change count (`#cs-change-count`) as `hx-swap-oob` fragments so they update in place. This also fixes the inverse case where removing the last item did not hide the Apply/Review controls.

### Tests

- test: added regression coverage in `03_changeset.robot` asserting the Apply button, Review link, and change count appear on add and disappear on removing the last item without a page reload; removed the `Reload` workaround from "Review Button Appears With Items".
- test: added unit coverage for dependency removal — `test_set_item_deps.py` (`_preserve_required_deps`: optional roles drop, required roles restore when cleared, re-wiring preserved) and `test_dependency_picker_template.py` (Remove/Undo control rendered for optional/stale roles, never for required); plus a `03_changeset.robot` smoke test that the Edit-dependencies panel opens and the picker partial loads.

## 2026-07-21

### Added

- feat: Add a repo class version detail page (`repo-classes/<repo_class_name>/versions/<version>/`) showing discovery metadata, default configuration, and role dependencies for a single repo class version, linked from the existing repo class detail page.

## 2026-07-16

### Fixed

- fix: the environment BOM DAG view (`bom_dag_data`) no longer recomputes its Cytoscape node/edge JSON from scratch on every tab load. The assembled `{nodes, edges}` payload is now cached under `bom_dag:<environment>` with the same TTL as the BOM cache and invalidated alongside it (`invalidate_bom_cache`) on ChangeSet apply -- closing off the repeated per-unique-(repo_class, version) classification round-trips that, combined with an O(N²) backend traversal in `hmd-ms-deployment`, were causing the DAG view to time out with a 504 on larger environments.
- fix: `_classify_dependency_roles`'s `suggest_resource_dependencies` call had its arguments swapped -- it passed `repo_class_name` where the client expects `environment_type` as the first positional argument, so every resource-dependency-role classification call silently failed environment resolution upstream and was swallowed by a bare `except Exception`, wasting an HTTP round-trip on every unique repo-class/version pair without ever producing a correct "resource"-kind edge. `environment` is now threaded through and the call fixed on the DAG view and instance detail page (both have a real environment in scope); the ChangeSet draft dependency picker -- which has no single environment to resolve against, since drafts are portable across DeploymentSets -- now skips the call outright instead of issuing one guaranteed to fail.
- fix: aligned the GUI's ALB ingress idle timeout (`idle_timeout.timeout_seconds=120`) with gunicorn's own 120s worker timeout. The ALB previously inherited AWS's 60s default, tighter than gunicorn's, so the load balancer could 504 a request the Django backend would have finished within its own budget.

### Tests

- test: extended `test_classify_dependency_roles.py`, `test_bom_dag_elements.py`, `test_instance_detail_sections.py`, and `test_role_picker_context.py` to cover the `environment` threading added alongside the fix above -- the call fires with the right argument when `environment` is provided, and is skipped entirely when it's absent.
- test: extended `test_api_client.py::TestInvalidateBomCache` to assert `invalidate_bom_cache` also drops the new `bom_dag:<environment>` cache key.
- test: new `test_bom_dag_data_view.py` covers `bom_dag_data`'s response caching -- the first call populates the cache and calls the backend client, a second call is served from cache without calling the client again.

## 2026-07-15

### Added

- feat: Switch the `eks-alb` dependency to the local ingress-controller Resource and expose the GUI through Traefik. The manifest now declares authoritative SPEC0008 `resource` blocks for the `eks-alb` (→ `kubernetes.neuronsphere.io/ingress-controller`), `eks-cluster`, `compute`, and `db-credentials` roles (keeping `repo_class_name` as a suggestion). The chart's Ingress is value-driven: a new `ns.ingressClass` helper reads the bound ingress-controller Resource's `ingress_class` (the local Traefik's `traefik`, else the cloud `alb` default), and the AWS ALB-controller annotations render only when the class is `alb` — cloud output is unchanged. `config_local.json` enables the Ingress, drops the `NodePort` (`ClusterIP` service), and reaches the app through Traefik at the node hostname.
- feat: Drop ephemeral container IPs from `config_local.json`. `config.deploymentApiUrl` uses the stable `http://hmd_proxy/hmd_ms_deployment` (a CoreDNS record added by `hmd-cli-neuronsphere` makes `hmd_proxy` pod-resolvable) and the dead `_local.db_host_ip` block is removed (the DB host is already the stable name `hmd_db`).

- feat: Full `hmd deploy --local` (cdktf + helm) now deploys the GUI to local k3s end-to-end (not just the helm step). Added a Floci-safe no-op `src/local/cdktf/cdktf_local.py` overlay (mirroring hmd-inf-ext-secrets) so the cloud-only Okta/Secrets-Manager stack is skipped locally; `hmd cdktf` prefers `src/local/cdktf` when `environment=="local"`. `config_local.json` points the `kubernetes-cluster` resource endpoint at the host-reachable k3s API (`localhost:6500`).

- feat: Resource-ify the helm chart + `meta-data/config_local.json` so the GUI deploys to local k3s via `hmd helm deploy --local` and passes `hmd bender` (9/9). A new `ns.resourceOutput` helper (mirroring `hmd_cli_helm._resource_output`) sources the DB name and the db-credentials ExternalSecret's secret key from the bound `postgres` Resource's `hmd_resources` output (NERD0006), falling back to the existing cloud db-credentials chain when absent. `DEPLOYMENT_API_URL`, `DJANGO_ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`, the ExternalSecret ClusterSecretStore name, `NodePort`, gunicorn worker cap, a local dev superuser, and plain-http/username-password auth are all config-gated so cloud deploys are unchanged.

### Changed

- fix: `production.py` HTTPS-only enforcement (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`) and `SOCIALACCOUNT_ONLY` are now env-overridable (defaults unchanged) so a local plain-http deploy can serve the username/password login form for acceptance tests.

- test: `DeploymentSeed.py` targets the current proxy hostname (`hmd_proxy`, overridable via `DEPLOYMENT_API_URL`) and probes readiness on `/apiop/list_resource_definitions` instead of the non-existent `/api/health`; the login keyword scopes its submit to the local login form (the page also renders an Okta submit).

## 2026-07-14

### Added

- feat: Read-only GUI views for the resource model (NERD0004/0006). A new **Resources** section in the sidebar browses **Resource Definitions** (namespace filter + search + pagination) and, per definition, shows the `isa` ancestry chain, effective (merged) output schema, and producing repo class versions. A **Resources** page finds concrete resources by a single tag or an AND selector (`key=value,key=value`). Repo class version rows gain a **Resource Dependencies** column (environment-resolved via `suggest_resource_dependencies`), and instance detail pages lazy-load the resources produced by an instance's latest deployment. New `DeploymentAPIClient` methods wrap the `list/get/ancestry/effective-schema/producers/deployment-resources/find-by-tag/find-by-selector/suggest` `/apiop/` endpoints (stable definition metadata cached, live state uncached).

- feat: The ChangeSet dependency picker now resolves **resource-based dependency roles**. Roles a repo class version declares against a resource type (rather than a concrete repo class) are discovered via `suggest_resource_dependencies` and offered from the same two existing sources — the current draft and an environment BOM — with candidates being the instances that satisfy the required resource type/tags. Class-based roles are unchanged.

## 2026-07-02

### Fixed

- fix: ChangeSet instances are now posted to the deployment service in dependency order. A chain set built with multiple new instances that depend on one another was posted in insertion order, so a dependent instance could be listed before the instance it depends on. `ChangeSetDraft.sanitized_content` now topologically sorts items (prerequisites first, dependents last) via `topological_sort_changeset`, covering the save, validate, and BOM-impact paths. The sort is stable (independent items keep their original order) and cycle-safe (leaves circular-dependency reporting to the backend validate step).

- fix: The "From BOM" dependency picker on the Edit Change Set page never returned any candidate instances. The picker asked for a DeploymentSet name and the backend resolved that set to its environments before querying the BOM, but the BOM API is keyed on an environment (dev/test/prod). Typing an environment like `dev` matched no DeploymentSet, so the resolver returned nothing and zero candidates were shown. The picker is now an environment dropdown (populated via `get_user_environments`) and `api_dep_candidates` queries `get_deployment_bom(environment)` directly.

## 2026-06-30

### Fixed

- fix: Every HTMX refresh of the Environment BOM table (pagination Next/Previous, column sort, Search, and Refresh) was silently failing with a 403 "Environment not specified". The `bom_table` partial view delegated to `bom_list` by passing `environment` as a positional argument, but `bom_list` is wrapped by `@require_environment_access`, whose decorator only resolves the environment from kwargs/POST/GET — so the positional value was invisible and the decorator denied the request. The global `htmx:responseError` handler swallows 403s (console-only), so sort/search/refresh appeared to do nothing while the non-advancing page number made pagination the visible symptom. Fixed by passing `environment` as a keyword argument (`bom_list(request, environment=environment)`). The initial full-page load was unaffected because Django passes the captured path param as a kwarg directly to the decorated view.

## 2026-06-29

### Added

- feat: Loading indicators for slow non-HTMX actions. Applying a ChangeSet to a DeploymentSet is a plain synchronous form POST that triggers real deployments (10–30s) and ended in a full-page redirect, so the only feedback was the browser tab spinner; the Apply modal now shows an in-modal spinner overlay ("Applying ChangeSet — triggering deployments…"), swaps the Apply button to a disabled "Applying…" spinner, and disables Cancel/input to prevent double-submit. A global `beforeunload` handler now shows the existing brand `#loading-bar` on any full-page navigation, so other plain form posts and GET reloads (Reject, Clone, Environment Compare, Deployment List filter/Load More, Repo Class search) get feedback too. The raw-`fetch` DAG and Timeline views, which bypass HTMX, now render a spinner in their container while loading. HTMX-driven actions already triggered the loading bar and were left unchanged.

## 2026-06-26

### Fixed

- fix: Editing a ChangeSet instance's dependencies no longer shows "Could not find that repo class / version" and hides the current wiring. `_build_role_picker_context` derived editable rows solely from the resolved `repo_class_version`'s declared roles, so when `find_repo_class_versions` (uncached) returned no match the dependency picker rendered only an error banner — and because no `dep_<role>` inputs were emitted, the instance's existing dependencies were dropped on save. Existing dependencies whose role isn't declared by the resolved version (including the version-not-found case) are now folded into the picker as preserved, editable "kept" rows so current wiring is always prepopulated and survives a save. The `no_version` message is now a non-blocking info banner instead of an early return.

### Changed

- feat: Environment BOMs are cached longer and invalidated on ChangeSet deployment instead of expiring on the 30s general API TTL. Added a configurable `DEPLOYMENT_BOM_CACHE_TTL` (default 1 hour) used by `get_deployment_bom`, a `cache_ttl` override on `_make_request`, and explicit `invalidate_bom_cache()` calls for the target DeploymentSet's environments after a successful `apply_changeset`. The deployment-set→environments lookup was factored into `_environments_for_deployment_set` and reused by `api_dep_candidates`. Note: `LocMemCache` is per-process, so the finite TTL also bounds cross-worker staleness.

## 2026-06-25

### Fixed

- fix: Environment BOM RepoInstance detail panel no longer opens blank. `showInstanceDetail()` built the HTMX request URL with a no-op `.replace()` and concatenated the instance name without URL-encoding, so any instance name containing a space or special character produced a malformed URL that 404'd; htmx silently skips the swap on failure, leaving the panel empty. The URL is now reversed from the real `deployments:instance_detail` route with `encodeURIComponent`, a "Loading…" state is shown while fetching, and a visible error message replaces the silent blank when the request fails. Also imported the missing `HttpResponseForbidden` in `decorators.py` to close a latent `NameError`.
- fix: Clicking "View" on a BOM row no longer refreshes the page with "Provide a name for the new ChangeSet." The per-row View button had no `type` attribute and sits inside the multi-select Create ChangeSet `<form>`, so it defaulted to `type="submit"` and posted the empty-named form right after opening the detail panel. Added `type="button"` so it only opens the panel.
- fix: The instance detail panel's Deployment History section now renders. The service returns history wrapped as `{"repo_instance": …, "history": […]}`, but the view passed the whole dict to the template, which iterated its keys instead of the deployment list; the view now unwraps the `history` list. The templates also referenced non-existent `version`/`deployed_at` fields — they now show each deployment's `deployment_id`, `status`, and `start` timestamp, which are the fields a `RepoInstanceDeployment` actually has.

## 2026-06-16

### Fixed

- fix: ChangeSet item editor now supports dependency roles wired to multiple instances. Previously the picker collapsed list-valued `selected_deps` to a single name and the form parser only kept one value per `dep_<role>` key, so adding (or prefilling) an instance whose `dependencies` map had `role -> [a, b, ...]` silently dropped every dep except the first. The dependency picker now renders a checkbox list per role, `request.POST.getlist` collects every checked value, and `compute_dependency_diff` normalizes single-string and list forms so the BOM diff doesn't churn on equivalent shapes. Storage mirrors `deploy_bom_creator`'s convention — one selection serializes as a string, two or more as a list.

## 2026-06-09

### Fixed

- fix: Deployment detail Timeline tab no longer shows "No timeline data yet — instances have not started deploying." for completed deployments whose RIDs lack a per-instance `start` timestamp. The empty-state copy now distinguishes "no instances tracked" (no groups at all) from "tracked but untimestamped" (groups present but no items); the upstream microservice provides `deploy_time` as a `start` fallback so the Gantt renders rows for every tracked instance.
- fix: Deployment Logs page pod-name dropdown was rendering blank options because the templates read `pod.name` while the microservice payload uses `pod.pod_name`. Aligned `deployment_logs.html` and the `deployment_status.html` partial with the wire shape, and reshaped the `deployment_logs` view to extract the selected pod's body into `logs.content` so the log viewer actually renders content after a pod is picked.

## 2026-06-05

### Fixed

- fix: render environments for Okta-authenticated platform admins by syncing Django `is_superuser`/`is_staff` from a new `OKTA_SUPERUSER_GROUPS` setting. Previously, allauth created accounts with `is_superuser=False`, so `get_user_environments` took the permission-only branch and never called `hmd-ms-deployment` — producing a silent empty list for anyone whose Okta groups did not appear in `OKTA_GROUP_MAPPING`. Locally-created superusers (no `SocialAccount`) are untouched.
- fix: align `src/python/setup.py` with `src/docker/requirements.txt` by adding `requests`, `PyJWT`, and `cryptography` so the build venv mirrors the production runtime (django-allauth's openid_connect provider needs all three at import time).

### Changed

- feat: log a `WARNING` from `environment_service.get_user_environments` when a non-superuser has zero permissions, so an empty sidebar/dashboard is self-diagnosing in production logs instead of silent.
- feat: render a helpful empty-state ("ask a platform admin to add you to the appropriate Okta group") in the sidebar, dashboard env cards, and `/environments/` page when no environments are visible.

## 2026-06-02

### Fixed

- fix: set `SOCIALACCOUNT_STORE_TOKENS = True` so allauth persists the Okta access token on `SocialToken`; without it, `get_api_client_for_request` could never find a user token, fell back to the (often unconfigured) service-account token, and sent requests to hmd-ms-deployment with no `Authorization` header — API Gateway then returned `{"message":"Unauthorized"}` before the OPA authorizer Lambda was ever invoked (hence no authorizer logs).

## 2026-05-29

### Fixed

- fix: forward the logged-in user's Okta access token (from allauth `SocialToken`) to the deployment service via a new `get_api_client_for_request(request)` helper; views and the sidebar context processor now use it instead of the service-account-only `get_api_client()`. Resolves `Unauthorized` responses on RepoClass / Environments / ChangeSet pages.
- fix: derive `DEPLOYMENT_API_URL` from the `deployment-service` dependency and cluster env vars in the helm configmap, replacing the placeholder `http://hmd-ms-deployment:8000` that caused `[Errno -2] Name or service not known` on the RepoClass/Environments/ChangeSet pages (hmd-ms-deployment is a Lambda behind API Gateway, not a K8s service)

## 2026-05-19

### Fixed

- fix: ALB target-group health checks failing Django `ALLOWED_HOSTS` validation — inject pod IP via downward API and append to `ALLOWED_HOSTS`, point ALB health check at `/health/`, and exempt `/health/` from `SECURE_SSL_REDIRECT`

## 2026-04-28

### Added

- feat: deployment timeline (Gantt) visualization on the deployment detail page with Status/Timeline tab toggle, manual refresh, and per-instance status colors
- feat: environment comparison view with side-by-side diff (only-in-source / only-in-target / modified) and "Generate ChangeSet from selected" entry into the existing promote-mapping flow
- feat: Compare Environments form on the environment list page; "Compare with…" link on the BOM toolbar that prefills the source env
- feat: `compute_environment_diff` helper in `bom_diff.py`
- feat: `get_deployment_timeline` API client method (backed by new `/apiop/get_deployment_timeline/<csd_id>` op in hmd-ms-deployment)

### Removed

- refactor: drop unused `get_change_set_deployment` API client stub (the matching backend op never existed)

## 2026-02-20

### Added

- feat: telemetry profile in nsplugin.json for telemetry-debug service seeding
