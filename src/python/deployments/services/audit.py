"""Audit-log writing, independent of the transport.

Extracted from ``decorators.audit_action`` so the GUI views and the MCP tool
layer write structurally identical ``AuditLog`` rows. A failure to write an
audit row is logged and swallowed -- auditing must never break the request it
is recording.
"""
import logging

logger = logging.getLogger(__name__)


def record_audit(
    *,
    user,
    action,
    target: str = "N/A",
    details: dict = None,
    ip_address=None,
    user_agent: str = "",
    correlation_id: str = None,
    success: bool = True,
    error_message: str = None,
    duration_ms: int = None,
):
    """Write one ``AuditLog`` row. Never raises."""
    from ..models import AuditLog

    try:
        AuditLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            action=action,
            target=target or "N/A",
            details=details or {},
            ip_address=ip_address,
            user_agent=(user_agent or "")[:500],
            # correlation_id and target are non-null CharFields; coerce rather
            # than pass None through, so a caller that omits them writes a row
            # instead of raising an IntegrityError.
            correlation_id=correlation_id or "",
            success=success,
            error_message=error_message,
            duration_ms=duration_ms,
        )
    except Exception as log_error:  # pragma: no cover - defensive
        logger.error(f"Failed to create audit log: {log_error}")


def build_target(**parts) -> str:
    """Join the identifying parts of an audited action into a target string.

    Mirrors the view decorator's ``environment:instance_name:csd_id`` ordering;
    absent or empty parts are dropped, and an empty result becomes ``"N/A"``.
    """
    ordered = [parts.get(k) for k in ("environment", "instance_name", "csd_id")]
    present = [str(p) for p in ordered if p]
    return ":".join(present) if present else "N/A"
