"""I/O serializers for the transport app.

Two flavours:

* CRUD serializers (``*Serializer``) — used by the admin management viewset;
  accept/return model fields plus FK ids.
* App-shaped serializers (``BusRouteAppSerializer`` / ``BusLiveStatusAppSerializer``)
  — emit the exact camelCase shapes the mobile app expects (``types.ts``:
  ``BusRoute`` + nested ``BusStop``, and ``BusLiveStatus``).
"""
from rest_framework import serializers

from transport.models import BusLiveStatus, BusRoute, BusStop


# --- CRUD serializers --------------------------------------------------------
class BusStopSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusStop
        fields = ["id", "route", "name", "time", "order", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class BusRouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusRoute
        fields = [
            "id",
            "name",
            "number",
            "driver",
            "driver_phone",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class BusLiveStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusLiveStatus
        fields = [
            "id",
            "route",
            "current_stop",
            "next_stop",
            "eta_mins",
            "occupancy",
            "lat",
            "lng",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# --- App-shaped read serializers (mobile contract) ---------------------------
class BusStopAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``BusStop`` shape (``{ name, time }``)."""

    class Meta:
        model = BusStop
        fields = ["name", "time"]


class BusRouteAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``BusRoute`` shape (camelCase, nested ``stops``)."""

    id = serializers.CharField(read_only=True)
    driverPhone = serializers.CharField(source="driver_phone", read_only=True)
    stops = BusStopAppSerializer(many=True, read_only=True)

    class Meta:
        model = BusRoute
        fields = ["id", "name", "number", "stops", "driver", "driverPhone"]


class BusLiveStatusAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``BusLiveStatus`` shape (camelCase, ``routeId``)."""

    routeId = serializers.CharField(source="route_id", read_only=True)
    currentStop = serializers.CharField(source="current_stop", read_only=True)
    nextStop = serializers.CharField(source="next_stop", read_only=True)
    etaMins = serializers.IntegerField(source="eta_mins", read_only=True)

    class Meta:
        model = BusLiveStatus
        fields = [
            "routeId",
            "lat",
            "lng",
            "currentStop",
            "nextStop",
            "etaMins",
            "occupancy",
        ]
