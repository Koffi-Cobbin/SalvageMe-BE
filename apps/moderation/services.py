from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.notifications.services import notify_report_resolved

from .models import AuditLog, Report


def record_audit_log(*, actor, action: str, target_type: str, target_id: int, metadata: dict | None = None) -> AuditLog:
    """
    Every moderation action (report resolution, listing removal, user
    suspension) must go through this so nothing happens silently — see
    BUSINESS LOGIC RULES.
    """
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata or {},
    )


def create_report(*, reporter, target_type: str, target_id: int, reason: str, detail: str = "") -> Report:
    try:
        with transaction.atomic():
            return Report.objects.create(
                reporter=reporter, target_type=target_type, target_id=target_id, reason=reason, detail=detail
            )
    except IntegrityError as exc:
        raise ValidationError(
            {
                "detail": "You already have an open report for this target.",
                "code": "duplicate_report",
            }
        ) from exc


def resolve_report(*, report: Report, acting_user, outcome: str) -> Report:
    has_legacy_staff_access = acting_user.is_staff
    has_capability = acting_user.has_capability("reports.resolve") if hasattr(acting_user, "has_capability") else False
    if not (has_legacy_staff_access or has_capability):
        raise PermissionDenied("Only staff/moderators can resolve reports.")

    if report.status != Report.Status.OPEN:
        raise ValidationError({"detail": f"Report is already {report.status}.", "code": "invalid_transition"})

    if outcome not in (Report.Status.RESOLVED, Report.Status.DISMISSED):
        raise ValidationError({"detail": "Invalid outcome.", "code": "invalid_outcome"})

    report.status = outcome
    report.resolved_by = acting_user
    report.resolved_at = timezone.now()
    report.save(update_fields=["status", "resolved_by", "resolved_at"])

    record_audit_log(
        actor=acting_user,
        action=f"report_{outcome}",
        target_type="report",
        target_id=report.id,
        metadata={"reported_target_type": report.target_type, "reported_target_id": report.target_id},
    )
    notify_report_resolved(report)
    return report
