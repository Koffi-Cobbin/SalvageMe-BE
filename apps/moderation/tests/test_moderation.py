import pytest
from django.urls import reverse
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.moderation import services
from apps.moderation.models import Report

pytestmark = pytest.mark.django_db


class TestCreateReportAPI:
    def test_requires_auth(self, api_client):
        response = api_client.post(reverse("report-list"), {"target_type": "listing", "target_id": 1, "reason": "spam"})
        assert response.status_code == 401

    def test_success(self, auth_client):
        client, _ = auth_client(username="reporter1")
        response = client.post(reverse("report-list"), {"target_type": "listing", "target_id": 1, "reason": "spam"})
        assert response.status_code == 201
        assert response.data["status"] == "open"

    def test_duplicate_open_report_rejected(self, auth_client):
        client, user = auth_client(username="reporter2")
        services.create_report(reporter=user, target_type="listing", target_id=5, reason=Report.Reason.SPAM)
        response = client.post(reverse("report-list"), {"target_type": "listing", "target_id": 5, "reason": "spam"})
        assert response.status_code == 400


class TestResolveReport:
    def test_only_staff_can_resolve(self, report_factory, user_factory):
        report = report_factory()
        non_staff = user_factory(username="nonstaff", is_staff=False)
        with pytest.raises(PermissionDenied):
            services.resolve_report(report=report, acting_user=non_staff, outcome=Report.Status.RESOLVED)

    def test_staff_can_resolve_and_audit_log_written(self, report_factory, user_factory):
        report = report_factory()
        staff = user_factory(username="staffuser", is_staff=True)
        result = services.resolve_report(report=report, acting_user=staff, outcome=Report.Status.RESOLVED)
        assert result.status == Report.Status.RESOLVED
        assert result.resolved_by == staff

        from apps.moderation.models import AuditLog

        assert AuditLog.objects.filter(action="report_resolved", target_id=report.id).exists()

    def test_cannot_resolve_already_resolved_report(self, report_factory, user_factory):
        report = report_factory()
        staff = user_factory(username="staffuser2", is_staff=True)
        services.resolve_report(report=report, acting_user=staff, outcome=Report.Status.RESOLVED)
        with pytest.raises(ValidationError):
            services.resolve_report(report=report, acting_user=staff, outcome=Report.Status.DISMISSED)
