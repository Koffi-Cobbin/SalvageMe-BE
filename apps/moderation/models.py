from django.conf import settings
from django.db import models


class Report(models.Model):
    class TargetType(models.TextChoices):
        LISTING = "listing", "Listing"
        USER = "user", "User"

    class Reason(models.TextChoices):
        SPAM = "spam", "Spam"
        INAPPROPRIATE = "inappropriate", "Inappropriate"
        MISREPRESENTED = "misrepresented", "Misrepresented"
        NO_SHOW = "no_show", "No show"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    target_type = models.CharField(max_length=16, choices=TargetType.choices)
    target_id = models.PositiveIntegerField()
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="reports_filed", on_delete=models.CASCADE)
    reason = models.CharField(max_length=32, choices=Reason.choices)
    detail = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports_resolved"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["reason"]),
            models.Index(fields=["target_type", "target_id"]),
        ]
        constraints = [
            # One OPEN report per reporter per target — a reasonable
            # dedup rule so one user can't spam-flag the same target
            # repeatedly (documented per BUSINESS LOGIC RULES). Resolved/
            # dismissed reports don't block a fresh report if the issue
            # recurs later.
            models.UniqueConstraint(
                fields=["reporter", "target_type", "target_id"],
                condition=models.Q(status="open"),
                name="one_open_report_per_reporter_per_target",
            )
        ]

    def __str__(self):
        return f"Report #{self.pk}: {self.target_type}#{self.target_id} ({self.reason})"


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="audit_actions")
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=32)
    target_id = models.PositiveIntegerField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self):
        return f"{self.action} on {self.target_type}#{self.target_id} by {self.actor_id}"
