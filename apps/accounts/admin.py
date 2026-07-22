from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.gis.admin import GISModelAdmin

from common.admin_capabilities import ALL_CAPABILITIES

from apps.moderation.services import record_audit_log

from .models import AdminRole, FeaturedDonor, User, UserRating


class ListingInline(admin.TabularInline):
    from apps.listings.models import Listing

    model = Listing
    fk_name = "owner"
    extra = 0
    fields = ["title", "status", "created_at"]
    readonly_fields = ["title", "status", "created_at"]
    can_delete = False
    show_change_link = True


class ReportsFiledInline(admin.TabularInline):
    from apps.moderation.models import Report

    model = Report
    fk_name = "reporter"
    extra = 0
    fields = ["target_type", "target_id", "reason", "status", "created_at"]
    readonly_fields = fields
    can_delete = False
    show_change_link = True


@admin.register(User)
class UserAdmin(DjangoUserAdmin, GISModelAdmin):
    list_display = ["username", "email", "role", "is_verified", "is_staff", "is_active", "date_joined"]
    list_filter = ["is_verified", "role", "is_staff", "is_active"]
    search_fields = ["username", "email", "phone"]
    inlines = [ListingInline, ReportsFiledInline]
    actions = ["suspend_users", "reactivate_users"]

    fieldsets = DjangoUserAdmin.fieldsets + (
        ("SalvageMe profile", {"fields": ("role", "phone", "location", "is_verified", "avatar_url")}),
    )

    @admin.action(description="Suspend selected users")
    def suspend_users(self, request, queryset):
        updated = queryset.update(is_active=False)
        for user in queryset:
            record_audit_log(
                actor=request.user,
                action="user_suspended",
                target_type="user",
                target_id=user.id,
            )
        self.message_user(request, f"Suspended {updated} user(s).")

    @admin.action(description="Reactivate selected users")
    def reactivate_users(self, request, queryset):
        updated = queryset.update(is_active=True)
        for user in queryset:
            record_audit_log(
                actor=request.user,
                action="user_reactivated",
                target_type="user",
                target_id=user.id,
            )
        self.message_user(request, f"Reactivated {updated} user(s).")


@admin.register(UserRating)
class UserRatingAdmin(admin.ModelAdmin):
    list_display = ["rated_user", "rated_by", "exchange", "score", "created_at"]
    list_filter = ["score"]
    search_fields = ["rated_user__username", "rated_by__username"]


class AdminRoleForm(forms.ModelForm):
    """
    Overrides the plain JSONField input Django would otherwise render for
    `capabilities` with a proper pick-from-a-list widget, sourced from the
    same fixed vocabulary the API validates against
    (common/admin_capabilities.py) — so there's one source of truth for
    "what capabilities exist," not a second list to keep in sync by hand.
    Still saves/loads as the same JSON list of capability-code strings the
    model field expects; MultipleChoiceField's clean() already returns a
    list, matching JSONField's storage shape with no extra conversion.
    """

    capabilities = forms.MultipleChoiceField(
        choices=[(code, f"{code} — {description}") for code, description in ALL_CAPABILITIES.items()],
        widget=FilteredSelectMultiple("capabilities", is_stacked=False),
        required=False,
        help_text="Pick from the fixed set of capabilities defined in common/admin_capabilities.py.",
    )

    class Meta:
        model = AdminRole
        fields = "__all__"


@admin.register(AdminRole)
class AdminRoleAdmin(admin.ModelAdmin):
    form = AdminRoleForm
    list_display = ["name", "is_protected", "created_at"]
    search_fields = ["name"]
    readonly_fields = ["is_protected"]


@admin.register(FeaturedDonor)
class FeaturedDonorAdmin(admin.ModelAdmin):
    list_display = ["user", "featured_from", "featured_until", "created_by"]
    search_fields = ["user__username"]
    readonly_fields = ["created_by"]
