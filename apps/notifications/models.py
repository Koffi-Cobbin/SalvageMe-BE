from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Category(models.TextChoices):
        REQUEST_RECEIVED = "request_received", "New request received"
        REQUEST_ACCEPTED = "request_accepted", "Request accepted"
        REQUEST_DECLINED = "request_declined", "Request declined"
        EXCHANGE_SCHEDULED = "exchange_scheduled", "Exchange scheduled"
        EXCHANGE_COMPLETED = "exchange_completed", "Exchange completed"
        EXCHANGE_REMINDER = "exchange_reminder", "Exchange reminder"
        REPORT_RESOLVED = "report_resolved", "Your report was resolved"
        PARTNER_APPLICATION_READY = "partner_application_ready", "Application ready for review"
        PARTNER_APPLICATION_APPROVED = "partner_application_approved", "Application approved"
        PARTNER_APPLICATION_REJECTED = "partner_application_rejected", "Application rejected"
        ROLE_ASSIGNED = "role_assigned", "Your admin role changed"
        SYSTEM = "system", "System notification"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="notifications", on_delete=models.CASCADE
    )
    category = models.CharField(max_length=32, choices=Category.choices)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    # Same target_type/target_id pattern already used by Report and AuditLog
    # elsewhere in this codebase — reused, not a new convention.
    target_type = models.CharField(max_length=32, blank=True)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read"])]

    def __str__(self):
        return f"{self.category} -> {self.recipient_id}"

    def mark_read(self):
        if not self.is_read:
            from django.utils import timezone

            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])
