"""Hostel domain models.

Three models model campus residential data:

* :class:`HostelBlock` — a hostel building with its warden contact.
* :class:`HostelRoom` — a room inside a block, with a bed ``capacity``.
* :class:`HostelAllocation` — the one-to-one link between a
  ``students.Student`` and the room/bed they occupy, carrying the mess plan
  and the hostel ``fees`` (``Decimal`` — money is never a float).

The mobile app's ``HostelInfo`` type is a flattened view of an allocation
joined to its room and block; ``GET /hostel`` composes it for the requesting
student. Every model extends :class:`core.models.BaseModel` (UUID PK, audit
fields, soft-delete).
"""
from decimal import Decimal

from django.db import models

from core.models import BaseModel


class HostelBlock(BaseModel):
    """A hostel block/building with its warden contact details."""

    name = models.CharField(max_length=128, db_index=True)
    warden = models.CharField(max_length=255, blank=True, default="")
    warden_phone = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        ordering = ["name"]
        verbose_name = "Hostel block"
        verbose_name_plural = "Hostel blocks"

    def __str__(self):
        return self.name


class HostelRoom(BaseModel):
    """A room inside a :class:`HostelBlock` with a bed ``capacity``."""

    block = models.ForeignKey(
        HostelBlock,
        on_delete=models.CASCADE,
        related_name="rooms",
    )
    room_no = models.CharField(max_length=32, db_index=True)
    capacity = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["block", "room_no"]
        verbose_name = "Hostel room"
        verbose_name_plural = "Hostel rooms"
        constraints = [
            models.UniqueConstraint(
                fields=["block", "room_no"],
                condition=models.Q(is_deleted=False),
                name="uniq_room_no_per_block",
            ),
        ]
        indexes = [
            models.Index(fields=["block", "room_no"]),
        ]

    def __str__(self):
        return f"{self.block.name} / {self.room_no}"


class HostelAllocation(BaseModel):
    """The room/bed a student is allocated, with mess plan and fees.

    One allocation per student (``OneToOne``); the room may house several
    students up to its ``capacity``.
    """

    student = models.OneToOneField(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="hostel_allocation",
    )
    room = models.ForeignKey(
        HostelRoom,
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    bed = models.CharField(max_length=32, blank=True, default="")
    mess_plan = models.CharField(max_length=128, blank=True, default="")
    fees = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Hostel allocation"
        verbose_name_plural = "Hostel allocations"
        indexes = [
            models.Index(fields=["room"]),
        ]

    def __str__(self):
        return f"Allocation {self.student_id} → {self.room_id}"
