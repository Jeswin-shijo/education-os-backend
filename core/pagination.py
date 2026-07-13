"""Standard pagination emitting a spec-shaped ``{results, pagination}`` body."""
from collections import OrderedDict

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """Page-number pagination with a ``limit`` override (max 100).

    ``get_paginated_response`` returns ``{"results": [...], "pagination": {...}}``
    as ``data``; the envelope renderer keeps that shape so paginated responses
    match the mobile contract exactly.
    """

    page_size = 25
    page_size_query_param = "limit"
    page_query_param = "page"
    max_page_size = 100

    def get_pagination_meta(self) -> dict:
        return OrderedDict(
            [
                ("count", self.page.paginator.count),
                ("page", self.page.number),
                ("limit", self.get_page_size(self.request)),
                ("total_pages", self.page.paginator.num_pages),
                ("next", self.get_next_link()),
                ("previous", self.get_previous_link()),
            ]
        )

    def get_paginated_response(self, data) -> Response:
        return Response(
            OrderedDict(
                [
                    ("results", data),
                    ("pagination", self.get_pagination_meta()),
                ]
            )
        )
