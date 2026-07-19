"""
Service-layer functions for the partner application flow — see
docs/PARTNER_APPLICATION_PLAN.md for the full design. Account creation
happens at submission time, not approval, so a rejected applicant keeps a
fully normal, usable account.
"""
from __future__ import annotations

import re

from django.contrib.gis.geos import Point
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import AdminRole, User
from apps.accounts.views import generate_password_set_link
from apps.dropoff.models import DropOffPoint
from apps.moderation.services import record_audit_log
from apps.notifications.services import (
    notify_partner_application_approved,
    notify_partner_application_ready,
    notify_partner_application_rejected,
)

from .models import PartnerApplication


def _generate_username(email: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]", "", email.split("@")[0]) or "partner"
    username = base
    suffix = 1
    while User.objects.filter(username=username).exists():
        suffix += 1
        username = f"{base}{suffix}"
    return username


def _send_invite_email(user: User) -> None:
    from django.conf import settings

    uid, token = generate_password_set_link(user)
    # The actual frontend URL isn't known to the backend — this is a
    # placeholder body; wire in the real frontend base URL when deploying.
    send_mail(
        subject="Verify your email and set your password",
        message=(
            f"Thanks for applying to SalvageMe. Confirm your email and set a password using "
            f"this link: /set-password?uid={uid}&token={token}"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


def submit_partner_application(
    *,
    requesting_user: User | None,
    applicant_name: str,
    applicant_email: str,
    applicant_phone: str = "",
    organization_name: str = "",
    message: str = "",
    proposed_dropoff_name: str = "",
    proposed_dropoff_address: str = "",
    proposed_latitude: float | None = None,
    proposed_longitude: float | None = None,
) -> PartnerApplication:
    existing_pending = PartnerApplication.objects.filter(
        applicant_email__iexact=applicant_email, status=PartnerApplication.Status.PENDING
    ).exists()
    if existing_pending:
        raise ValidationError(
            {"detail": "You already have a pending application.", "code": "duplicate_application"}
        )

    email_verified_at = None

    if requesting_user is not None and requesting_user.is_authenticated:
        applicant_user = requesting_user
        applicant_name = requesting_user.get_full_name() or requesting_user.username
        applicant_email = requesting_user.email
        applicant_phone = requesting_user.phone or ""
        email_verified_at = timezone.now()
    else:
        applicant_user = User.objects.filter(email__iexact=applicant_email).first()
        if applicant_user is not None:
            if applicant_user.is_verified:
                email_verified_at = timezone.now()
        else:
            applicant_user = User(username=_generate_username(applicant_email), email=applicant_email)
            applicant_user.set_unusable_password()
            applicant_user.save()

    location = None
    if proposed_latitude is not None and proposed_longitude is not None:
        location = Point(proposed_longitude, proposed_latitude, srid=4326)

    try:
        with transaction.atomic():
            application = PartnerApplication.objects.create(
                applicant_name=applicant_name,
                applicant_email=applicant_email,
                applicant_phone=applicant_phone,
                applicant_user=applicant_user,
                organization_name=organization_name,
                message=message,
                proposed_dropoff_name=proposed_dropoff_name,
                proposed_dropoff_address=proposed_dropoff_address,
                proposed_location=location,
                email_verified_at=email_verified_at,
            )
    except IntegrityError as exc:
        raise ValidationError(
            {"detail": "You already have a pending application.", "code": "duplicate_application"}
        ) from exc

    if email_verified_at is not None:
        notify_partner_application_ready(application)
        application.reviewers_notified_at = timezone.now()
        application.save(update_fields=["reviewers_notified_at"])
    else:
        _send_invite_email(applicant_user)

    return application


def complete_email_verification_if_pending(user: User) -> None:
    """
    Called from apps/accounts/views.py::SetPasswordView after a successful
    password set. If this user has a pending, not-yet-verified partner
    application, finish its verification step and notify reviewers.
    """
    application = (
        PartnerApplication.objects.filter(
            applicant_user=user, status=PartnerApplication.Status.PENDING, email_verified_at__isnull=True
        )
        .order_by("-created_at")
        .first()
    )
    if application is None:
        return

    application.email_verified_at = timezone.now()
    application.save(update_fields=["email_verified_at"])
    notify_partner_application_ready(application)
    application.reviewers_notified_at = timezone.now()
    application.save(update_fields=["reviewers_notified_at"])


def approve_partner_application(
    *, application: PartnerApplication, acting_user: User, admin_role: AdminRole, assign_dropoff_manager: bool = True
) -> PartnerApplication:
    from apps.accounts import admin_services

    if application.email_verified_at is None:
        raise ValidationError({"detail": "This application's email is not verified yet.", "code": "email_not_verified"})
    if application.status != PartnerApplication.Status.PENDING:
        raise ValidationError({"detail": f"Application is already {application.status}.", "code": "already_reviewed"})

    admin_services.assign_admin_role(user=application.applicant_user, new_role=admin_role, acting_user=acting_user)

    created_dropoff_point = None
    if assign_dropoff_manager and application.proposed_dropoff_name and application.proposed_location:
        created_dropoff_point = DropOffPoint.objects.create(
            name=application.proposed_dropoff_name,
            address=application.proposed_dropoff_address,
            location=application.proposed_location,
        )
        created_dropoff_point.managers.add(application.applicant_user)

    application.status = PartnerApplication.Status.APPROVED
    application.granted_role = admin_role
    application.created_dropoff_point = created_dropoff_point
    application.reviewed_by = acting_user
    application.reviewed_at = timezone.now()
    application.save(
        update_fields=["status", "granted_role", "created_dropoff_point", "reviewed_by", "reviewed_at"]
    )

    record_audit_log(
        actor=acting_user, action="partner_application_approved", target_type="partner_application",
        target_id=application.id,
        metadata={"granted_role_id": admin_role.id, "dropoff_point_id": created_dropoff_point.id if created_dropoff_point else None},
    )
    notify_partner_application_approved(application)
    return application


def reject_partner_application(*, application: PartnerApplication, acting_user: User, reason: str) -> PartnerApplication:
    if application.status != PartnerApplication.Status.PENDING:
        raise ValidationError({"detail": f"Application is already {application.status}.", "code": "already_reviewed"})

    application.status = PartnerApplication.Status.REJECTED
    application.rejection_reason = reason
    application.reviewed_by = acting_user
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at"])

    record_audit_log(
        actor=acting_user, action="partner_application_rejected", target_type="partner_application",
        target_id=application.id, metadata={"reason": reason},
    )
    notify_partner_application_rejected(application)
    return application
