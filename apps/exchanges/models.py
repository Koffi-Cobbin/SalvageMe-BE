from django.conf import settings
from django.db import models


class Exchange(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No show"

    listing = models.ForeignKey("listings.Listing", related_name="exchanges", on_delete=models.CASCADE)
    donor = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="donor_exchanges", on_delete=models.CASCADE)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="recipient_exchanges", on_delete=models.CASCADE
    )
    dropoff_point = models.ForeignKey(
        "dropoff.DropOffPoint", null=True, blank=True, on_delete=models.SET_NULL, related_name="exchanges"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["donor"]),
            models.Index(fields=["recipient"]),
            models.Index(fields=["scheduled_at"]),
        ]

    def __str__(self):
        return f"Exchange #{self.pk} ({self.status})"

    def is_party(self, user) -> bool:
        return user.id in (self.donor_id, self.recipient_id)
