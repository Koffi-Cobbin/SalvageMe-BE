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

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
