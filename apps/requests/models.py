from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class BookRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    listing = models.ForeignKey("listings.Listing", related_name="requests", on_delete=models.CASCADE)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="sent_requests", on_delete=models.CASCADE)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["listing"]),
            models.Index(fields=["requester"]),
        ]

    def __str__(self):
        return f"Request #{self.pk} for listing {self.listing_id} by {self.requester_id}"

    def clean(self):
        if self.listing_id and self.requester_id and self.listing.owner_id == self.requester_id:
            raise ValidationError("You cannot request your own listing.")
