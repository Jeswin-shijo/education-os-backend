"""Standard pagination emitting pagination info under the envelope ``meta``."""
from collections import OrderedDict

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """Page-number pagination with a ``page_size`` override (max 100).

    ``get_paginated_response`` returns the raw list as ``data`` and the
    pagination info as a top-level ``pagination`` key; the envelope renderer
    lifts that into ``meta`` so views never assemble the envelope themselves.
    """

    page_size = 20
    page_size_query_param = "page_size"
    page_query_param = "page"
    max_page_size = 100

    def get_pagination_meta(self) -> dict:
        return OrderedDict(
            [
                ("count", self.page.paginator.count),
                ("page", self.page.number),
                ("page_size", self.get_page_size(self.request)),
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
