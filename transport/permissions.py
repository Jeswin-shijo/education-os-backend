"""RBAC matrices for the transport viewsets.

Per the BUILD_CONTRACT matrix (library/hostel/transport/events/certificates row):
every authenticated role reads; only admins write. The custom ``live`` read
action is open to all roles.
"""
from core.permissions import Role

ALL_ROLES = list(Role.ALL)
ADMINS = list(Role.ADMINS)

# Everyone reads (incl. the custom `live` action); admins write.
TRANSPORT_MATRIX = {
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    "live": ALL_ROLES,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
}

# Bus stops + live-status admin management viewsets: reads open, admin writes.
ADMIN_WRITE_MATRIX = {
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
}
