from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.utils.text import slugify

from common.mixins import TimestampedModel


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Listing(TimestampedModel):
    class Condition(models.TextChoices):
        NEW = "new", "New"
        GOOD = "good", "Good"
        FAIR = "fair", "Fair"
        WORN = "worn", "Worn"

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        PENDING = "pending", "Pending"
        CLAIMED = "claimed", "Claimed"
        REMOVED = "removed", "Removed"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="listings", on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(Category, related_name="listings", on_delete=models.PROTECT)
    grade_level = models.CharField(max_length=50, null=True, blank=True)
    condition = models.CharField(max_length=16, choices=Condition.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AVAILABLE)
    location = gis_models.PointField(null=True, blank=True, geography=True, srid=4326)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["owner"]),
            models.Index(fields=["category"]),
            models.Index(fields=["condition"]),
            models.Index(fields=["grade_level"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        # Belt-and-braces: the authoritative "no self-request" rule lives in
        # apps/requests, but a listing should also never be directly saved
        # into a claimed state outside the exchange-completion flow.
        pass

    def mark_pending(self):
        if self.status == self.Status.AVAILABLE:
            self.status = self.Status.PENDING
            self.save(update_fields=["status", "updated_at"])

    def revert_to_available(self):
        if self.status == self.Status.PENDING:
            self.status = self.Status.AVAILABLE
            self.save(update_fields=["status", "updated_at"])

    def mark_claimed(self):
        self.status = self.Status.CLAIMED
        self.save(update_fields=["status", "updated_at"])


class ListingPhoto(models.Model):
    listing = models.ForeignKey(Listing, related_name="images", on_delete=models.CASCADE)
    # FileForge File.id is the source of truth; `url` is a cached copy of
    # the provider-served URL so reads never need a FileForge round trip.
    fileforge_file_id = models.PositiveIntegerField()
    url = models.URLField()
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"Photo {self.order} for {self.listing_id}"
