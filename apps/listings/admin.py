from django.contrib.gis.admin import GISModelAdmin
from django.contrib import admin

from apps.moderation.services import record_audit_log

from .models import Category, Listing, ListingPhoto


class ListingPhotoInline(admin.TabularInline):
    model = ListingPhoto
    extra = 0
    fields = ["url", "fileforge_file_id", "order"]
    readonly_fields = ["url", "fileforge_file_id"]


@admin.register(Listing)
class ListingAdmin(GISModelAdmin):
    list_display = ["title", "owner", "status", "category", "condition", "created_at"]
    list_filter = ["status", "category", "condition"]
    search_fields = ["title", "owner__username"]
    inlines = [ListingPhotoInline]
    actions = ["remove_listings", "restore_listings"]

    @admin.action(description="Remove selected listings")
    def remove_listings(self, request, queryset):
        updated = queryset.update(status=Listing.Status.REMOVED)
        for listing in queryset:
            record_audit_log(
                actor=request.user,
                action="listing_removed",
                target_type="listing",
                target_id=listing.id,
            )
        self.message_user(request, f"Removed {updated} listing(s).")

    @admin.action(description="Restore selected listings to available")
    def restore_listings(self, request, queryset):
        updated = queryset.update(status=Listing.Status.AVAILABLE)
        for listing in queryset:
            record_audit_log(
                actor=request.user,
                action="listing_restored",
                target_type="listing",
                target_id=listing.id,
            )
        self.message_user(request, f"Restored {updated} listing(s).")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
