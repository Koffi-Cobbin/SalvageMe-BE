from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models


class DropOffPoint(models.Model):
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    coordinator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="coordinated_dropoffs"
    )
    location = gis_models.PointField(null=True, blank=True, geography=True, srid=4326)
    # Users with the scoped `dropoff.manage` capability (as opposed to the
    # unscoped `dropoff.manage_all`) can only see/edit points they're
    # assigned to here — see docs/ADMIN_API_PLAN.md "Drop-off scoping".
    managers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="managed_dropoff_points"
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
