from django.contrib import admin

from .models import ImpactStatsSnapshot


@admin.register(ImpactStatsSnapshot)
class ImpactStatsSnapshotAdmin(admin.ModelAdmin):
    list_display = ["computed_at", "total_listings", "total_exchanges_completed"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
