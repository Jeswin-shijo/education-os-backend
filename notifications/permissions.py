"""RBAC matrix for the notifications viewset.

Per the BUILD_CONTRACT matrix (notifications row): every authenticated role
reads their own notifications; only admins broadcast. The read/write actions
here operate on the requesting user's own data (enforced in the viewset by
scoping the queryset to the user), so all roles may call them; the ``broadcast``
action is admin-only.
"""
from core.permissions import Role

ALL_ROLES = list(Role.ALL)
ADMINS = list(Role.ADMINS)

# All roles read their own; per-user mutations (mark read/all) are self-scoped;
# broadcast is admin-only.
NOTIFICATIONS_MATRIX = {
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    "read": ALL_ROLES,            # POST /{id}/read
    "read_all": ALL_ROLES,        # POST /read-all
    "unread_count": ALL_ROLES,    # GET /unread-count
    "broadcast": ADMINS,          # POST /broadcast (admin only)
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
}
