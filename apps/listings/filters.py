import django_filters

from .models import Listing


class ListingFilterSet(django_filters.FilterSet):
    category = django_filters.CharFilter(field_name="category__slug")
    condition = django_filters.CharFilter(field_name="condition")
    grade_level = django_filters.CharFilter(field_name="grade_level")

    class Meta:
        model = Listing
        fields = ["category", "condition", "grade_level"]
