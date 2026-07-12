from django.contrib.auth.models import AbstractUser
from django.contrib.gis.db import models as gis_models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from common.mixins import TimestampedModel


class User(AbstractUser):
    class Role(models.TextChoices):
        DONOR = "donor", "Donor"
        RECIPIENT = "recipient", "Recipient"
        BOTH = "both", "Both"

    # Coordinator/admin capability is handled via is_staff/groups, not a
    # role choice — a "role" here describes how someone uses the exchange
    # marketplace, not their platform privileges.
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.BOTH)
    phone = models.CharField(max_length=32, null=True, blank=True)
    location = gis_models.PointField(null=True, blank=True, geography=True, srid=4326)
    is_verified = models.BooleanField(default=False)

    # FileForge is the storage boundary for avatars — we only ever persist
    # the returned file reference, never bytes.
    avatar_file_id = models.PositiveIntegerField(null=True, blank=True)
    avatar_url = models.URLField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["is_verified"]),
        ]

    def __str__(self):
        return self.username


class UserRating(TimestampedModel):
    rated_user = models.ForeignKey(User, related_name="ratings_received", on_delete=models.CASCADE)
    rated_by = models.ForeignKey(User, related_name="ratings_given", on_delete=models.CASCADE)
    exchange = models.ForeignKey("exchanges.Exchange", related_name="ratings", on_delete=models.CASCADE)
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["exchange", "rated_by"],
                name="one_rating_per_rater_per_exchange",
            )
        ]
        indexes = [models.Index(fields=["rated_user"])]

    def __str__(self):
        return f"{self.rated_by} -> {self.rated_user} ({self.score}) on exchange {self.exchange_id}"
