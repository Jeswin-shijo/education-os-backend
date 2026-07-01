"""Transport domain models.

Mirrors the mobile app's transport shapes (``types.ts``: ``BusRoute``,
``BusStop``, ``BusLiveStatus``): a :class:`BusRoute` has ordered
:class:`BusStop` rows and a live :class:`BusLiveStatus` (one-to-one) that a
future Channels consumer will push updates to. REST reads are exposed now.

Every model extends :class:`core.models.BaseModel` (UUID PK, audit fields,
soft-delete).
"""
from django.db import models

from core.models import BaseModel


class BusRoute(BaseModel):
    """A bus route with a driver and an ordered set of stops."""

    name = models.CharField(max_length=255)
    number = models.CharField(max_length=32, db_index=True)
    driver = models.CharField(max_length=255, blank=True, default="")
    driver_phone = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        ordering = ["number"]
        verbose_name = "Bus Route"
        verbose_name_plural = "Bus Routes"

    def __str__(self):
        return f"{self.number} — {self.name}"


class BusStop(BaseModel):
    """A single stop on a route. ``order`` drives the sequence along the route."""

    route = models.ForeignKey(
        BusRoute,
        on_delete=models.CASCADE,
        related_name="stops",
    )
    name = models.CharField(max_length=255)
    # Stored as a free-form "HH:MM" string to mirror the mobile app contract.
    time = models.CharField(max_length=16, blank=True, default="")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["route", "order"]
        indexes = [models.Index(fields=["route", "order"])]
        constraints = [
            models.UniqueConstraint(
                fields=["route", "order"],
                condition=models.Q(is_deleted=False),
                name="uniq_busstop_route_order",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.route.number})"


class BusLiveStatus(BaseModel):
    """Live position/occupancy for a route (one row per route).

    A realtime WebSocket consumer will update these fields later; for now the
    values are read over REST via ``GET /transport/routes/{id}/live``.
    """

    route = models.OneToOneField(
        BusRoute,
        on_delete=models.CASCADE,
        related_name="live_status",
    )
    current_stop = models.CharField(max_length=255, blank=True, default="")
    next_stop = models.CharField(max_length=255, blank=True, default="")
    eta_mins = models.PositiveIntegerField(default=0)
    # Occupancy as a percentage (0-100) of the bus's capacity.
    occupancy = models.PositiveIntegerField(default=0)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "Bus Live Status"
        verbose_name_plural = "Bus Live Statuses"

    def __str__(self):
        return f"Live: {self.route.number}"
