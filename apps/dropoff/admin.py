from django.contrib.gis.admin import GISModelAdmin
from django.contrib import admin

from .models import DropOffPoint


@admin.register(DropOffPoint)
class DropOffPointAdmin(GISModelAdmin):
    list_display = ["name", "address", "coordinator"]
    search_fields = ["name", "address"]
