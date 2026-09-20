"""Unit tests for the transport-independent audit-log writer.

Runs against the real ``AuditLog`` model: the contract that matters is that a
GUI request and an MCP tool call produce structurally identical rows.
"""
import unittest

from django.contrib.auth.models import AnonymousUser, User

from deployments.models import AuditLog
from deployments.services.audit import build_target, record_audit


class TestRecordAudit(unittest.TestCase):
    def setUp(self):
        self.user = User.objects.create_user("audit_user")

    def test_writes_one_row_with_the_given_fields(self):
        record_audit(
            user=self.user,
            action=AuditLog.Action.MCP_TOOL_CALL,
            target="dev:web",
            details={"tool": "list_environments"},
            correlation_id="abc-123",
            duration_ms=12,
        )
        row = AuditLog.objects.get()
        self.assertEqual(row.user, self.user)
        self.assertEqual(row.action, "mcp_tool_call")
        self.assertEqual(row.target, "dev:web")
        self.assertEqual(row.details, {"tool": "list_environments"})
        self.assertEqual(row.correlation_id, "abc-123")
        self.assertEqual(row.duration_ms, 12)
        self.assertTrue(row.success)

    def test_anonymous_user_is_stored_as_null(self):
        record_audit(user=AnonymousUser(), action=AuditLog.Action.VIEW_BOM)
        self.assertIsNone(AuditLog.objects.get().user)

    def test_none_user_is_stored_as_null(self):
        record_audit(user=None, action=AuditLog.Action.VIEW_BOM)
        self.assertIsNone(AuditLog.objects.get().user)

    def test_user_agent_is_truncated_to_the_column_width(self):
        record_audit(
            user=self.user, action=AuditLog.Action.VIEW_BOM, user_agent="x" * 900
        )
        self.assertEqual(len(AuditLog.objects.get().user_agent), 500)

    def test_none_user_agent_becomes_empty_string(self):
        record_audit(user=self.user, action=AuditLog.Action.VIEW_BOM, user_agent=None)
        self.assertEqual(AuditLog.objects.get().user_agent, "")

    def test_details_defaults_to_empty_dict(self):
        record_audit(user=self.user, action=AuditLog.Action.VIEW_BOM)
        self.assertEqual(AuditLog.objects.get().details, {})

    def test_failure_is_recorded_with_its_message(self):
        record_audit(
            user=self.user,
            action=AuditLog.Action.MCP_TOOL_CALL,
            success=False,
            error_message="denied",
        )
        row = AuditLog.objects.get()
        self.assertFalse(row.success)
        self.assertEqual(row.error_message, "denied")

    def test_a_write_failure_is_swallowed_not_raised(self):
        # Auditing must never break the request it is recording.
        from unittest import mock

        with mock.patch.object(
            AuditLog.objects, "create", side_effect=RuntimeError("db is down")
        ):
            record_audit(user=self.user, action=AuditLog.Action.VIEW_BOM)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_correlation_id_and_target_default_without_violating_not_null(self):
        # Both are non-null CharFields; omitting them must still write a row.
        record_audit(user=self.user, action=AuditLog.Action.VIEW_BOM)
        row = AuditLog.objects.get()
        self.assertEqual(row.correlation_id, "")
        self.assertEqual(row.target, "N/A")


class TestBuildTarget(unittest.TestCase):
    def test_joins_in_the_documented_order(self):
        self.assertEqual(
            build_target(instance_name="web", environment="dev"), "dev:web"
        )

    def test_drops_absent_and_empty_parts(self):
        self.assertEqual(build_target(environment="dev", instance_name=""), "dev")

    def test_no_parts_yields_na(self):
        self.assertEqual(build_target(), "N/A")
        self.assertEqual(build_target(environment=None), "N/A")

    def test_includes_csd_id(self):
        self.assertEqual(build_target(environment="dev", csd_id="123"), "dev:123")


if __name__ == "__main__":
    unittest.main()
