"""RBAC matrix for the certificates viewset.

Per the BUILD_CONTRACT matrix, ``certificates`` is **read for everyone** and
**read-write for admins**: every authenticated role may read certificates (the
``mine`` custom action scopes non-staff to their own records), while only
super_admin/admin may issue/update/delete them.
"""
from core.permissions import Role

ADMINS = list(Role.ADMINS)      # super_admin, admin
ALL_ROLES = list(Role.ALL)

CERTIFICATE_MATRIX = {
    # App-facing read of the requesting student's own certificates.
    "mine": ALL_ROLES,
    # Admin-managed full table + CRUD (issue/update/delete).
    "list": ADMINS,
    "retrieve": ADMINS,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
}
