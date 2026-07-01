"""I/O serializers for the library app.

Two flavours per resource:

* CRUD serializers (``*Serializer``) — used by the admin/staff management
  viewset; accept/return the full model fields.
* App-shaped serializers (``*AppSerializer``) — emit the exact camelCase shape
  the mobile app expects (``types.ts`` ``Book`` / ``BookLoan``) for the
  ``GET /library/books`` and ``GET /library/loans`` reads.
"""
from rest_framework import serializers

from library.models import Book, BookLoan


# --- CRUD serializers (admin/staff console) ----------------------------------
class BookSerializer(serializers.ModelSerializer):
    """Full catalogue record. ``available`` is derived by the service from
    ``copies_available`` and is therefore read-only here."""

    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "author",
            "category",
            "isbn",
            "available",
            "copies_total",
            "copies_available",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "available", "created_at", "updated_at"]

    def validate(self, attrs):
        total = attrs.get(
            "copies_total",
            getattr(self.instance, "copies_total", None),
        )
        available = attrs.get("copies_available")
        if available is not None and total is not None and available > total:
            raise serializers.ValidationError(
                {"copies_available": "Cannot exceed copies_total."}
            )
        return attrs


class BookLoanSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookLoan
        fields = [
            "id",
            "book",
            "student",
            "issued_on",
            "due_on",
            "returned_on",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# --- App-shaped serializers (mobile contract: types.ts) ----------------------
class BookAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``Book`` (``{id, title, author, category, available}``)."""

    id = serializers.CharField(read_only=True)

    class Meta:
        model = Book
        fields = ["id", "title", "author", "category", "available"]


class BookLoanAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``BookLoan``
    (``{id, bookId, title, issuedOn, dueOn, status}``)."""

    id = serializers.CharField(read_only=True)
    bookId = serializers.CharField(source="book_id", read_only=True)
    title = serializers.CharField(source="book.title", read_only=True)
    issuedOn = serializers.DateField(source="issued_on", read_only=True)
    dueOn = serializers.DateField(source="due_on", read_only=True)

    class Meta:
        model = BookLoan
        fields = ["id", "bookId", "title", "issuedOn", "dueOn", "status"]
