from django.contrib import admin

from .models import PartnerApplication


@admin.register(PartnerApplication)
class PartnerApplicationAdmin(admin.ModelAdmin):
    list_display = ["id", "applicant_name", "applicant_email", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["applicant_name", "applicant_email", "organization_name"]
    readonly_fields = ["applicant_user", "granted_role", "created_dropoff_point"]
