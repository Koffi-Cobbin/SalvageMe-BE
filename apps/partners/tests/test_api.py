import pytest
from django.urls import reverse

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


class TestSubmitEndpoint:
    def test_unauthenticated_success(self, api_client):
        response = api_client.post(
            reverse("partner-application-submit"),
            {"applicant_name": "New Partner", "applicant_email": "newpartner@example.com"},
        )
        assert response.status_code == 201
        assert response.data["status"] == "pending"
        assert User.objects.filter(email="newpartner@example.com").exists()

    def test_unauthenticated_missing_required_fields_rejected(self, api_client):
        response = api_client.post(reverse("partner-application-submit"), {})
        assert response.status_code == 400

    def test_authenticated_success_uses_own_identity(self, auth_client):
        client, user = auth_client(username="selfapply", email="selfapply@example.com")
        response = client.post(
            reverse("partner-application-submit"),
            {"applicant_name": "Someone Else", "applicant_email": "spoofed@example.com"},
        )
        assert response.status_code == 201
        assert response.data["applicant_email"] == "selfapply@example.com"  # server overwrote it


class TestSetPasswordEndpoint:
    def test_invalid_token_rejected(self, api_client, user_factory):
        user_factory()  # exists but not referenced — this test only needs an invalid token to be rejected
        response = api_client.post(
            reverse("auth-set-password"), {"uid": "bad", "token": "bad", "new_password": "NewPass123!"}
        )
        assert response.status_code == 400

    def test_valid_token_sets_password_and_verifies(self, api_client, user_factory):
        from apps.accounts.views import generate_password_set_link

        user = user_factory()
        user.set_unusable_password()
        user.save()
        uid, token = generate_password_set_link(user)

        response = api_client.post(
            reverse("auth-set-password"), {"uid": uid, "token": token, "new_password": "NewSecurePass123!"}
        )
        assert response.status_code == 204
        user.refresh_from_db()
        assert user.check_password("NewSecurePass123!")
        assert user.is_verified is True

    def test_completes_pending_partner_application_verification(self, api_client, mocker):
        from apps.accounts.views import generate_password_set_link
        from apps.partners import services

        application = services.submit_partner_application(
            requesting_user=None, applicant_name="X", applicant_email="setpw@example.com"
        )
        user = application.applicant_user
        uid, token = generate_password_set_link(user)

        api_client.post(reverse("auth-set-password"), {"uid": uid, "token": token, "new_password": "NewSecurePass123!"})

        application.refresh_from_db()
        assert application.email_verified_at is not None


class TestAdminReviewEndpoints:
    def test_list_requires_capability(self, auth_client, partner_application_factory):
        client, user = auth_client(username="norev")
        response = client.get(reverse("admin-partner-application-list"))
        assert response.status_code == 403

    def test_list_success(self, auth_client, admin_role_factory, partner_application_factory):
        role = admin_role_factory(capabilities=["partner_applications.review"])
        client, user = auth_client(admin_role=role)
        partner_application_factory.create_batch(2)
        response = client.get(reverse("admin-partner-application-list"))
        assert len(response.data["results"]) == 2

    def test_approve_requires_capability(self, auth_client, admin_role_factory, partner_application_factory):
        admin_role_factory(capabilities=["partner_applications.review"])  # not actually assigned to the acting user in this test
        target_role = admin_role_factory(capabilities=["listings.view"])
        from django.utils import timezone

        application = partner_application_factory(email_verified_at=timezone.now())
        client, user = auth_client(username="noreview")
        response = client.post(
            reverse("admin-partner-application-approve", args=[application.id]), {"admin_role_id": target_role.id}
        )
        assert response.status_code == 403

    def test_approve_success(self, auth_client, admin_role_factory, partner_application_factory):
        from django.utils import timezone

        reviewer_role = admin_role_factory(capabilities=["partner_applications.review"])
        target_role = admin_role_factory(capabilities=["listings.view"])
        client, user = auth_client(admin_role=reviewer_role)
        application = partner_application_factory(email_verified_at=timezone.now())

        response = client.post(
            reverse("admin-partner-application-approve", args=[application.id]), {"admin_role_id": target_role.id}
        )
        assert response.status_code == 200
        assert response.data["status"] == "approved"

    def test_approve_unverified_rejected(self, auth_client, admin_role_factory, partner_application_factory):
        reviewer_role = admin_role_factory(capabilities=["partner_applications.review"])
        target_role = admin_role_factory()
        client, user = auth_client(admin_role=reviewer_role)
        application = partner_application_factory(email_verified_at=None)

        response = client.post(
            reverse("admin-partner-application-approve", args=[application.id]), {"admin_role_id": target_role.id}
        )
        assert response.status_code == 400

    def test_reject_success_leaves_account_active(self, auth_client, admin_role_factory, partner_application_factory):
        reviewer_role = admin_role_factory(capabilities=["partner_applications.review"])
        client, user = auth_client(admin_role=reviewer_role)
        application = partner_application_factory()

        response = client.post(
            reverse("admin-partner-application-reject", args=[application.id]), {"reason": "Not needed right now"}
        )
        assert response.status_code == 200
        assert response.data["status"] == "rejected"
        application.applicant_user.refresh_from_db()
        assert application.applicant_user.is_active is True
