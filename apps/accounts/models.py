from django.contrib.auth.models import AbstractUser
from django.contrib.gis.db import models as gis_models
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from common.admin_capabilities import is_valid_capability
from common.mixins import TimestampedModel


class AdminRole(models.Model):
    """
    A named, admin-creatable bundle of capabilities — see
    docs/ADMIN_API_PLAN.md for the full design. Capabilities themselves are
    a fixed vocabulary defined in code (common/admin_capabilities.py); which
    capabilities belong to a given role is data, editable at runtime.
    """

    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    capabilities = models.JSONField(default=list, blank=True)
    # True only for the single built-in role seeded by migration — see
    # docs/ADMIN_API_PLAN.md "Seeding: the one built-in role". Its
    # capabilities can't be edited and it can't be deleted, guaranteeing the
    # system can never be edited into a state where nobody can manage roles.
    is_protected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        invalid = [c for c in self.capabilities if not is_valid_capability(c)]
        if invalid:
            raise ValidationError({"capabilities": f"Unknown capability code(s): {invalid}"})


class User(AbstractUser):
    class Role(models.TextChoices):
        DONOR = "donor", "Donor"
        RECIPIENT = "recipient", "Recipient"
        BOTH = "both", "Both"

    # Coordinator/admin capability is handled via admin_role below, not this
    # field — this "role" describes how someone uses the exchange
    # marketplace, not their platform privileges. Kept deliberately separate
    # from admin_role, which is an unrelated concept.
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.BOTH)
    phone = models.CharField(max_length=32, null=True, blank=True)
    location = gis_models.PointField(null=True, blank=True, geography=True, srid=4326)
    is_verified = models.BooleanField(default=False)
    # Opt-out (default True — see docs/LEADERBOARD_PLAN.md "Privacy"). A
    # user can toggle this themselves via PATCH /users/me/; staff can also
    # set it on someone else's behalf via PATCH /admin/users/{id}/
    # (gated by the existing users.edit capability — no new capability
    # needed just to exclude someone from a public list).
    include_in_leaderboard = models.BooleanField(default=True)

    # Null = no admin access at all. See docs/ADMIN_API_PLAN.md.
    admin_role = models.ForeignKey(
        AdminRole, null=True, blank=True, on_delete=models.PROTECT, related_name="users"
    )

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

    def has_capability(self, capability: str) -> bool:
        return bool(self.admin_role and capability in self.admin_role.capabilities)


def role_ids_with_capability(capability: str) -> list[int]:
    """
    Returns AdminRole ids whose capabilities include the given one.

    Deliberately filters in Python rather than using
    AdminRole.objects.filter(capabilities__contains=[capability]) — that
    JSONField lookup isn't supported on SQLite (only Postgres/MariaDB), and
    this project runs on both SQLite (local dev, via SpatiaLite) and
    Postgres (staging/prod) with parity expected between them. The number
    of AdminRole rows is small (a handful of named roles, not one per
    user), so doing this in Python is cheap and keeps behavior identical
    across both backends rather than depending on a backend-specific
    feature.
    """
    return [role.id for role in AdminRole.objects.all() if capability in role.capabilities]


def users_with_capability(capability: str):
    """QuerySet of every User currently holding a role with this capability."""
    return User.objects.filter(admin_role_id__in=role_ids_with_capability(capability))


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


class FeaturedDonor(TimestampedModel):
    """
    Editorial "Donor of the Month"-style spotlight — a human pick,
    distinct from the algorithmic ranking in leaderboard_services.py. See
    docs/LEADERBOARD_PLAN.md "Admin tie-in: featuring/excluding".
    """

    user = models.ForeignKey(User, related_name="featured_donor_entries", on_delete=models.CASCADE)
    blurb = models.TextField(blank=True)
    featured_from = models.DateTimeField()
    featured_until = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-featured_from"]
        indexes = [models.Index(fields=["featured_from", "featured_until"])]

    def __str__(self):
        return f"Featured: {self.user.username} ({self.featured_from.date()})"

    def is_active(self, at=None) -> bool:
        from django.utils import timezone

        at = at or timezone.now()
        if at < self.featured_from:
            return False
        if self.featured_until is not None and at > self.featured_until:
            return False
        return True
