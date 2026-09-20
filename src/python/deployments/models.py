"""Django models for NeuronSphere Deployment GUI."""
import hashlib
import secrets

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator


class UserEnvironmentPermission(models.Model):
    """RBAC: Limit user access to specific environments."""

    class Role(models.TextChoices):
        VIEWER = "viewer", "Viewer"
        DEPLOYER = "deployer", "Deployer"
        ADMIN = "admin", "Admin"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        OKTA = "okta", "Okta"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="environment_permissions",
    )
    environment = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Environment type (e.g., 'dev', 'test', 'prod')",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.VIEWER,
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.MANUAL,
        help_text="How this permission was assigned (manual or synced from Okta)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["user", "environment", "source"]
        ordering = ["user", "environment"]
        indexes = [
            models.Index(fields=["user", "role"]),
            models.Index(fields=["user", "source"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.environment} ({self.role}, {self.source})"

    @classmethod
    def user_can_deploy(cls, user, environment):
        """Check if user has deployer or admin role for environment."""
        if user.is_superuser:
            return True
        return cls.objects.filter(
            user=user,
            environment=environment,
            role__in=[cls.Role.DEPLOYER, cls.Role.ADMIN],
        ).exists()

    @classmethod
    def user_can_view(cls, user, environment):
        """Check if user has any access to environment."""
        if user.is_superuser:
            return True
        return cls.objects.filter(user=user, environment=environment).exists()

    @classmethod
    def get_user_environments(cls, user):
        """Get list of environments user has access to."""
        if user.is_superuser:
            return None  # Superuser has access to all
        return list(
            cls.objects.filter(user=user)
            .values_list("environment", flat=True)
            .distinct()
        )


class AuditLog(models.Model):
    """Track all deployment actions for compliance."""

    class Action(models.TextChoices):
        VIEW_BOM = "view_bom", "View BOM"
        VIEW_INSTANCE = "view_instance", "View Instance"
        CREATE_CHANGESET = "create_changeset", "Create ChangeSet"
        APPLY_CHANGESET = "apply_changeset", "Apply ChangeSet"
        VIEW_DEPLOYMENT = "view_deployment", "View Deployment"
        VIEW_LOGS = "view_logs", "View Logs"
        REJECT_CHANGESET = "reject_changeset", "Reject ChangeSet"
        REOPEN_CHANGESET = "reopen_changeset", "Reopen ChangeSet"
        CLONE_CHANGESET = "clone_changeset", "Clone ChangeSet"
        GROUP_SYNC = "group_sync", "Sync Groups from Okta"
        MCP_TOOL_CALL = "mcp_tool_call", "MCP Tool Call"

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=50, choices=Action.choices)
    target = models.CharField(
        max_length=200,
        help_text="Target resource (e.g., 'dev:base-vpc')",
    )
    details = models.JSONField(
        default=dict,
        help_text="Full request details",
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    correlation_id = models.CharField(
        max_length=36,
        blank=True,
        help_text="Request correlation ID for tracing",
    )
    success = models.BooleanField(default=True)
    error_message = models.TextField(null=True, blank=True)
    duration_ms = models.IntegerField(
        null=True,
        help_text="Request duration in milliseconds",
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["action", "-timestamp"]),
            models.Index(fields=["target", "-timestamp"]),
        ]

    def __str__(self):
        username = self.user.username if self.user else "anonymous"
        return f"{username} - {self.action} - {self.target}"


_CHANGESET_ITEM_ALLOWED_KEYS = (
    "deployment_id",
    "repo_instance_name",
    "repo_class_name",
    "repo_class_version",
    "instance_configuration",
    "dependencies",
    "config_spec",
    "image_only",
)


def sanitize_changeset_item(item: dict) -> dict:
    """Strip BOM/runtime fields (status, auto_deploy, etc.) that the
    backend's change_set schema rejects via additionalProperties: False."""
    return {k: item[k] for k in _CHANGESET_ITEM_ALLOWED_KEYS if k in item}


def topological_sort_changeset(items: list) -> list:
    """Order ChangeSet items so each instance appears after the in-draft
    instances it depends on. Dependencies point earlier, dependents later.

    Only edges whose target is another item in this list constrain ordering
    (external/BOM instances already exist). Stable: items with no ordering
    constraint keep their original relative order. Cycles cannot be ordered,
    so any items left in a cycle are appended in original order (the backend's
    validate step reports the circular dependency).
    """
    items = list(items or [])
    if not items:
        return items

    # First occurrence of each name wins; unnamed items impose no constraints.
    name_to_index = {}
    for idx, item in enumerate(items):
        name = item.get("repo_instance_name")
        if name and name not in name_to_index:
            name_to_index[name] = idx

    def prerequisites(item):
        """Names this item depends on that are other items in this list."""
        deps = set()
        for targets in (item.get("dependencies") or {}).values():
            candidates = targets if isinstance(targets, list) else [targets]
            for target in candidates:
                if target in name_to_index and target != item.get("repo_instance_name"):
                    deps.add(target)
        return deps

    reqs = [prerequisites(item) for item in items]

    emitted_names = set()
    ordered = []
    remaining = list(range(len(items)))

    while remaining:
        # Emit the earliest-in-original-order item whose prerequisites are met.
        progressed = False
        for pos, idx in enumerate(remaining):
            if reqs[idx] <= emitted_names:
                ordered.append(items[idx])
                name = items[idx].get("repo_instance_name")
                if name:
                    emitted_names.add(name)
                remaining.pop(pos)
                progressed = True
                break
        if not progressed:
            # Cycle: no item's deps can be satisfied. Append the rest in
            # original order and stop — never loop forever.
            ordered.extend(items[idx] for idx in remaining)
            break

    return ordered


class ChangeSetDraft(models.Model):
    """ChangeSet drafts before submission. Environment-agnostic: a portable bundle
    of instances + dependencies that can be applied to one or more DeploymentSets."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_REVIEW = "in_review", "In Review"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="changeset_drafts",
    )
    name = models.CharField(max_length=100)
    content = models.JSONField(
        default=list,
        help_text="List of changes in ChangeSet format",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    rejection_reason = models.TextField(
        blank=True,
        default="",
        help_text="Reason provided when the ChangeSet was rejected",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user.username} - {self.name}"

    @property
    def change_count(self):
        """Return number of changes in the draft."""
        return len(self.content) if self.content else 0

    @property
    def sanitized_content(self):
        # Post instances in dependency order (prerequisites first) so the
        # deployment service never sees a dependent before what it depends on.
        ordered = topological_sort_changeset(self.content or [])
        return [sanitize_changeset_item(item) for item in ordered]

    def save(self, *args, **kwargs):
        if self.content:
            self.content = [sanitize_changeset_item(item) for item in self.content]
        super().save(*args, **kwargs)


class ChangeSetApplication(models.Model):
    """Record of a ChangeSet being applied to a DeploymentSet.

    A single draft can be applied to multiple DeploymentSets; each apply
    creates one row. csd_id is set on successful submission to the backend.
    """

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        FAILED = "failed", "Failed"

    draft = models.ForeignKey(
        ChangeSetDraft,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    deployment_set = models.CharField(max_length=100)
    csd_id = models.CharField(max_length=100, blank=True, default="")
    applied_at = models.DateTimeField(auto_now_add=True)
    applied_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="changeset_applications",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUBMITTED,
    )
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-applied_at"]

    def __str__(self):
        return f"{self.draft.name} → {self.deployment_set} ({self.status})"


class DeploymentSetPermission(models.Model):
    """RBAC: Limit user access to specific deployment sets."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="deployment_set_permissions",
    )
    deployment_set = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Deployment set name (e.g., 'dev-main', 'prod-primary')",
    )
    can_deploy = models.BooleanField(
        default=False,
        help_text="Whether the user can deploy to this deployment set",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["user", "deployment_set"]
        ordering = ["user", "deployment_set"]

    def __str__(self):
        access = "deploy" if self.can_deploy else "view"
        return f"{self.user.username} - {self.deployment_set} ({access})"

    @classmethod
    def user_can_deploy_to_set(cls, user, deployment_set):
        """Check if user has deploy permission for a deployment set.

        Args:
            user: Django User instance
            deployment_set: Deployment set name

        Returns:
            True if user is superuser or has can_deploy=True for the set
        """
        if user.is_superuser:
            return True
        return cls.objects.filter(
            user=user,
            deployment_set=deployment_set,
            can_deploy=True,
        ).exists()

    @classmethod
    def user_can_view_set(cls, user, deployment_set):
        """Check if user has any access to a deployment set.

        Args:
            user: Django User instance
            deployment_set: Deployment set name

        Returns:
            True if user is superuser or has any permission for the set
        """
        if user.is_superuser:
            return True
        return cls.objects.filter(
            user=user,
            deployment_set=deployment_set,
        ).exists()

    @classmethod
    def get_user_deployment_sets(cls, user):
        """Get list of deployment sets user has access to.

        Args:
            user: Django User instance

        Returns:
            None for superusers (access to all), or list of deployment set names
        """
        if user.is_superuser:
            return None
        return list(
            cls.objects.filter(user=user)
            .values_list("deployment_set", flat=True)
            .distinct()
        )


class EnvironmentServiceConfig(models.Model):
    """Override default service instance names per environment.

    Used for service discovery — maps a service type (e.g., 'telemetry')
    to the actual instance name deployed in a given environment.
    """

    environment = models.CharField(
        max_length=50,
        help_text="Environment type (e.g., 'dev', 'test', 'prod')",
    )
    service_type = models.CharField(
        max_length=50,
        help_text="Service type (e.g., 'telemetry', 'transform', 'librarian')",
    )
    instance_name = models.CharField(
        max_length=100,
        help_text="Overridden instance name in the BOM",
    )

    class Meta:
        unique_together = ["environment", "service_type"]
        ordering = ["environment", "service_type"]

    def __str__(self):
        return f"{self.environment}:{self.service_type} -> {self.instance_name}"

    # Default instance names per service type (used when no override exists)
    DEFAULT_INSTANCE_NAMES = {
        "telemetry": "ms-telemetry",
        "transform": "ms-transform",
        "librarian": "ms-librarian",
    }

    @classmethod
    def get_instance_name(cls, environment, service_type):
        """Resolve the instance name for a service in an environment.

        Resolution order:
        1. Check for a per-environment override in this table
        2. Fall back to the default instance name for the service type

        Args:
            environment: Environment type string
            service_type: Service type string

        Returns:
            Instance name string, or None if service type is unknown
        """
        try:
            config = cls.objects.get(
                environment=environment,
                service_type=service_type,
            )
            return config.instance_name
        except cls.DoesNotExist:
            return cls.DEFAULT_INSTANCE_NAMES.get(service_type)


class UserPreference(models.Model):
    """Store user UI preferences."""

    class ViewMode(models.TextChoices):
        TABLE = "table", "Table View"
        DAG = "dag", "DAG View"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    default_environment = models.CharField(
        max_length=50,
        null=True,
        blank=True,
    )
    default_deployment_set = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )
    default_view = models.CharField(
        max_length=20,
        choices=ViewMode.choices,
        default=ViewMode.TABLE,
    )
    items_per_page = models.IntegerField(
        default=50,
        validators=[MinValueValidator(10), MaxValueValidator(200)],
    )

    def __str__(self):
        return f"Preferences for {self.user.username}"


class MCPApiKey(models.Model):
    """A bearer token for the MCP server, bound to a Django user.

    Used where Okta bearer tokens aren't available -- local development, bender
    acceptance runs, and CI. Only the SHA-256 hash of the key is stored; the
    plaintext is shown once at creation and is unrecoverable afterwards.

    The key authorizes *as its owner*: every MCP tool applies the same
    ``UserEnvironmentPermission`` checks the GUI applies to that user. Note the
    deliberate asymmetry documented in NERD008 -- calls authenticated by an API
    key use the service account for the downstream hmd-ms-deployment request,
    because there is no user access token to forward.
    """

    PREFIX = "nsmcp_"
    #: Characters of the generated key retained in the clear, for identification
    #: in the admin and in logs. Not secret and not sufficient to authenticate.
    KEY_PREFIX_LENGTH = 8
    #: Floor for a supplied (rather than generated) key, so the bootstrap path
    #: cannot install something trivially guessable.
    MIN_KEY_LENGTH = 24

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="mcp_api_keys",
    )
    name = models.CharField(
        max_length=100,
        help_text="What this key is for (e.g. 'local dev', 'bender')",
    )
    key_prefix = models.CharField(
        max_length=16,
        db_index=True,
        help_text="Leading characters of the key, for identification only",
    )
    key_hash = models.CharField(
        max_length=64,
        unique=True,
        help_text="SHA-256 hex digest of the full key",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional expiry; blank means the key never expires",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "MCP API key"
        verbose_name_plural = "MCP API keys"

    def __str__(self):
        return f"{self.name} ({self.key_prefix}...) for {self.user.username}"

    @staticmethod
    def hash_key(raw_key: str) -> str:
        """SHA-256 hex digest of a raw key.

        A plain digest rather than a password hash is deliberate: these are
        high-entropy random tokens, not user-chosen secrets, so there is nothing
        for a slow KDF to defend against, and lookup must be a single indexed
        query per request.
        """
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @classmethod
    def generate(cls, user, name: str, expires_at=None, raw_key: str = None):
        """Create a key for ``user``. Returns ``(instance, plaintext_key)``.

        The plaintext is returned once and never stored; callers are responsible
        for displaying it to the operator.

        ``raw_key`` supplies the plaintext instead of generating one. That is
        only for a deploy-time bootstrap where the credential has to be known on
        both sides -- the local ``createLocalMcpKey`` hook, whose key comes from
        the same instance configuration bender reads -- so it is validated for
        the prefix and a minimum length rather than trusted.
        """
        if raw_key:
            if not raw_key.startswith(cls.PREFIX):
                raise ValueError(f"An MCP API key must start with '{cls.PREFIX}'")
            if len(raw_key) < cls.MIN_KEY_LENGTH:
                raise ValueError(
                    f"An MCP API key must be at least {cls.MIN_KEY_LENGTH} "
                    f"characters; got {len(raw_key)}"
                )
        else:
            raw_key = cls.PREFIX + secrets.token_urlsafe(32)
        instance = cls.objects.create(
            user=user,
            name=name,
            key_prefix=raw_key[: cls.KEY_PREFIX_LENGTH],
            key_hash=cls.hash_key(raw_key),
            expires_at=expires_at,
        )
        return instance, raw_key

    @classmethod
    def authenticate(cls, raw_key: str):
        """Return the active, unexpired key matching ``raw_key``, else ``None``.

        Stamps ``last_used_at``. Returns ``None`` rather than raising for every
        failure mode so callers can't accidentally distinguish "unknown key"
        from "revoked key" in a response.
        """
        from django.utils import timezone

        if not raw_key or not raw_key.startswith(cls.PREFIX):
            return None
        try:
            key = cls.objects.select_related("user").get(
                key_hash=cls.hash_key(raw_key), is_active=True
            )
        except cls.DoesNotExist:
            return None
        if key.expires_at and key.expires_at <= timezone.now():
            return None
        key.last_used_at = timezone.now()
        key.save(update_fields=["last_used_at"])
        return key
