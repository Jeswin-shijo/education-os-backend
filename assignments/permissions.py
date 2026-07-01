"""RBAC matrices for the assignments viewsets.

Contract (assignments/materials/quizzes row): student **R + submit**, parent
**R(child)**, faculty **RW(own)**, hod **R(dept)**, principal **R**, admin
**RW**. Concretely:

- Everyone authenticated may read the assignment list/detail (students see their
  own per-student status; scoping to child/dept/self is refined in views).
- ``submit`` is student-only.
- Creating assignments (``create`` / ``POST /assignments``) and the faculty
  ``faculty_assignments`` list are faculty + admins.
- Update/delete are faculty (own) + admins.
"""
from core.permissions import Role

ADMINS = list(Role.ADMINS)
ALL_ROLES = list(Role.ALL)
FACULTY_AND_ADMINS = [Role.FACULTY, *Role.ADMINS]

ASSIGNMENT_MATRIX = {
    # Reads: any authenticated role (object scoping applied in the view/service).
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    # Faculty-created + admin management.
    "create": FACULTY_AND_ADMINS,
    "update": FACULTY_AND_ADMINS,
    "partial_update": FACULTY_AND_ADMINS,
    "destroy": FACULTY_AND_ADMINS,
    # Custom actions.
    "submit": [Role.STUDENT],
    "faculty_assignments": FACULTY_AND_ADMINS,
}
