from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsListingOwnerOrReadOnly(BasePermission):
    """Only the listing's owner may edit/delete it or manage its photos."""

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        listing = obj if hasattr(obj, "owner") else obj.listing
        return listing.owner_id == request.user.id
