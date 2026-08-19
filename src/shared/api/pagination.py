from typing import Any

from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.response import Response


class DefaultPageNumberPagination(PageNumberPagination):
    page_size = 16
    page_size_query_param = "page_size"
    max_page_size = 64

    def get_paginated_response(self, data: Any) -> Response:
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )


class TimelineCursorPagination(CursorPagination):
    page_size = 16
    page_size_query_param = "page_size"
    max_page_size = 64
    ordering = ("-created_at", "-id")

    def get_paginated_response(self, data: Any) -> Response:
        return Response(
            {
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )
