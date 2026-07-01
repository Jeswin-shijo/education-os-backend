"""RBAC matrix for the materials viewset.

Contract (assignments/materials/quizzes row): student **R**, parent
**R(child)**, faculty **RW(own)**, hod **R(dept)**, principal **R**, admin
**RW**. Concretely:

- Everyone authenticated may read the material list/detail (the student
  ``?subjectId=`` view). Deeper scoping (child/dept) is refined in the view.
- Creating materials (``create`` / ``POST /materials`` upload) + the faculty
  ``faculty_materials`` list are faculty + admins.
- Update/delete are faculty (own) + admins.
"""
from core.permissions import Role

ADMINS = list(Role.ADMINS)
ALL_ROLES = list(Role.ALL)
FACULTY_AND_ADMINS = [Role.FACULTY, *Role.ADMINS]

MATERIAL_MATRIX = {
    # Reads: any authenticated role (object scoping applied in the view).
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    # Faculty-created + admin management.
    "create": FACULTY_AND_ADMINS,
    "update": FACULTY_AND_ADMINS,
    "partial_update": FACULTY_AND_ADMINS,
    "destroy": FACULTY_AND_ADMINS,
    # Custom actions.
    "faculty_materials": FACULTY_AND_ADMINS,
}
