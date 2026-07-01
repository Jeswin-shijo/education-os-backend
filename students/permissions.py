"""RBAC matrices for the students viewsets.

Roster CRUD (list/retrieve/create/update/destroy) is staff/admin only — students
and parents do not browse the institutional roster. Each student reads/edits
their own profile via the ``me`` action; parents (and staff) may read a child's
profile, allowed for now via a staff-or-self object check.
"""
from core.permissions import Role

STAFF = list(Role.STAFF)          # super_admin, admin, principal, hod, faculty
ADMINS = list(Role.ADMINS)        # super_admin, admin
ALL_ROLES = list(Role.ALL)

# Roster management: staff read the roster; only admins mutate it.
STUDENT_MATRIX = {
    "list": STAFF,
    "retrieve": STAFF,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
    # `me` self-profile: any authenticated role reaches the action; object-level
    # scoping restricts non-staff to their own linked Student.
    "me": ALL_ROLES,
}

# Child-collection viewsets (addresses/guardians/medical/documents): staff read,
# admins write.
CHILD_MATRIX = {
    "list": STAFF,
    "retrieve": STAFF,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
}
