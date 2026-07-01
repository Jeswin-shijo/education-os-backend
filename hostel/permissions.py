"""RBAC matrices for the hostel viewsets.

Per the BUILD_CONTRACT matrix (library/hostel/transport row): every role may
read hostel data; only admins may create/update/delete blocks, rooms and
allocations.

The ``info`` action (``GET /hostel``) returns the *requesting* student's own
allocation, so any authenticated role reaches it — the queryset scopes it to the
caller's linked Student record.
"""
from core.permissions import Role

STAFF = list(Role.STAFF)          # super_admin, admin, principal, hod, faculty
ADMINS = list(Role.ADMINS)        # super_admin, admin
ALL_ROLES = list(Role.ALL)

# Block/room/allocation management: everyone reads; only admins mutate.
HOSTEL_MATRIX = {
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
    # `info` self-allocation: any authenticated role reaches the action; the
    # view scopes it to the caller's own linked Student.
    "info": ALL_ROLES,
}
