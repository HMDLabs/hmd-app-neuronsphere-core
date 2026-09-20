"""URL configuration for deployments app."""
from django.urls import path

from . import views

app_name = "deployments"

urlpatterns = [
    # Dashboard (landing page)
    path("", views.dashboard, name="dashboard"),
    path(
        "dashboard/env-status/",
        views.dashboard_env_status_partial,
        name="dashboard_env_status",
    ),
    # Environment List (moved from root)
    path("environments/", views.environment_list, name="environment_list"),
    path(
        "environments/compare/", views.environment_compare, name="environment_compare"
    ),
    path(
        "environments/compare/create-changeset/",
        views.environment_compare_create_changeset,
        name="environment_compare_create_changeset",
    ),
    # BOM Views
    path("bom/<str:environment>/", views.bom_list, name="bom_list"),
    path("bom/<str:environment>/table/", views.bom_table, name="bom_table"),
    path(
        "bom/<str:environment>/create-changeset/",
        views.bom_create_changeset,
        name="bom_create_changeset",
    ),
    path("bom/<str:environment>/dag-data/", views.bom_dag_data, name="bom_dag_data"),
    path(
        "bom/<str:environment>/instance/<str:instance_name>/",
        views.instance_detail,
        name="instance_detail",
    ),
    path(
        "bom/<str:environment>/instance/<str:instance_name>/resources/",
        views.instance_resources,
        name="instance_resources",
    ),
    # ChangeSet Views
    path("changeset/", views.changeset_list, name="changeset_list"),
    path("changeset/new/", views.changeset_create, name="changeset_create"),
    path("changeset/<int:draft_id>/", views.changeset_draft, name="changeset_draft"),
    path(
        "changeset/<int:draft_id>/add/",
        views.changeset_add_item,
        name="changeset_add_item",
    ),
    path(
        "changeset/<int:draft_id>/remove/<int:index>/",
        views.changeset_remove_item,
        name="changeset_remove_item",
    ),
    path(
        "changeset/<int:draft_id>/item/<int:index>/edit-deps/",
        views.changeset_edit_item_deps,
        name="changeset_edit_item_deps",
    ),
    path(
        "changeset/<int:draft_id>/item/<int:index>/save-deps/",
        views.changeset_set_item_deps,
        name="changeset_set_item_deps",
    ),
    path(
        "changeset/<int:draft_id>/item/<int:index>/edit-instance/",
        views.changeset_edit_item_instance,
        name="changeset_edit_item_instance",
    ),
    path(
        "changeset/<int:draft_id>/item/<int:index>/save-instance/",
        views.changeset_set_item_instance,
        name="changeset_set_item_instance",
    ),
    path(
        "changeset/<int:draft_id>/review/",
        views.changeset_review,
        name="changeset_review",
    ),
    path(
        "changeset/<int:draft_id>/bom-impact/",
        views.changeset_bom_impact,
        name="changeset_bom_impact",
    ),
    path(
        "changeset/<int:draft_id>/validate/",
        views.changeset_validate,
        name="changeset_validate",
    ),
    path(
        "changeset/<int:draft_id>/clone/", views.changeset_clone, name="changeset_clone"
    ),
    path(
        "changeset/<int:draft_id>/reject/",
        views.changeset_reject,
        name="changeset_reject",
    ),
    path(
        "changeset/<int:draft_id>/reopen/",
        views.changeset_reopen,
        name="changeset_reopen",
    ),
    path(
        "changeset/<int:draft_id>/search-instances/",
        views.api_search_instances_html,
        name="api_search_instances_html",
    ),
    path(
        "changeset/<int:draft_id>/repo-class-roles/<str:repo_class>/<str:version>/",
        views.api_repo_class_roles,
        name="api_repo_class_roles",
    ),
    path(
        "changeset/<int:draft_id>/repo-class-roles/",
        views.api_repo_class_roles_query,
        name="api_repo_class_roles_query",
    ),
    path(
        "changeset/<int:draft_id>/dep-candidates/",
        views.api_dep_candidates,
        name="api_dep_candidates",
    ),
    # Backward-compat redirects for old bookmarks
    path(
        "changeset/draft/",
        views.changeset_draft_redirect,
        name="changeset_draft_redirect",
    ),
    path(
        "changeset/review/",
        views.changeset_review_redirect,
        name="changeset_review_redirect",
    ),
    # Deployment Status Views
    # Repo Classes
    path("repo-classes/", views.repo_class_list, name="repo_class_list"),
    # Before the <str:repo_class_name>/ route, or "capabilities" is a class name.
    path(
        "repo-classes/capabilities/",
        views.capability_search,
        name="capability_search",
    ),
    path(
        "repo-classes/<str:repo_class_name>/",
        views.repo_class_detail,
        name="repo_class_detail",
    ),
    path(
        "repo-classes/<str:repo_class_name>/versions/<str:version>/",
        views.repo_class_version_detail,
        name="repo_class_version_detail",
    ),
    # Resources (read-only browse of the NERD0004/0006 resource model)
    path(
        "resources/definitions/",
        views.resource_definition_list,
        name="resource_definition_list",
    ),
    path(
        "resources/definitions/<str:rd_id>/",
        views.resource_definition_detail,
        name="resource_definition_detail",
    ),
    path("resources/", views.resource_list, name="resource_list"),
    # API endpoints for HTMX
    path(
        "api/versions/<str:repo_class_name>/",
        views.api_repo_versions,
        name="api_repo_versions",
    ),
    path(
        "api/repo-classes/options/",
        views.api_repo_class_options,
        name="api_repo_class_options",
    ),
    path(
        "api/repo-classes/versions/options/",
        views.api_repo_class_versions_options,
        name="api_repo_class_versions_options",
    ),
    path(
        "api/repo-class-version-resources/",
        views.api_repo_class_version_resources,
        name="api_repo_class_version_resources",
    ),
    path(
        "api/search/instances/", views.api_search_instances, name="api_search_instances"
    ),
    # Health check
    path("health/", views.health_check, name="health_check"),
]
