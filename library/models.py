"""Library domain models.

:class:`Book` is the catalogue record (mirrors the mobile app's ``Book`` type:
``title``/``author``/``category``/``available``) plus the inventory fields the
build spec adds (``isbn``, ``copies_total``, ``copies_available``).
:class:`BookLoan` tracks a copy issued to a :class:`students.Student` and maps to
the app's ``BookLoan`` type (``bookId``/``title``/``issuedOn``/``dueOn``/
``status``).

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete).
"""
from django.db import models
from django.utils import timezone

from core.models import BaseModel


class Book(BaseModel):
    """A catalogue title with copy inventory.

    ``available`` is a denormalised convenience flag the app reads directly; the
    service keeps it in sync with ``copies_available`` on every write and loan
    issue/return.
    """

    title = models.CharField(max_length=255, db_index=True)
    author = models.CharField(max_length=255, blank=True, default="", db_index=True)
    category = models.CharField(max_length=128, blank=True, default="", db_index=True)
    isbn = models.CharField(max_length=32, blank=True, default="", db_index=True)
    available = models.BooleanField(default=True, db_index=True)
    copies_total = models.PositiveIntegerField(default=1)
    copies_available = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["title"]
        verbose_name = "Book"
        verbose_name_plural = "Books"
        indexes = [
            models.Index(fields=["category", "available"]),
        ]

    def __str__(self):
        return f"{self.title} — {self.author}"

    def sync_availability(self) -> None:
        """Recompute the ``available`` flag from ``copies_available``."""
        self.available = self.copies_available > 0


class BookLoan(BaseModel):
    """A copy of a :class:`Book` issued to a :class:`students.Student`."""

    STATUS_BORROWED = "borrowed"
    STATUS_RETURNED = "returned"
    STATUS_OVERDUE = "overdue"
    STATUS_CHOICES = [
        (STATUS_BORROWED, "Borrowed"),
        (STATUS_RETURNED, "Returned"),
        (STATUS_OVERDUE, "Overdue"),
    ]

    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="loans",
    )
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="book_loans",
    )
    issued_on = models.DateField(default=timezone.localdate)
    due_on = models.DateField()
    returned_on = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_BORROWED,
        db_index=True,
    )

    class Meta:
        ordering = ["-issued_on"]
        verbose_name = "Book loan"
        verbose_name_plural = "Book loans"
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["book", "status"]),
        ]

    def __str__(self):
        return f"{self.book_id} → {self.student_id} ({self.status})"

    @property
    def is_overdue(self) -> bool:
        return (
            self.status == self.STATUS_BORROWED
            and self.returned_on is None
            and self.due_on < timezone.localdate()
        )
