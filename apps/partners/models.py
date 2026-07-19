from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models


class PartnerApplication(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    # Always stored as submitted, even for an authenticated applicant — the
    # application is a stable historical record independent of later
    # profile edits.
    applicant_name = models.CharField(max_length=200)
    applicant_email = models.EmailField()
    applicant_phone = models.CharField(max_length=32, blank=True)

    # Always set at creation time — either the already-authenticated
    # requester, an existing account matched by email, or a brand-new
    # account created for this submission. See apps/partners/services.py.
    applicant_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="partner_applications"
    )

    organization_name = models.CharField(max_length=200, blank=True)
    message = models.TextField(blank=True)

    # Optional — present only if they're also offering a physical location.
    proposed_dropoff_name = models.CharField(max_length=200, blank=True)
    proposed_dropoff_address = models.CharField(max_length=300, blank=True)
    proposed_location = gis_models.PointField(null=True, blank=True, geography=True, srid=4326)

    email_verified_at = models.DateTimeField(null=True, blank=True)
    reviewers_notified_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    granted_role = models.ForeignKey(
        "accounts.AdminRole", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_dropoff_point = models.ForeignKey(
        "dropoff.DropOffPoint", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["applicant_email"],
                condition=models.Q(status="pending"),
                name="one_pending_application_per_email",
            )
        ]

    def __str__(self):
        return f"PartnerApplication #{self.pk} ({self.applicant_name}, {self.status})"
