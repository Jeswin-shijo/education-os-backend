"""I/O serializers for the events app.

Two flavours:

* CRUD serializer (:class:`EventSerializer`) — used by the admin management
  viewset; accepts/returns the full model fields.
* App-shaped serializer (:class:`EventAppSerializer`) — emits the exact shape the
  mobile app expects (``types.ts`` ``EventItem``:
  ``{id, title, date, time, venue, category, registered}``). ``registered`` is
  derived per requesting user from live :class:`~events.models.EventRegistration`
  rows.
"""
from rest_framework import serializers

from events.models import Event


# --- CRUD serializer (admin console) -----------------------------------------
class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "date",
            "time",
            "venue",
            "category",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# --- App-shaped serializer (mobile contract: types.ts EventItem) -------------
class EventAppSerializer(serializers.ModelSerializer):
    """Matches ``types.ts`` ``EventItem``.

    ``registered`` reflects whether the requesting user has a live registration.
    The view supplies the set of registered event ids via serializer context
    (``registered_ids``) so the list endpoint stays a single query.
    """

    id = serializers.CharField(read_only=True)
    registered = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ["id", "title", "date", "time", "venue", "category", "registered"]

    def get_registered(self, obj) -> bool:
        registered_ids = self.context.get("registered_ids") or set()
        return obj.id in registered_ids
