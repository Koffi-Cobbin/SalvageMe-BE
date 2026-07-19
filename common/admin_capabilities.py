"""
The fixed vocabulary of admin capabilities. Capabilities can only be defined
here in code, because each one corresponds to an actual permission check
guarding actual endpoint logic (see common/permissions.py::HasCapability).
Which capabilities any given role actually has is data (apps.accounts.models.AdminRole),
fully admin-editable at runtime — see docs/ADMIN_API_PLAN.md for the full design.
"""

ALL_CAPABILITIES = {
    "users.view": "View user profiles and account status",
    "users.suspend": "Suspend / reactivate user accounts",
    "users.edit": "Edit a user's profile fields directly",
    "roles.manage": "Create, edit, delete roles and assign them to users",
    "listings.view": "View listings, including removed ones",
    "listings.remove_restore": "Remove / restore listings",
    "listings.delete_photo": "Delete an individual listing photo",
    "categories.manage": "Create / edit / delete categories",
    "reports.view": "View filed reports",
    "reports.resolve": "Resolve / dismiss reports",
    "exchanges.view": "View all exchanges",
    "exchanges.force_override": "Force-cancel / force-complete a stuck exchange",
    "requests.view": "View all book requests",
    "ratings.view": "View all user ratings",
    "dropoff.view": "View drop-off points",
    "dropoff.manage": "Create / edit / delete drop-off points assigned to you",
    "dropoff.manage_all": "Create / edit / delete any drop-off point, not just assigned ones",
    "auditlog.view": "View the admin action audit log",
    "dashboard.view": "View the admin dashboard summary",
    "stats.recompute": "Manually trigger an impact-stats recompute",
    "partner_applications.review": "Review, approve, or reject partner/drop-off applications",
}


def is_valid_capability(code: str) -> bool:
    return code in ALL_CAPABILITIES
