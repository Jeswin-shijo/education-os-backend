"""RBAC matrices for the placement viewsets.

Per the BUILD_CONTRACT matrix, placement postings are in the
"library/hostel/transport/events/certificates" family — **read for everyone,
read-write for admins**. Students additionally apply to openings and read their
own applications; principals may monitor stats (institution read).
"""
from core.permissions import Role

ADMINS = list(Role.ADMINS)          # super_admin, admin
ALL_ROLES = list(Role.ALL)
# Roles allowed to see aggregate placement stats: admins + principal (monitor).
STATS_ROLES = list(Role.ADMINS) + [Role.PRINCIPAL]

# Openings: every authenticated role browses; admins manage.
# ``apply`` (student turn-in) and ``applications`` (own list) are open to any
# authenticated role — object scoping in the action limits them to the caller's
# own student profile. ``stats`` is admin + principal.
OPENING_MATRIX = {
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    "apply": ALL_ROLES,
    "applications": ALL_ROLES,
    "stats": STATS_ROLES,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
}

# Applications management table: admins only (status transitions, full view).
APPLICATION_MATRIX = {
    "list": ADMINS,
    "retrieve": ADMINS,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
}
