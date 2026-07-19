import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


class TestAdminReportViewSet:
    def test_list_requires_capability(self, auth_client, report_factory):
        client, user = auth_client(username="norep")
        response = client.get(reverse("admin-report-list"))
        assert response.status_code == 403

    def test_list_success(self, auth_client, admin_role_factory, report_factory):
        role = admin_role_factory(capabilities=["reports.view"])
        client, user = auth_client(admin_role=role)
        report_factory.create_batch(2)
        response = client.get(reverse("admin-report-list"))
        assert response.status_code == 200
        assert len(response.data["results"]) == 2

    def test_resolve_requires_capability(self, auth_client, admin_role_factory, report_factory):
        role = admin_role_factory(capabilities=["reports.view"])  # no reports.resolve
        client, user = auth_client(admin_role=role)
        report = report_factory()
        response = client.post(reverse("admin-report-resolve", args=[report.id]))
        assert response.status_code == 403

    def test_resolve_success_notifies_reporter(self, auth_client, admin_role_factory, report_factory, mailoutbox):
        role = admin_role_factory(capabilities=["reports.resolve"])
        client, user = auth_client(admin_role=role)
        report = report_factory()
        response = client.post(reverse("admin-report-resolve", args=[report.id]))
        assert response.status_code == 200
        assert response.data["status"] == "resolved"
        assert len(mailoutbox) == 1  # the reporter was notified

    def test_dismiss_success(self, auth_client, admin_role_factory, report_factory):
        role = admin_role_factory(capabilities=["reports.resolve"])
        client, user = auth_client(admin_role=role)
        report = report_factory()
        response = client.post(reverse("admin-report-dismiss", args=[report.id]))
        assert response.status_code == 200
        assert response.data["status"] == "dismissed"


class TestAdminAuditLogViewSet:
    def test_requires_capability(self, auth_client, audit_log_factory):
        client, user = auth_client(username="noaudit")
        response = client.get(reverse("admin-auditlog-list"))
        assert response.status_code == 403

    def test_list_success(self, auth_client, admin_role_factory, audit_log_factory):
        role = admin_role_factory(capabilities=["auditlog.view"])
        client, user = auth_client(admin_role=role)
        audit_log_factory.create_batch(3)
        response = client.get(reverse("admin-auditlog-list"))
        assert response.status_code == 200
        assert len(response.data["results"]) == 3
