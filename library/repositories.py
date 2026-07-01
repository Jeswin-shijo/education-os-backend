"""Data-access layer for the library app.

Repositories wrap each model over the soft-delete-aware default manager and add
``select_related`` where serializers touch related objects, avoiding N+1 queries
on the loans endpoint.
"""
from __future__ import annotations

from core.repositories import BaseRepository

from library.models import Book, BookLoan


class BookRepository(BaseRepository):
    model = Book


class BookLoanRepository(BaseRepository):
    model = BookLoan

    def get_queryset(self, include_deleted: bool = False):
        return (
            super()
            .get_queryset(include_deleted)
            .select_related("book", "student")
        )

    def for_student(self, student, include_deleted: bool = False):
        """Loans belonging to ``student`` (most recent first)."""
        return self.get_queryset(include_deleted).filter(student=student)
