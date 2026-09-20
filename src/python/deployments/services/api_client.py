"""HTTP client for hmd-ms-deployment service."""
import json
import logging
from base64 import b64encode
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from django.conf import settings
from django.core.cache import cache


def _encode_collection(value: Any) -> str:
    """Encode a 'collection' field for ms-base's wire format.

    hmd-meta-types' Entity.serialize() base64-encodes JSON for any field whose
    schema type is 'collection' or 'mapping'. ms-base's Pydantic model then
    validates the field as a plain string. Sending the raw list/dict is rejected
    with a misleading 'Input should be a valid string' error."""
    return b64encode(json.dumps(value).encode("latin-1")).decode("latin-1")


logger = logging.getLogger(__name__)


@dataclass
class APIResponse:
    """Wrapper for API responses."""

    success: bool
    data: Any
    error: Optional[str] = None
    status_code: int = 200


class DeploymentAPIClient:
    """HTTP client for hmd-ms-deployment service."""

    def __init__(self, auth_token: Optional[str] = None):
        """Initialize the API client.

        Args:
            auth_token: Optional Bearer token for authentication.
        """
        self.base_url = settings.DEPLOYMENT_API_URL.rstrip("/")
        self.timeout = settings.DEPLOYMENT_API_TIMEOUT
        self.cache_ttl = settings.DEPLOYMENT_API_CACHE_TTL
        self.bom_cache_ttl = settings.DEPLOYMENT_BOM_CACHE_TTL
        self.auth_token = auth_token

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        cache_key: Optional[str] = None,
        cache_ttl: Optional[int] = None,
    ) -> APIResponse:
        """Make HTTP request to deployment API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON body data
            cache_key: Optional cache key for cacheable requests
            cache_ttl: Optional TTL override for the cached response; falls back
                to ``self.cache_ttl`` when not supplied.

        Returns:
            APIResponse with success status and data or error
        """
        # Check cache for cacheable requests
        if cache_key:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return APIResponse(success=True, data=cached)

        url = f"{self.base_url}{endpoint}"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(
                    method=method,
                    url=url,
                    headers=self._get_headers(),
                    params=params,
                    json=json_data,
                )

                if response.status_code >= 400:
                    logger.error(
                        f"API error: {response.status_code} - {response.text}",
                        extra={"url": url, "method": method},
                    )
                    return APIResponse(
                        success=False,
                        data=None,
                        error=response.text,
                        status_code=response.status_code,
                    )

                data = response.json() if response.text else {}

                # Cache successful responses
                if cache_key:
                    cache.set(
                        cache_key,
                        data,
                        cache_ttl if cache_ttl is not None else self.cache_ttl,
                    )

                return APIResponse(
                    success=True, data=data, status_code=response.status_code
                )

        except httpx.TimeoutException:
            logger.error(f"Timeout calling {url}")
            return APIResponse(
                success=False,
                data=None,
                error="API request timed out",
                status_code=504,
            )
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            return APIResponse(
                success=False,
                data=None,
                error=str(e),
                status_code=503,
            )

    # ========== BOM Operations ==========

    def get_deployment_bom(self, environment_type: str) -> APIResponse:
        """Get Bill of Materials for an environment.

        GET /apiop/get_deployment_bom/<environment_type>

        Args:
            environment_type: Environment identifier (e.g., 'dev', 'test', 'prod')

        Returns:
            APIResponse with list of deployment objects
        """
        cache_key = f"bom:{environment_type}"
        return self._make_request(
            "GET",
            f"/apiop/get_deployment_bom/{environment_type}",
            cache_key=cache_key,
            cache_ttl=self.bom_cache_ttl,
        )

    def get_deployment_info(self, environment_type: str) -> APIResponse:
        """Get deployment diagram info for an environment.

        GET /apiop/get_deployment_info/<environment_type>

        Args:
            environment_type: Environment identifier

        Returns:
            APIResponse with PlantUML diagram data
        """
        return self._make_request(
            "GET",
            f"/apiop/get_deployment_info/{environment_type}",
        )

    def get_deployment_history(
        self,
        environment_type: str,
        instance_name: str,
    ) -> APIResponse:
        """Get deployment history for an instance.

        GET /apiop/get_deployment_history/<type>/<name>

        Args:
            environment_type: Environment identifier
            instance_name: Instance name

        Returns:
            APIResponse with deployment history
        """
        return self._make_request(
            "GET",
            f"/apiop/get_deployment_history/{environment_type}/{instance_name}",
        )

    def get_deployment_config(
        self,
        environment_type: str,
        instance_name: str,
    ) -> APIResponse:
        """Get configuration for a deployed instance.

        GET /apiop/get_deployment_config/<type>/<name>

        Args:
            environment_type: Environment identifier
            instance_name: Instance name

        Returns:
            APIResponse with instance configuration
        """
        return self._make_request(
            "GET",
            f"/apiop/get_deployment_config/{environment_type}/{instance_name}",
        )

    # ========== RepoClass Operations ==========

    def find_repo_class_versions(self, repo_class_name: str) -> APIResponse:
        """Find all versions for a repo class.

        POST /apiop/find_repo_class_versions/<repo_class_name>

        Args:
            repo_class_name: Name of the repo class

        Returns:
            APIResponse with list of RepoClassVersion objects
        """
        return self._make_request(
            "POST",
            f"/apiop/find_repo_class_versions/{repo_class_name}",
        )

    def find_repo_class_versions_page(
        self,
        repo_class_name: str,
        q: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> APIResponse:
        """Find a page of versions for a repo class (for the version picker).

        POST /apiop/find_repo_class_versions/<name>?limit=&offset=[&q=]&include_deps=false

        Passing pagination params triggers the microservice's envelope response
        (``{"items", "total", "limit", "offset"}``) and skips the per-version
        dependency resolution the picker doesn't need. Cached per
        (name, q, limit, offset) since the version picker re-fetches on every
        keystroke/page.

        Args:
            repo_class_name: Name of the repo class
            q: Optional case-insensitive version substring filter
            limit: Page size
            offset: Pagination offset

        Returns:
            APIResponse whose data is the ``{"items", "total", ...}`` envelope
        """
        params = {"limit": limit, "offset": offset, "include_deps": "false"}
        if q:
            params["q"] = q
        return self._make_request(
            "POST",
            f"/apiop/find_repo_class_versions/{repo_class_name}",
            params=params,
            cache_key=f"versions:{repo_class_name}:{q}:{limit}:{offset}",
        )

    def get_repo_class_version_detail(
        self, repo_class_name: str, version: str
    ) -> APIResponse:
        """Get full detail for one repo class version (discovery metadata,
        default configuration, and role dependencies).

        GET /apiop/get_repo_class_version_detail/<repo_class_name>/<version>

        Args:
            repo_class_name: Name of the repo class
            version: Version specifier

        Returns:
            APIResponse with the RepoClassVersion detail
        """
        return self._make_request(
            "GET",
            f"/apiop/get_repo_class_version_detail/{repo_class_name}/{version}",
        )

    def get_repo_class_instances(
        self,
        repo_class_name: str,
        environment_type: str,
    ) -> APIResponse:
        """Get instances of a repo class in an environment.

        GET /apiop/get_repo_class_instances/<name>/<type>

        Args:
            repo_class_name: Name of the repo class
            environment_type: Environment identifier

        Returns:
            APIResponse with list of instances
        """
        return self._make_request(
            "GET",
            f"/apiop/get_repo_class_instances/{repo_class_name}/{environment_type}",
        )

    # ========== ChangeSet Operations ==========

    def save_changeset(
        self,
        name: str,
        definition: List[Dict],
    ) -> APIResponse:
        """Upsert a ChangeSet entity by name.

        Search by name first; if an entity exists, include its ``identifier`` in
        the PUT body so ms-base's ``put_entity`` takes the update branch instead
        of colliding on the unique ``name`` (business_id). Without this, applying
        the same draft to a second deployment_set 500s on duplicate insert.

        - POST /api/hmd_lang_deployment.change_set with a filter body looks up
          the existing entity.
        - PUT /api/hmd_lang_deployment.change_set with the entity body upserts.
        """
        search = self._make_request(
            "POST",
            "/api/hmd_lang_deployment.change_set",
            json_data={"attribute": "name", "operator": "=", "value": name},
        )
        if not search.success:
            return search

        body: Dict[str, Any] = {
            "name": name,
            "definition": _encode_collection(definition),
        }
        results = search.data if isinstance(search.data, list) else []
        if results:
            existing_id = results[0].get("identifier")
            if existing_id:
                body["identifier"] = existing_id

        return self._make_request(
            "PUT",
            "/api/hmd_lang_deployment.change_set",
            json_data=body,
        )

    def validate_changeset(self, changeset_content: List[Dict]) -> APIResponse:
        """Validate a ChangeSet before applying.

        POST /apiop/validate_changeset

        Checks dependency resolution, version compatibility, and circular
        dependency detection.

        Args:
            changeset_content: List of ChangeSet item dicts

        Returns:
            APIResponse with validation result:
            {
                "valid": bool,
                "errors": [{"type": str, "instance": str, "message": str}],
                "warnings": [{"type": str, "instance": str, "message": str}]
            }
        """
        return self._make_request(
            "POST",
            "/apiop/validate_changeset",
            json_data={"changes": changeset_content},
        )

    # ========== Environment Comparison ==========

    def compare_environments(
        self,
        from_env: str,
        to_env: str,
    ) -> APIResponse:
        """Compare deployments between two environments.

        POST /apiop/compare_environments

        Args:
            from_env: Source environment
            to_env: Target environment

        Returns:
            APIResponse with comparison data
        """
        return self._make_request(
            "POST",
            "/apiop/compare_environments",
            json_data={
                "from_env": from_env,
                "to_env": to_env,
            },
        )

    # ========== Deployment Logs ==========

    # ========== Status Updates ==========

    def set_deployment_status(
        self,
        deployment_id: str,
        status: str,
    ) -> APIResponse:
        """Update deployment status.

        POST /apiop/set_deployment_status/<id>/<status>

        Args:
            deployment_id: Deployment identifier
            status: New status value

        Returns:
            APIResponse with update result
        """
        return self._make_request(
            "POST",
            f"/apiop/set_deployment_status/{deployment_id}/{status}",
        )

    # ========== Environment Listing ==========

    def list_environments(self) -> APIResponse:
        """List all environments from the deployment service.

        Uses POST /api/hmd_lang_deployment.environment (ms-base search)
        with a filter to find all environment entities.

        Returns:
            APIResponse with list of environment entity objects
        """
        return self._make_request(
            "POST",
            "/api/hmd_lang_deployment.environment",
            json_data={"attribute": "type", "operator": "!=", "value": "__none__"},
            cache_key="environments:all",
        )

    def invalidate_environment_cache(self) -> None:
        """Invalidate cached environment list."""
        cache.delete("environments:all")
        logger.debug("Invalidated environment cache")

    # ========== DeploymentSet Listing ==========

    def list_deployment_sets(self) -> APIResponse:
        """List all DeploymentSets from the deployment service.

        Uses POST /api/hmd_lang_deployment.deployment_set (ms-base search)
        with a no-op filter to return all DeploymentSet entities.
        """
        return self._make_request(
            "POST",
            "/api/hmd_lang_deployment.deployment_set",
            json_data={"attribute": "name", "operator": "!=", "value": "__none__"},
            cache_key="deployment_sets:all",
        )

    def invalidate_deployment_set_cache(self) -> None:
        """Invalidate cached deployment set list."""
        cache.delete("deployment_sets:all")
        logger.debug("Invalidated deployment set cache")

    # ========== RepoClass Listing ==========

    def list_repo_classes(self) -> APIResponse:
        """List all available repo classes.

        GET /apiop/list_repo_classes

        Returns:
            APIResponse with list of repo class objects
        """
        return self._make_request(
            "GET",
            "/apiop/list_repo_classes",
            cache_key="repo_classes:all",
        )

    def search_discovery(
        self,
        q: str = "",
        kind: str = "",
        repo_class_name: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> APIResponse:
        """Search every repo class's latest-version discovery metadata.

        GET /apiop/search_discovery?q=&kind=&repo_class_name=&limit=&offset=
        (hmd-ms-deployment NERD0013 SPEC0002)

        Only the filters that are set are sent, so the backend's "empty query
        returns the whole catalog with full capability lists" path is reachable.
        Cached per (q, kind, prefix, limit, offset): the capability search form
        re-fetches on every keystroke/page.

        Args:
            q: Free text; every token must hit the summary, a capability, or an
                entry point
            kind: Exact capability kind (endpoint/cli_command/function/class/
                operation)
            repo_class_name: Case-insensitive class-name prefix
            limit: Page size
            offset: Pagination offset

        Returns:
            APIResponse whose data is the ``{"items", "total", ...}`` envelope
        """
        params = {"limit": limit, "offset": offset}
        if q:
            params["q"] = q
        if kind:
            params["kind"] = kind
        if repo_class_name:
            params["repo_class_name"] = repo_class_name
        return self._make_request(
            "GET",
            "/apiop/search_discovery",
            params=params,
            cache_key=f"discovery:{q}:{kind}:{repo_class_name}:{limit}:{offset}",
        )

    # ========== ChangeSetDeployment Listing ==========

    # ========== Resource Operations ==========
    #
    # NERD0004/0006 resource model. Definition metadata (list/get/ancestry/
    # effective schema) is stable and cached with the default API TTL, mirroring
    # ``list_repo_classes``. Anything reflecting live environment state (producers,
    # deployed resources, dependency suggestions) is left uncached so changeset
    # authors always see current data.

    def list_resource_definitions(
        self, resource_namespace: Optional[str] = None
    ) -> APIResponse:
        """List Resource Definitions, optionally scoped to a namespace.

        GET /apiop/list_resource_definitions[?resource_namespace=<ns>]
        """
        params = None
        if resource_namespace:
            params = {"resource_namespace": resource_namespace}
        return self._make_request(
            "GET",
            "/apiop/list_resource_definitions",
            params=params,
            cache_key=f"resource_defs:{resource_namespace or 'all'}",
        )

    def get_resource_definition(self, rd_id: str) -> APIResponse:
        """Get a single Resource Definition by identifier.

        GET /apiop/get_resource_definition/<id>
        """
        return self._make_request(
            "GET",
            f"/apiop/get_resource_definition/{rd_id}",
            cache_key=f"resource_def:{rd_id}",
        )

    def get_resource_definition_ancestry(self, rd_id: str) -> APIResponse:
        """Get a definition's ``isa`` ancestry chain, root-first.

        GET /apiop/get_resource_definition_ancestry/<id>
        """
        return self._make_request(
            "GET",
            f"/apiop/get_resource_definition_ancestry/{rd_id}",
            cache_key=f"resource_def_ancestry:{rd_id}",
        )

    def get_effective_output_schema(self, rd_id: str) -> APIResponse:
        """Get a definition's effective (isa-merged) output JSON schema.

        GET /apiop/get_effective_output_schema/<id>
        """
        return self._make_request(
            "GET",
            f"/apiop/get_effective_output_schema/{rd_id}",
            cache_key=f"resource_def_schema:{rd_id}",
        )

    def get_producers(self, rd_id: str, include_subtypes: bool = False) -> APIResponse:
        """List RepoClassVersions that produce a Resource Definition.

        GET /apiop/get_producers/<id>[?include_subtypes=true]

        Not cached — the producer set changes as repo class versions are added.
        """
        params = None
        if include_subtypes:
            params = {"include_subtypes": "true"}
        return self._make_request(
            "GET",
            f"/apiop/get_producers/{rd_id}",
            params=params,
        )

    def get_deployment_resources(self, repo_instance_deployment_id: str) -> APIResponse:
        """List the resources recorded for a RepoInstanceDeployment.

        GET /apiop/get_deployment_resources/<id>

        Each entry carries ``resource_name``, ``resource_definition``, ``output``
        and ``tags``. Not cached — reflects live environment state.
        """
        return self._make_request(
            "GET",
            f"/apiop/get_deployment_resources/{repo_instance_deployment_id}",
        )

    def find_resources_by_tag(
        self, key: str, value: str, environment: Optional[str] = None
    ) -> APIResponse:
        """Find resources carrying a specific ``key=value`` tag.

        GET /apiop/find_resources_by_tag/<key>/<value>[?environment=<type>]

        Pass ``environment`` to scope results to resources deployed in that
        environment (the whole graph otherwise).
        """
        params = {"environment": environment} if environment else None
        return self._make_request(
            "GET",
            f"/apiop/find_resources_by_tag/{key}/{value}",
            params=params,
        )

    def find_resources_by_selector(
        self, tags: Dict[str, str], environment: Optional[str] = None
    ) -> APIResponse:
        """Find resources whose tags satisfy every ``key=value`` pair (AND).

        GET /apiop/find_resources_by_selector?tags=k=v,k=v[&environment=<type>]

        The backend parses a comma-joined ``key=value`` string from the ``tags``
        query parameter — so this is a GET with a query string, NOT a POST body,
        and nothing here is base64-encoded (``_encode_collection`` applies only to
        ms-base entity PUTs, never to ``/apiop/`` operations). Pass ``environment``
        to additionally scope results to that environment.
        """
        selector = ",".join(f"{k}={v}" for k, v in (tags or {}).items())
        params = {"tags": selector}
        if environment:
            params["environment"] = environment
        return self._make_request(
            "GET",
            "/apiop/find_resources_by_selector",
            params=params,
        )

    def list_resources(
        self, limit: int = 50, offset: int = 0, environment: Optional[str] = None
    ) -> APIResponse:
        """List deployed resources, paginated.

        GET /apiop/list_resources?limit=&offset=[&environment=<type>]

        Returns an ``{"items", "total", "limit", "offset"}`` envelope. Pass
        ``environment`` to scope to resources deployed in that environment (the whole
        graph otherwise). This is the unfiltered companion to
        ``find_resources_by_tag`` / ``find_resources_by_selector``.
        """
        params = {"limit": limit, "offset": offset}
        if environment:
            params["environment"] = environment
        return self._make_request(
            "GET",
            "/apiop/list_resources",
            params=params,
        )

    def suggest_resource_dependencies(
        self,
        environment_type: str,
        repo_class_version_id: Optional[str] = None,
        resource_namespace: Optional[str] = None,
        resource_definition_name: Optional[str] = None,
        version: Optional[str] = None,
        version_spec: Optional[str] = None,
        tags: Optional[str] = None,
    ) -> APIResponse:
        """Suggest RepoInstances that could satisfy a resource-type dependency.

        GET /apiop/suggest_resource_dependencies/<environment_type>

        Two query modes (mirroring the backend):
        - ``repo_class_version_id`` — returns a role-keyed dict
          ``{role: {resource_definition, version_spec, tag_selector, required,
          suggested_repo_class_name, candidates:[{name, identifier}]}}``.
        - ``resource_namespace`` + ``resource_definition_name`` + ``version``
          (+ optional ``version_spec``/``tags``) — returns
          ``{"candidates": [{name, identifier}]}``.

        Not cached — candidates depend on live environment state.
        """
        params: Dict[str, str] = {}
        if repo_class_version_id:
            params["repo_class_version_id"] = repo_class_version_id
        if resource_namespace:
            params["resource_namespace"] = resource_namespace
        if resource_definition_name:
            params["resource_definition_name"] = resource_definition_name
        if version:
            params["version"] = version
        if version_spec:
            params["version_spec"] = version_spec
        if tags:
            params["tags"] = tags
        return self._make_request(
            "GET",
            f"/apiop/suggest_resource_dependencies/{environment_type}",
            params=params or None,
        )

    # ========== Cache Management ==========

    def invalidate_bom_cache(self, environment_type: str) -> None:
        """Invalidate cached BOM and DAG-elements JSON for an environment.

        Args:
            environment_type: Environment identifier
        """
        cache.delete(f"bom:{environment_type}")
        cache.delete(f"bom_dag:{environment_type}")
        logger.debug(f"Invalidated BOM/DAG cache for {environment_type}")
