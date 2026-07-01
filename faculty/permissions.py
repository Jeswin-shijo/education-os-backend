"""RBAC matrices for the faculty viewsets.

Contract: faculty **R own**; staff **R**; admin **full**. Concretely:

- Admin/super-admin get full CRUD over :class:`FacultyProfile` rows.
- Every staff role (super_admin/admin/principal/hod/faculty) may read the
  faculty directory and class/roster reads.
- The self-scoped endpoints (``/faculty/me``, ``/faculty/classes`` …) are open
  to any authenticated staff role; object-level scoping to "own" data is applied
  in the views/services (a faculty user only ever sees their own profile +
  classes).
"""
from core.permissions import Role

ADMINS = list(Role.ADMINS)
STAFF = list(Role.STAFF)

# Admin full CRUD on FacultyProfile; all staff may read the directory.
FACULTY_PROFILE_MATRIX = {
    "list": STAFF,
    "retrieve": STAFF,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
    # self-scoped custom actions
    "me": STAFF,
    "classes": STAFF,
    "class_detail": STAFF,
    "roster": STAFF,
}
