"""
Reusable, generic permission building blocks. Object-level rules that are
specific to a single app's domain (e.g. "only the exchange's donor or
recipient") live in that app's own `permissions.py` and typically subclass
from here.
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsOwnerOrReadOnly(BasePermission):
    """
    Read access to anyone permitted by the view; write access only to the
    object's owner. Expects the object to expose an `owner` attribute —
    subclass and override `get_owner(obj)` if the field is named
    differently.
    """

    owner_field = "owner"

    def get_owner(self, obj):
        return getattr(obj, self.owner_field)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return self.get_owner(obj) == request.user


class IsStaffOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)


class IsStaff(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)


class HasCapability(BasePermission):
    """
    Usage: permission_classes = [HasCapability("listings.remove_restore")]

    Checks request.user.admin_role.capabilities — see docs/ADMIN_API_PLAN.md.
    Completely decoupled from role *names*; a role can be renamed or have
    its capabilities changed at runtime with no code change needed here.
    """

    def __init__(self, capability: str):
        self.capability = capability

    def __call__(self):
        # DRF instantiates permission_classes entries with no args; this
        # lets HasCapability("x") itself be used directly in the list
        # (already-instantiated) rather than needing a factory wrapper.
        return self

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_capability(self.capability)
        )


class HasAnyCapability(BasePermission):
    """Usage: permission_classes = [HasAnyCapability("dropoff.view", "dropoff.manage", "dropoff.manage_all")]"""

    def __init__(self, *capabilities: str):
        self.capabilities = capabilities

    def __call__(self):
        return self

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.admin_role
            and any(c in request.user.admin_role.capabilities for c in self.capabilities)
        )
