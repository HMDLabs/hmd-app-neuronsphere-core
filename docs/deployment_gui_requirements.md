# Requirements for a GUI to hmd-ms-deployment

This document details the requirements for a GUI to the NeuronSphere Deployment Service, in the hmd-ms-deployment repo.
The GUI should extend and enhance the UX already provided by the hmd-cli-ns-bootstrap tool.
It will allow NeuronSphere Admins the ability to manage their NeuronSphere deployments visually without resorting to editing JSON in the terminal.
NeuronSphere Admins should be able to deploy updates to their NeuronSphere Environments, see what is currently deployed with its configuration, and destroy deployed instances if necessary.
It should have robust user management and RBAC in place through OAuth2 providers, notably Okta and Auth0.

## Technologies

The GUI application should be created with the following technologies:

- **Django 5.x** - Web framework with ORM for local state, sessions, and user management
- **HTMX 2.x** - Dynamic UI updates without full page reloads
- **Alpine.js** - Lightweight JavaScript for interactive components (forms, modals, DAG interactions)
- **Tailwind CSS** or **Bootstrap 5** - Responsive UI styling
- **D3.js** or **Cytoscape.js** - DAG visualization for dependency graphs
- **Docker** - Container packaging
- **Helm** - Kubernetes deployment

### Backend Dependencies

- **django-allauth** - OAuth2 integration for Okta/Auth0
- **django-htmx** - HTMX integration utilities
- **httpx** or **requests** - HTTP client for hmd-ms-deployment API calls
- **channels** (optional) - WebSocket support for real-time status updates

## Visual Design

The GUI follows a **clean minimalist admin interface** design, consistent with the NeuronSphere brand identity at neuronsphere.io.

### Design Principles

- **Minimal and professional** - Clean layouts, generous whitespace, no visual clutter
- **Data-first** - Tables, status indicators, and actionable information take priority over decoration
- **Quiet chrome** - Navigation, headers, and controls recede; content is the focus
- **Consistent feedback** - Status colors, loading states, and flash messages follow a unified system

### Typography

Fonts are sourced from Google Fonts to match the NeuronSphere website:

| Role | Font | Weights | Usage |
|------|------|---------|-------|
| Logo / Brand | **Comfortaa** | 400, 700 | Logo text in nav and footer |
| Headings | **Comfortaa** | 400, 500, 600, 700 | Page titles, section headers, card headings |
| Body / UI | **Source Sans 3** | 300-900 | All body text, form labels, table content, navigation |

### Color Palette

Derived from the NeuronSphere brand at neuronsphere.io:

**Brand Colors:**
| Token | Hex | Usage |
|-------|-----|-------|
| `ns-navy` | `#180075` | Primary brand navy. Logo text, dark section backgrounds |
| `ns-magenta` | `#A70B52` | Brand accent. CTA buttons, destructive/warning highlights, logo accent |

**UI Surface Colors:**
| Token | Hex | Usage |
|-------|-----|-------|
| `ns-dark` | `#0B0D2C` | Deepest background (footer) |
| `ns-navy` | `#180075` | Sidebar, top nav, dark panels |
| `ns-mist` | `#F4F4F9` | Page background, light sections |
| `ns-white` | `#FFFFFF` | Cards, tables, content panels |

**Text Colors:**
| Token | Hex | Usage |
|-------|-----|-------|
| `ns-text` | `#161718` | Primary body text on light backgrounds |
| `ns-text-muted` | `#6B7280` | Secondary text, descriptions, timestamps |
| `ns-text-inverse` | `#FFFFFF` | Text on dark backgrounds |
| `ns-text-lavender` | `#D4D0E2` | Muted text on dark backgrounds |

**Accent / Interactive Colors:**
| Token | Hex | Usage |
|-------|-----|-------|
| `ns-magenta` | `#A70B52` | Primary action buttons, active states |
| `ns-electric` | `#3DBCD8` | Links, hover accents, informational highlights |
| `ns-lime` | `#E7F2BC` | Success states (DEPLOYED, COMPLETED) |

**Status Badge Colors:**
| Status | Background | Text |
|--------|-----------|------|
| DEPLOYED / COMPLETED | `#E7F2BC` | `#065f46` |
| DEPLOY_NEXT / STARTED | `rgba(61,188,216,0.2)` | `#180075` |
| FAILED | `rgba(167,11,82,0.15)` | `#A70B52` |
| DESTROYED / SKIPPED | `#D7DCDD` | `#3A4046` |
| DESTROY_NEXT | `#fef3c7` | `#92400e` |
| CREATED | `rgba(24,0,117,0.1)` | `#180075` |

### Layout

- **Top nav**: Fixed, `ns-navy` background, logo left, user/logout right
- **Sidebar**: Collapsible, `ns-navy` background, icon + label navigation with environment tree
- **Content area**: `ns-mist` background with white card panels for content sections
- **Footer**: Minimal, `ns-dark` background, centered brand + copyright

### Component Guidelines

- **Cards**: White background, subtle shadow (`shadow`), rounded corners (`rounded-lg`), optional colored left border for environment cards
- **Tables**: White background, gray header row, divide-y row separators, hover highlight
- **Buttons**: Primary uses `ns-magenta` with white text and rounded corners. Secondary uses gray border outline. Pill-shaped for CTAs (`rounded-full`)
- **Forms**: Standard inputs with gray borders, focus ring in `ns-magenta`
- **Flash messages**: Colored banners (red/green/yellow/blue) with dismiss button
- **Loading**: Thin gradient bar (navy -> magenta -> electric) at top of viewport during HTMX requests

## Functional Requirements

### Authentication/Authorization

- **Cloud deployments:** Okta OIDC authentication via django-allauth (``SOCIALACCOUNT_ONLY = True``)
- **Local development:** Email/password authentication via Django's ModelBackend
- RBAC should be used to determine what actions a user can perform
    - Admin: full control within assigned environments
    - Deployer: allows creating and editing deployments
    - Viewer: allows only viewing what is deployed
- Users should be further limited to what Environments or DeploymentSets they can take action in

#### Okta Group-to-Role Mapping

- Okta groups are provisioned via CDKTF
- The ``OKTA_GROUP_MAPPING`` environment variable provides a JSON mapping of Okta group names to environment+role pairs (set at deploy time)
- On each Okta login, the user's ``groups`` claim is resolved against this mapping to assign environment permissions
- Okta-synced permissions (``source=okta``) are authoritative: replaced on each login
- Manually-assigned permissions (``source=manual``) are never modified by the sync
- When a user has permissions from multiple sources, the highest role wins (admin > deployer > viewer)
- The Okta authorization server must include a ``groups`` claim in the ID token (configured via CDKTF)

### Deployment Views

All views should interact with the hmd-ms-deployment REST API endpoints to fetch data. If necessary, some local settings or extra data may be stored in a Django database via its ORM.
However, hmd-ms-deployment will remain the source of truth about the NeuronSphere deployments.

#### Environment Discovery

Environments are dynamically fetched from the Deployment service via `GET /api/hmd_lang_deployment.environment`. The GUI does not use hardcoded default environments. If no environments are found in the Deployment service, the GUI displays an empty state prompting the user to contact their administrator. The environment `type` attribute is used as the environment identifier throughout the GUI.

#### 1. Environment BOM View

Shows currently deployed instances in a given Environment.

**API Endpoints Used:**
- `GET /api/hmd_lang_deployment.environment` - Lists all available environments
- `GET /apiop/get_deployment_bom/<environment_type>` - Retrieves Bill of Materials for environment
- `GET /apiop/get_deployment_info/<environment_type>` - Retrieves PlantUML diagram data

**Display Options:**
- **Table View**: Sortable/filterable table with columns:
  - Instance Name
  - RepoClass
  - Version (RepoClassVersion)
  - Status (DEPLOYED, DEPLOY_NEXT, FAILED, etc.)
  - Last Deployed timestamp
  - Deployment ID link
- **DAG View**: Interactive dependency graph using D3.js/Cytoscape.js
  - Nodes colored by status
  - Click node to view instance details
  - Zoom/pan navigation
  - Filter by RepoClass type

**Instance Detail Panel:**
- Current configuration (merged default + instance config)
- Dependency list with versions
- Deployment history via `GET /apiop/get_deployment_history/<environment_type>/<instance_name>`
- Quick actions: Edit, Redeploy, Destroy (based on RBAC)

#### 2. ChangeSet Creation View

Allows building and managing ChangeSets for deployment.

**API Endpoints Used:**
- `POST /apiop/find_repo_class_versions/<repo_class_name>` - List available versions
- `GET /apiop/get_repo_class_instances/<repo_class_name>/<environment_type>` - Get existing instances
- `POST /apiop/apply_changeset` - Apply ChangeSet to DeploymentSet

**Features:**
- **Edit Mode on BOM View**: Click instance to modify, changes tracked in session-based ChangeSet draft
- **Review Panel**: Shows pending changes before submission
  - Added instances (green)
  - Modified instances (yellow)
  - Instances marked for destruction (red)
- **RepoClass Browser**: Searchable list of all RepoClasses with available versions
- **Dynamic Configuration Form**:
  - Generated from `default_configuration` in manifest.json for selected RepoClassVersion
  - Field types inferred from JSON schema or value types
  - Validation before submission
- **Add Instance Wizard**:
  1. Select RepoClass
  2. Select RepoClassVersion (shows compatible versions)
  3. Name instance
  4. Configure (pre-populated with defaults)
  5. Review dependencies (auto-resolved or manually selected)
- **Copy Instance**: Clone existing instance with new name, optionally update version
- **Cascade Selection**: Select ancestor instance to include all downstream dependents in ChangeSet
- **Dependency Switching**: For EKS upgrades, select instances to reroute to new cluster instance

**ChangeSet Schema** (hmd-lang-deployment.change_set):
```json
{
  "name": "string",
  "repo_instances": [
    {
      "name": "string",
      "repo_class_name": "string",
      "repo_class_version": "string",
      "configuration": {},
      "deploy_action": "DEPLOY|DESTROY"
    }
  ]
}
```

#### 3. Deployment Workflow View

Monitor active and historical deployments.

**API Endpoints Used:**
- `GET /apiop/get_deployment_logs/<change_set_deployment_id>` - Fetch Argo logs
- Status endpoints for real-time updates (see Suggested API Changes below)

**Features:**
- **Recent Deployments List**: Paginated list of ChangeSetDeployments
  - Filter by DeploymentSet, Environment, status, date range
  - Status badges: CREATED, STARTED, COMPLETED, FAILED, SKIPPED
- **Deployment Detail View**:
  - ChangeSetDeployment header with overall status
  - Per-Environment breakdown (ChangeSetEnvDeployment)
  - Individual RepoInstanceDeployment status list/DAG
  - Timeline visualization showing deployment progression
- **Log Viewer**:
  - Fetch from S3 (completed) or streaming from Argo pod (in-progress)
  - Syntax highlighting for deployment output
  - Download log option
- **Real-time Updates**:
  - Polling via HTMX `hx-trigger="every 5s"` or WebSocket for live status

#### 4. Telemetry & Service Health View

Display operational telemetry and health status for deployed instances.

**Data Source:** An `hmd-ms-telemetry-debug` instance deployed in the same environment as the monitored services. The GUI discovers this service from the environment BOM using a default instance name of `ms-telemetry`. This can be overridden per-environment via the Service Discovery Configuration (see below).

**API Endpoints Used (via hmd-ms-telemetry-debug):**
- `POST /apiop/health_check` - Evaluate service health against defined metric profiles
- `POST /apiop/service_statistics` - Overall service performance statistics
- `POST /apiop/query_traces` - Query distributed traces with filters (service, span name, duration, status)
- `POST /apiop/query_logs` - Query logs with filters (severity, text search, trace ID)
- `POST /apiop/query_metrics` - Query raw metrics (gauge, counter, histogram)
- `POST /apiop/analyze_service` - Comprehensive service analysis (slowness, errors, patterns)
- `POST /apiop/error_summary` - Summarize errors within a time range
- `POST /apiop/slow_operations` - Identify slow operations
- `POST /apiop/failed_operations` - Identify failed operations
- `POST /apiop/trace_detail` - Get full trace with all spans and correlated logs
- `GET /apiop/list_services` - List all services reporting telemetry

**Features:**
- Instance selector (from BOM)
- Time range picker
- **Health Dashboard:**
  - Per-service health status (from `health_check` against service profiles)
  - At-a-glance environment health overview
- **Metrics Dashboard:**
  - Request latency (p50, p95, p99)
  - Error rates
  - Throughput
  - Resource utilization
- **Log Search** with filters by:
  - `hmd.instance.name`
  - `hmd.environment`
  - `hmd.deployment.id`
  - Severity level
- **Trace Explorer** linking to distributed traces with span timeline visualization
- **Error & Slow Operation Summaries** with direct links to relevant traces

##### Transform Monitoring

When an `hmd-ms-transform` instance is available in the environment (default instance name: `ms-transform`), the telemetry view exposes additional transform-specific monitoring via the telemetry service:

- `POST /apiop/transform_health` - Health check for transform workflows
- `POST /apiop/transform_statistics` - Transform performance statistics
- `POST /apiop/slow_transforms` - Identify slow-running transforms
- `POST /apiop/failed_transforms` - Identify failed transforms

##### Service Discovery Configuration

The GUI uses a convention-based approach to discover common NeuronSphere services deployed in each environment. Services are located by looking up their default instance name in the environment BOM. Per-environment overrides allow administrators to point to differently-named instances.

| Service | Derived From | Default Instance Name | Purpose |
|---------|-------------|----------------------|---------|
| Telemetry | `hmd-ms-telemetry-debug` | `ms-telemetry` | Health monitoring, metrics, logs, traces |
| Transform | `hmd-ms-transform` | `ms-transform` | Transform workflow monitoring & statistics |
| Librarian | `hmd-ms-librarian` | `ms-librarian` | Content catalog queries |

**Resolution Logic:**
1. Check `EnvironmentServiceConfig` for a per-environment override for the service type
2. If no override exists, look up the default instance name in the environment BOM
3. If the service instance is found and its status is DEPLOYED, the feature is enabled
4. If the service instance is not found, the corresponding UI section is hidden gracefully

#### 5. Environment Differences View

Compare deployments between environments.

**API Endpoints Used:**
- `POST /apiop/compare_environments` - Compare two environments

**Request Body:**
```json
{
  "source_environment": "dev",
  "target_environment": "test"
}
```

**Features:**
- Environment selector (source vs target)
- Diff display:
  - Instances only in source
  - Instances only in target
  - Instances in both with different versions/configs (highlight changes)
- **Configuration Diff**: Side-by-side JSON comparison with highlighting
- **Generate ChangeSet from Diff**:
  - Select instances to include
  - Option: Configuration only (same version, different config)
  - Option: Full sync (update version and config)
  - Option: Include dependencies (cascading updates)
- Generated ChangeSets are deployment-set-agnostic; pick a target DeploymentSet at apply time.

## Non-Functional Requirements

### Performance

- Page load time: < 2 seconds for BOM views with up to 100 instances
- DAG rendering: < 3 seconds for graphs with up to 200 nodes
- API response caching: Cache BOM and RepoClassVersion data with 30-second TTL
- Pagination: All list views should paginate at 50 items per page

### Scalability

- Support concurrent users: 50+ simultaneous active sessions
- Handle environments with 500+ deployed instances
- Stateless Django application for horizontal scaling behind load balancer

### Availability

- Target uptime: 99.5% (non-critical admin tool)
- Graceful degradation: Show cached data if hmd-ms-deployment API is temporarily unavailable
- Health check endpoint for Kubernetes liveness/readiness probes

### Security

- All communication over HTTPS/TLS
- CSRF protection on all forms (Django default)
- Session timeout: 8 hours of inactivity
- Audit logging: Record all deployment actions with user, timestamp, and details
- No secrets stored in Django database; use environment variables or external secrets manager
- Input sanitization for all user-provided configuration values

### Observability

- Structured logging with correlation IDs
- Metrics export for Prometheus/OTEL:
  - Request latency histograms
  - Error rates by endpoint
  - Active user sessions
- Integration with existing NeuronSphere OTEL collector

## Suggested API Changes for hmd-ms-deployment

The following new endpoints or modifications are recommended for hmd-ms-deployment to fully support the GUI requirements:

### New Endpoints Required

#### 1. List All RepoClasses

```
GET /apiop/list_repo_classes
```

**Purpose:** Provide a searchable list of all available RepoClasses for the Add Instance wizard.

**Response:**
```json
{
  "repo_classes": [
    {
      "name": "hmd-vpc",
      "description": "VPC infrastructure",
      "latest_version": "0.1.25",
      "repo_type": "hmd-inf"
    }
  ]
}
```

#### 2. Get RepoClassVersion Details with Default Configuration

```
GET /apiop/get_repo_class_version/<repo_class_name>/<version>
```

**Purpose:** Retrieve full details of a RepoClassVersion including default_configuration for form generation.

**Response:**
```json
{
  "repo_class_name": "hmd-vpc",
  "version": "0.1.25",
  "default_configuration": {
    "vpc_cidr": "10.0.0.0/16",
    "enable_nat": true
  },
  "dependencies": [
    {
      "repo_class_name": "hmd-inf-account",
      "version_spec": "~= 0.1",
      "required": true
    }
  ],
  "configuration_schema": {
    "type": "object",
    "properties": {
      "vpc_cidr": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+\\.\\d+/\\d+$"},
      "enable_nat": {"type": "boolean"}
    }
  }
}
```

**Note:** The `configuration_schema` field (JSON Schema) is optional but highly recommended for form validation. This could be added to RepoClassVersion entities or derived from manifest.json during version registration.

#### 3. List ChangeSetDeployments

```
GET /apiop/list_change_set_deployments
```

**Purpose:** Paginated list of recent ChangeSetDeployments for the Deployment Workflow view.

**Query Parameters:**
- `deployment_set` (optional) - Filter by DeploymentSet name
- `status` (optional) - Filter by status
- `limit` (default: 50)
- `offset` (default: 0)
- `since` (optional) - ISO timestamp for date filtering

**Response:**
```json
{
  "total": 150,
  "items": [
    {
      "id": "csd-12345",
      "change_set_name": "release-v2.1",
      "deployment_set_name": "dev-test-prod",
      "status": "COMPLETED",
      "created_at": "2024-01-15T10:30:00Z",
      "completed_at": "2024-01-15T11:45:00Z",
      "created_by": "user@example.com"
    }
  ]
}
```

#### 4. Get ChangeSetDeployment Details

```
GET /apiop/get_change_set_deployment/<id>
```

**Purpose:** Full details of a ChangeSetDeployment including all ChangeSetEnvDeployments and RepoInstanceDeployments.

**Response:**
```json
{
  "id": "csd-12345",
  "change_set_name": "release-v2.1",
  "deployment_set_name": "dev-test-prod",
  "status": "STARTED",
  "environments": [
    {
      "environment": "dev",
      "status": "COMPLETED",
      "instance_deployments": [
        {
          "instance_name": "base-vpc",
          "repo_class_name": "hmd-vpc",
          "version": "0.1.25",
          "status": "DEPLOYED",
          "started_at": "2024-01-15T10:35:00Z",
          "completed_at": "2024-01-15T10:42:00Z"
        }
      ]
    },
    {
      "environment": "test",
      "status": "STARTED",
      "instance_deployments": []
    }
  ]
}
```

#### 5. Get Downstream Dependents

```
POST /apiop/get_downstream_dependents
```

**Purpose:** Given an instance, return all instances that depend on it (directly or transitively). Supports cascade selection and EKS upgrade workflows.

**Request:**
```json
{
  "environment": "dev",
  "instance_name": "base-eks-cluster"
}
```

**Response:**
```json
{
  "dependents": [
    {
      "instance_name": "app-service-1",
      "repo_class_name": "hmd-ms-app",
      "depth": 1
    },
    {
      "instance_name": "app-service-2",
      "repo_class_name": "hmd-ms-app",
      "depth": 1
    }
  ]
}
```

#### 6. Validate ChangeSet

```
POST /apiop/validate_changeset
```

**Purpose:** Validate a ChangeSet before applying (dependency resolution, version compatibility, circular dependency detection).

**Request:** ChangeSet JSON

**Response:**
```json
{
  "valid": false,
  "errors": [
    {
      "type": "missing_dependency",
      "instance": "new-service",
      "message": "Required dependency hmd-vpc not found in environment"
    }
  ],
  "warnings": [
    {
      "type": "version_mismatch",
      "instance": "base-vpc",
      "message": "Version 0.1.20 is older than currently deployed 0.1.25"
    }
  ]
}
```

### Modifications to Existing Endpoints

#### Enhance compare_environments Response

Add configuration diff details to the comparison response:

```json
{
  "source": "dev",
  "target": "test",
  "differences": [
    {
      "instance_name": "base-vpc",
      "source_version": "0.1.25",
      "target_version": "0.1.20",
      "config_diff": {
        "added": {},
        "removed": {},
        "changed": {
          "vpc_cidr": {
            "source": "10.0.0.0/16",
            "target": "10.1.0.0/16"
          }
        }
      }
    }
  ]
}
```

#### Add Pagination to find_repo_class_versions

Support `limit` and `offset` query parameters for large RepoClass histories.

#### Add created_by Field to ChangeSetDeployment

Track which user initiated the deployment for audit purposes. This requires:
1. Accepting a `created_by` parameter in `/apiop/apply_changeset`
2. Storing it in the ChangeSetDeployment entity
3. Returning it in list/detail endpoints

## Django Data Model

The GUI should store minimal local data. The following Django models are suggested:

```python
from django.db import models
from django.contrib.auth.models import User

class UserEnvironmentPermission(models.Model):
    """RBAC: Limit user access to specific environments"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    environment = models.CharField(max_length=50)  # e.g., "dev", "test", "prod"
    role = models.CharField(max_length=20, choices=[
        ('viewer', 'Viewer'),
        ('deployer', 'Deployer'),
        ('admin', 'Admin'),
    ])
    source = models.CharField(max_length=20, choices=[
        ('manual', 'Manual'),
        ('okta', 'Okta'),
    ], default='manual')  # Tracks if permission was synced from Okta or manually assigned

    class Meta:
        unique_together = ['user', 'environment', 'source']

class DeploymentSetPermission(models.Model):
    """RBAC: Limit user access to specific deployment sets"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    deployment_set = models.CharField(max_length=100)
    can_deploy = models.BooleanField(default=False)

class AuditLog(models.Model):
    """Track all deployment actions for compliance"""
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50)  # e.g., "apply_changeset", "destroy_instance"
    target = models.CharField(max_length=200)  # e.g., "dev:base-vpc"
    details = models.JSONField()  # Full request payload
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True)
    success = models.BooleanField()
    error_message = models.TextField(null=True, blank=True)

class ChangeSetDraft(models.Model):
    """Session-persisted ChangeSet drafts before submission"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    target_deployment_set = models.CharField(max_length=100)
    content = models.JSONField()  # ChangeSet JSON
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class EnvironmentServiceConfig(models.Model):
    """Override default service instance names per environment"""
    environment = models.CharField(max_length=50)  # e.g., "dev", "test", "prod"
    service_type = models.CharField(max_length=50)  # e.g., "telemetry", "transform", "librarian"
    instance_name = models.CharField(max_length=100)  # overridden instance name

    class Meta:
        unique_together = ['environment', 'service_type']

class UserPreference(models.Model):
    """Store user UI preferences"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    default_environment = models.CharField(max_length=50, null=True)
    default_view = models.CharField(max_length=20, default='table')  # 'table' or 'dag'
    items_per_page = models.IntegerField(default=50)
```

## Deployment Architecture

```
                    ┌─────────────────┐
                    │   Load Balancer │
                    │    (Ingress)    │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
        │  Django   │  │  Django   │  │  Django   │
        │  Pod #1   │  │  Pod #2   │  │  Pod #N   │
        └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼─────┐  ┌─────▼─────┐  ┌───────────────┐
        │PostgreSQL │  │hmd-ms-    │  │hmd-ms-        │
        │ (Django)  │  │deployment │  │telemetry-debug│
        └───────────┘  │   API     │  │(per-env)      │
                       └───────────┘  └───────────────┘
```

### Kubernetes Resources

- **Deployment**: Django application (2+ replicas)
- **Service**: ClusterIP for internal communication
- **Ingress**: External HTTPS access with TLS termination
- **ConfigMap**: Non-sensitive configuration
- **Secret**: Database credentials, OAuth client secrets
- **PersistentVolumeClaim**: Optional, for static file storage (or use S3)

### Environment Variables

```yaml
# Django settings
DJANGO_SECRET_KEY: <from-secret>
DJANGO_DEBUG: "false"
DJANGO_ALLOWED_HOSTS: "deployment-gui.neuronsphere.example.com"

# Database
DATABASE_URL: "postgresql://user:pass@host:5432/deployment_gui"

# OAuth
OAUTH_CLIENT_ID: <from-secret>
OAUTH_CLIENT_SECRET: <from-secret>
OAUTH_PROVIDER_URL: "https://yourorg.okta.com"

# Okta group-to-role mapping (JSON, provisioned via CDKTF)
OKTA_GROUP_MAPPING: '{"ns-dev-deployers":{"dev":"deployer"},"ns-prod-admins":{"prod":"admin"}}'

# hmd-ms-deployment API
DEPLOYMENT_API_URL: "https://deployment-api.neuronsphere.internal"
DEPLOYMENT_API_TOKEN: <from-secret>  # Service account token

# Service Discovery (optional overrides - defaults use BOM lookup)
# TELEMETRY_INSTANCE_NAME: "ms-telemetry"  # Override default telemetry instance name
# TRANSFORM_INSTANCE_NAME: "ms-transform"  # Override default transform instance name
# LIBRARIAN_INSTANCE_NAME: "ms-librarian"  # Override default librarian instance name
```

## Open Questions

1. **ChangeSet Persistence**: Should ChangeSets be created immediately in hmd-ms-deployment when users start editing, or should drafts remain local in Django until explicit submission?

2. **Real-time Updates**: Should we implement WebSocket connections for live deployment status, or is HTMX polling (every 5 seconds) sufficient?

3. **Configuration Schema**: Should hmd-ms-deployment provide JSON Schema for RepoClassVersion configurations, or should the GUI infer field types from default values?

4. ~~**Telemetry Integration**: Should telemetry queries go through hmd-ms-deployment, or should the GUI connect directly to ClickHouse?~~ **Resolved:** Telemetry queries go through an `hmd-ms-telemetry-debug` instance deployed in the same environment, discovered via the BOM with default instance name `ms-telemetry`.

5. **Multi-tenant Isolation**: For MSP deployments, should the GUI support multiple separate NeuronSphere installations, or one GUI per installation?

## Implementation Phases

### Phase 1: Core Views (MVP)
- Authentication with Okta/Auth0
- Environment BOM view (table only)
- Basic ChangeSet creation and application
- Deployment status viewing

### Phase 2: Enhanced Visualization
- DAG view for BOM
- Deployment workflow timeline
- Environment diff view

### Phase 3: Advanced Features
- Cascade selection and dependency switching
- Telemetry integration
- Advanced RBAC with environment restrictions

### Phase 4: Polish
- User preferences
- Audit log viewer
- Performance optimizations