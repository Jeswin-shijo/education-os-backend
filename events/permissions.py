"""RBAC matrices for the events viewsets.

Per the BUILD_CONTRACT matrix, ``events`` is **read for everyone** and
**read-write for admins**: every authenticated role may browse events and toggle
their own registration; only super_admin/admin may create/update/delete events.
"""
from core.permissions import Role

ADMINS = list(Role.ADMINS)      # super_admin, admin
ALL_ROLES = list(Role.ALL)

# Event catalogue: all roles read + toggle their own registration; admins write.
# ``events`` is the app-facing GET /events list action (method name = action key);
# ``list``/``retrieve`` are the router-backed admin reads.
EVENT_MATRIX = {
    "events": ALL_ROLES,
    "register": ALL_ROLES,
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
}
