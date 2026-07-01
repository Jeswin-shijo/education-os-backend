"""RBAC for the chat viewset.

Chat is parent ↔ teacher messaging. Per the contract only the two thread
participants may see or act on a thread — enforced *object-level* by
:class:`IsThreadParticipant`. The role matrix additionally gates which roles may
touch the chat endpoints at all: parents and faculty (the two participant roles)
plus admins (support/oversight). Students/HOD/principal have no chat surface in
the app, so they are excluded.
"""
from rest_framework.permissions import BasePermission

from core.permissions import Role

# Roles allowed to reach the chat endpoints (object-level scoping still applies).
CHAT_ROLES = list({*Role.ADMINS, Role.FACULTY, Role.PARENT})

CHAT_MATRIX = {
    "list": CHAT_ROLES,
    "retrieve": CHAT_ROLES,
    "messages": CHAT_ROLES,
    "read": CHAT_ROLES,
    "*": CHAT_ROLES,
}


class IsThreadParticipant(BasePermission):
    """Object-level: only the thread's teacher or parent (or an admin)."""

    message = "You are not a participant in this conversation."

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if getattr(user, "role", None) in set(Role.ADMINS):
            return True
        return obj.is_participant(user)
