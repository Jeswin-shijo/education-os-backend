"""RBAC for the ai app.

The AI assistant is a personal surface: **every authenticated role** may use it,
but only against **their own** threads. There is no cross-user access and no
admin-broadcast surface here, so the matrix simply admits all roles for the
custom actions; ownership is enforced object-level in the view (threads are
always filtered/created for ``request.user``).
"""
from core.permissions import Role

ALL_ROLES = [
    Role.SUPER_ADMIN,
    Role.ADMIN,
    Role.PRINCIPAL,
    Role.HOD,
    Role.FACULTY,
    Role.PARENT,
    Role.STUDENT,
]

# All custom actions on the AI viewset are self-scoped and open to every role.
AI_MATRIX = {
    "threads": ALL_ROLES,
    "thread_by_feature": ALL_ROLES,
    "respond": ALL_ROLES,
    "send_message": ALL_ROLES,
    "suggestions": ALL_ROLES,
    "*": ALL_ROLES,
}
