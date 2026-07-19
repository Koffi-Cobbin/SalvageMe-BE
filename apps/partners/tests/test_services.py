import pytest
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.partners import services
from apps.partners.models import PartnerApplication

pytestmark = pytest.mark.django_db


class TestSubmitPartnerApplication:
    def test_authenticated_submission_links_existing_user_and_verifies_immediately(self, user_factory):
        user = user_factory(username="already", email="already@example.com")
        application = services.submit_partner_application(
            requesting_user=user, applicant_name="Ignored", applicant_email="ignored@example.com"
        )
        assert application.applicant_user_id == user.id
        assert application.applicant_email == user.email  # server overwrites, not client-supplied
        assert application.email_verified_at is not None

    def test_unauthenticated_submission_creates_new_account(self, mailoutbox):
        assert not User.objects.filter(email="newperson@example.com").exists()
        application = services.submit_partner_application(
            requesting_user=None, applicant_name="New Person", applicant_email="newperson@example.com"
        )
        assert application.applicant_user is not None
        user = application.applicant_user
        assert user.email == "newperson@example.com"
        assert user.has_usable_password() is False
        assert application.email_verified_at is None  # not verified yet
        assert len(mailoutbox) == 1  # invite email sent

    def test_unauthenticated_submission_matches_existing_unverified_account(self, user_factory):
        existing = user_factory(email="existing@example.com", is_verified=False)
        application = services.submit_partner_application(
            requesting_user=None, applicant_name="X", applicant_email="existing@example.com"
        )
        assert application.applicant_user_id == existing.id
        assert application.email_verified_at is None

    def test_unauthenticated_submission_matches_existing_verified_account(self, user_factory):
        existing = user_factory(email="verified@example.com", is_verified=True)
        application = services.submit_partner_application(
            requesting_user=None, applicant_name="X", applicant_email="verified@example.com"
        )
        assert application.applicant_user_id == existing.id
        assert application.email_verified_at is not None

    def test_duplicate_pending_application_rejected(self, user_factory):
        user = user_factory(email="dup@example.com")
        services.submit_partner_application(requesting_user=user, applicant_name="X", applicant_email="dup@example.com")
        with pytest.raises(ValidationError):
            services.submit_partner_application(requesting_user=user, applicant_name="X", applicant_email="dup@example.com")

    def test_verified_submission_notifies_reviewers_immediately(self, user_factory, admin_role_factory, mailoutbox):
        reviewer_role = admin_role_factory(capabilities=["partner_applications.review"])
        user_factory(admin_role=reviewer_role)  # a reviewer exists
        applicant = user_factory(email="app@example.com")

        services.submit_partner_application(requesting_user=applicant, applicant_name="X", applicant_email="app@example.com")

        assert len(mailoutbox) == 1
        assert "New partner application" in mailoutbox[0].subject


class TestCompleteEmailVerificationIfPending:
    def test_verifies_and_notifies_reviewers(self, user_factory, admin_role_factory, mailoutbox):
        reviewer_role = admin_role_factory(capabilities=["partner_applications.review"])
        user_factory(admin_role=reviewer_role)

        applicant_user = user_factory(email="pending@example.com", is_verified=False)
        application = services.submit_partner_application(
            requesting_user=None, applicant_name="X", applicant_email="pending@example.com"
        )
        # first was matched to applicant_user since email matched (unverified path)
        assert application.applicant_user_id == applicant_user.id
        assert application.email_verified_at is None

        services.complete_email_verification_if_pending(applicant_user)

        application.refresh_from_db()
        assert application.email_verified_at is not None
        assert len(mailoutbox) == 2  # invite email + reviewer notification

    def test_noop_when_no_pending_application(self, user_factory):
        user = user_factory()
        services.complete_email_verification_if_pending(user)  # should not raise


class TestApprovePartnerApplication:
    def test_requires_verified_email(self, partner_application_factory, admin_role_factory, user_factory):
        application = partner_application_factory(email_verified_at=None)
        role = admin_role_factory()
        acting = user_factory()
        with pytest.raises(ValidationError):
            services.approve_partner_application(application=application, acting_user=acting, admin_role=role)

    def test_success_grants_role(self, partner_application_factory, admin_role_factory, user_factory):
        from django.utils import timezone

        application = partner_application_factory(email_verified_at=timezone.now())
        role = admin_role_factory(capabilities=["listings.view"])
        acting = user_factory()

        result = services.approve_partner_application(application=application, acting_user=acting, admin_role=role)

        assert result.status == PartnerApplication.Status.APPROVED
        application.applicant_user.refresh_from_db()
        assert application.applicant_user.admin_role_id == role.id

    def test_success_creates_dropoff_point_when_proposed(self, partner_application_factory, admin_role_factory, user_factory):
        from django.contrib.gis.geos import Point
        from django.utils import timezone

        application = partner_application_factory(
            email_verified_at=timezone.now(),
            proposed_dropoff_name="Community Hub",
            proposed_dropoff_address="1 Main St",
            proposed_location=Point(-0.1, 51.5, srid=4326),
        )
        role = admin_role_factory()
        acting = user_factory()

        result = services.approve_partner_application(application=application, acting_user=acting, admin_role=role)

        assert result.created_dropoff_point is not None
        assert application.applicant_user in result.created_dropoff_point.managers.all()

    def test_already_reviewed_rejected(self, partner_application_factory, admin_role_factory, user_factory):
        from django.utils import timezone

        application = partner_application_factory(
            email_verified_at=timezone.now(), status=PartnerApplication.Status.APPROVED
        )
        role = admin_role_factory()
        acting = user_factory()
        with pytest.raises(ValidationError):
            services.approve_partner_application(application=application, acting_user=acting, admin_role=role)


class TestRejectPartnerApplication:
    def test_success_leaves_account_untouched(self, partner_application_factory, user_factory):
        applicant = user_factory()
        application = partner_application_factory(applicant_user=applicant)
        acting = user_factory()

        result = services.reject_partner_application(application=application, acting_user=acting, reason="Not a fit")

        assert result.status == PartnerApplication.Status.REJECTED
        applicant.refresh_from_db()
        assert applicant.admin_role is None
        assert applicant.is_active is True  # fully normal account, untouched
