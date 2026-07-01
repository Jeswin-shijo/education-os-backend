"""Business-logic layer for the library app.

Services extend :class:`core.services.BaseService` so every write auto-stamps
``created_by``/``updated_by``, emits an :class:`~core.models.AuditLog` row and
invalidates the cached catalogue/loan views (``library`` prefix, TTL 600s).

:class:`BookService` keeps a :class:`~library.models.Book`'s ``available`` flag in
sync with ``copies_available`` on every write.
"""
from __future__ import annotations

from core.cache import invalidate_prefix
from core.services import BaseService

from library.models import Book, BookLoan
from library.repositories import BookLoanRepository, BookRepository

# Cache key prefix owned by this app.
LIBRARY_PREFIX = "library"


class BookService(BaseService):
    model = Book
    repository_class = BookRepository
    entity_name = "Book"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(LIBRARY_PREFIX)

    def create(self, **data) -> Book:
        # Default copies_available to copies_total when only the total is given,
        # then derive the availability flag from stock.
        if "copies_available" not in data and "copies_total" in data:
            data["copies_available"] = data["copies_total"]
        data["available"] = data.get("copies_available", 0) > 0
        return super().create(**data)

    def update(self, instance: Book, **data) -> Book:
        copies_available = data.get("copies_available", instance.copies_available)
        data["available"] = copies_available > 0
        return super().update(instance, **data)


class BookLoanService(BaseService):
    model = BookLoan
    repository_class = BookLoanRepository
    entity_name = "BookLoan"

    def invalidate_cache(self, instance=None) -> None:
        invalidate_prefix(LIBRARY_PREFIX)
