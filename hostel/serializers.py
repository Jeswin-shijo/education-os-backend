"""I/O serializers for the hostel app.

Two flavours:

* CRUD serializers (``*Serializer``) — used by the admin/staff management
  viewsets. They accept/return model fields plus FK ids and expose a few
  read-only convenience fields (block name on a room, resolved room/block on an
  allocation).
* App-shaped serializer (``HostelInfoSerializer``) — emits the exact camelCase
  shape the mobile app expects (``types.ts`` ``HostelInfo``) for ``GET /hostel``,
  flattening an allocation joined to its room and block.
"""
from rest_framework import serializers

from hostel.models import HostelAllocation, HostelBlock, HostelRoom


# --- CRUD serializers (admin/staff console) ----------------------------------
class HostelBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = HostelBlock
        fields = [
            "id",
            "name",
            "warden",
            "warden_phone",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class HostelRoomSerializer(serializers.ModelSerializer):
    block_name = serializers.CharField(source="block.name", read_only=True)

    class Meta:
        model = HostelRoom
        fields = [
            "id",
            "block",
            "block_name",
            "room_no",
            "capacity",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class HostelAllocationSerializer(serializers.ModelSerializer):
    room_no = serializers.CharField(source="room.room_no", read_only=True)
    block = serializers.CharField(source="room.block.name", read_only=True)
    warden = serializers.CharField(source="room.block.warden", read_only=True)

    class Meta:
        model = HostelAllocation
        fields = [
            "id",
            "student",
            "room",
            "room_no",
            "block",
            "warden",
            "bed",
            "mess_plan",
            "fees",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# --- App-shaped serializer (mobile contract: types.ts HostelInfo) ------------
class HostelInfoSerializer(serializers.Serializer):
    """Matches ``types.ts`` ``HostelInfo`` (flattened allocation + room + block).

    Read-only; built from a :class:`HostelAllocation` instance whose ``room`` and
    ``room.block`` are already ``select_related``.
    """

    block = serializers.SerializerMethodField()
    roomNo = serializers.SerializerMethodField()
    bed = serializers.CharField()
    warden = serializers.SerializerMethodField()
    wardenPhone = serializers.SerializerMethodField()
    messPlan = serializers.CharField(source="mess_plan")
    fees = serializers.FloatField()

    def get_block(self, obj) -> str:
        return obj.room.block.name if obj.room_id else ""

    def get_roomNo(self, obj) -> str:
        return obj.room.room_no if obj.room_id else ""

    def get_warden(self, obj) -> str:
        return obj.room.block.warden if obj.room_id else ""

    def get_wardenPhone(self, obj) -> str:
        return obj.room.block.warden_phone if obj.room_id else ""
