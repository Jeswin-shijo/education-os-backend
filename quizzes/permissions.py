"""RBAC matrix for the quizzes viewset.

Contract (assignments/materials/quizzes row): student **R**, parent **R**,
faculty **RW (own)**, hod **R**, principal **R**, admin **RW**. Concretely:

- ``list``/``retrieve`` are readable by every authenticated role.
- ``create`` (faculty POST /quizzes with nested questions) is allowed for
  faculty and admins.
- ``update``/``partial_update``/``destroy`` are restricted to faculty + admins
  (owner-scoping for faculty is enforced object-level in the view). The mobile
  contract only exercises list/retrieve/create, but the mutating actions are
  matrixed for completeness.
"""
from core.permissions import Role

ADMINS = list(Role.ADMINS)
# Every authenticated role may read quizzes.
ALL_ROLES = [
    Role.SUPER_ADMIN,
    Role.ADMIN,
    Role.PRINCIPAL,
    Role.HOD,
    Role.FACULTY,
    Role.PARENT,
    Role.STUDENT,
]
# Faculty + admins may create/modify quizzes.
FACULTY_WRITERS = list({*ADMINS, Role.FACULTY})

QUIZ_MATRIX = {
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    "create": FACULTY_WRITERS,
    "update": FACULTY_WRITERS,
    "partial_update": FACULTY_WRITERS,
    "destroy": FACULTY_WRITERS,
}
