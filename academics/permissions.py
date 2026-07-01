"""RBAC matrices for the academics viewsets.

Reads (list/retrieve + the custom timetable actions) are open to every
authenticated role; writes are restricted to admins. Subjects and Sections also
admit HOD writes (HODs curate their department's teaching structure).
"""
from core.permissions import Role

ALL_ROLES = list(Role.ALL)
ADMINS = list(Role.ADMINS)
ADMINS_AND_HOD = list(Role.ADMINS) + [Role.HOD]

# Admin-only writes; everyone reads.
ADMIN_WRITE_MATRIX = {
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
}

# Admin + HOD writes; everyone reads (subjects, sections).
ADMIN_HOD_WRITE_MATRIX = {
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    "create": ADMINS_AND_HOD,
    "update": ADMINS_AND_HOD,
    "partial_update": ADMINS_AND_HOD,
    "destroy": ADMINS_AND_HOD,
    # custom read actions
    "week": ALL_ROLES,
    "today": ALL_ROLES,
}

# Timetable viewset: all reads, admin writes.
TIMETABLE_MATRIX = {
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    "week": ALL_ROLES,
    "today": ALL_ROLES,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
}
