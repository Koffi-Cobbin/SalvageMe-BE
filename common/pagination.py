from rest_framework.pagination import CursorPagination


class CursorSetPagination(CursorPagination):
    """
    Default cursor pagination for unbounded list endpoints (listings,
    requests). Ordering defaults to newest-first; individual views can
    override `ordering` where a different sort makes sense (e.g. distance).
    """

    page_size = 20
    max_page_size = 100
    ordering = "-created_at"
    page_size_query_param = "page_size"
