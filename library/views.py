"""HTTP layer for the library app.

``BookViewSet`` gives every role the catalogue (``GET /library/books?q=`` via the
``books`` action, plus a standard filterable/searchable ``list``) and admins full
CRUD, all flowing through :class:`BookService` (audit + cache-invalidate).

``BookLoanViewSet`` gives admins the full loan table and serves the mobile app's
``GET /library/loans`` (the requesting student's own loans) via the ``loans``
custom action.
"""
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.cache import TTL_LIBRARY, cache_get_or_set, cache_key
from core.permissions import Role
from core.viewsets import BaseModelViewSet

from library.models import Book, BookLoan
from library.permissions import BOOK_MATRIX, LOAN_MATRIX
from library.serializers import (
    BookAppSerializer,
    BookLoanAppSerializer,
    BookLoanSerializer,
    BookSerializer,
)
from library.services import BookLoanService, BookService
from students.models import Student

_STAFF_ROLES = set(Role.STAFF)


class BookViewSet(BaseModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer
    service_class = BookService
    permission_matrix = BOOK_MATRIX
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["category", "available", "author"]
    search_fields = ["title", "author", "category", "isbn"]
    ordering_fields = ["title", "author", "created_at"]

    # -- GET /library/books?q= (app-shaped catalogue search) --------------
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="q",
                type=str,
                required=False,
                description="Case-insensitive search over title/author/category.",
            )
        ],
        responses={200: BookAppSerializer(many=True)},
    )
    def books(self, request):
        q = (request.query_params.get("q") or "").strip()
        key = cache_key("library", "books", q.lower() or "all")

        def produce():
            qs = Book.objects.all()
            if q:
                from django.db.models import Q

                qs = qs.filter(
                    Q(title__icontains=q)
                    | Q(author__icontains=q)
                    | Q(category__icontains=q)
                )
            return BookAppSerializer(qs.order_by("title"), many=True).data

        return Response(cache_get_or_set(key, TTL_LIBRARY, produce))


class BookLoanViewSet(BaseModelViewSet):
    queryset = BookLoan.objects.select_related("book", "student").all()
    serializer_class = BookLoanSerializer
    service_class = BookLoanService
    permission_matrix = LOAN_MATRIX
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["student", "book", "status"]
    ordering_fields = ["issued_on", "due_on", "created_at"]

    # -- GET /library/loans (requesting student's own loans) --------------
    def _resolve_student(self, request):
        """The Student profile linked to the requesting user (or 404)."""
        student = Student.objects.filter(user=request.user).first()
        if student is None:
            raise NotFound("No student profile is linked to this account.")
        return student

    @extend_schema(responses={200: BookLoanAppSerializer(many=True)})
    def loans(self, request):
        student = self._resolve_student(request)
        qs = (
            BookLoan.objects.select_related("book")
            .filter(student=student)
            .order_by("-issued_on")
        )
        return Response(BookLoanAppSerializer(qs, many=True).data)
