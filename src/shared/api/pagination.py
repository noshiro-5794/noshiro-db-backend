from typing import Any

from rest_framework.pagination import PageNumberPagination

from shared.api.responses import APIResponse


class DefaultPageNumberPagination(PageNumberPagination):
    page_size = 16
    page_size_query_param = "page_size"
    max_page_size = 64

    def get_paginated_response(self, data: Any) -> APIResponse:
        return APIResponse(
            data={
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )
