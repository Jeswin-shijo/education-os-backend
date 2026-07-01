"""RBAC matrices for the exams viewsets.

Contract (marks/results row): student **R(self)**, parent **R(child)**, faculty
**RW(own classes)**, hod **R(dept)**, principal **R**, admin **RW**. Concretely:

- Exams and results are readable by everyone (self-scoping applied in the views:
  a student only ever sees their own results/exams).
- Result CRUD and exam CRUD are restricted to staff who own the marks
  (faculty/hod/principal read; admins + faculty write).
- The faculty marks-entry endpoints (``POST /marks``, ``GET /faculty/marks``) are
  faculty + admins; object-level scoping to "own classes" is enforced in the
  view/service.
"""
from core.permissions import Role

ADMINS = list(Role.ADMINS)
STAFF = list(Role.STAFF)
ALL_ROLES = list(Role.ALL)
FACULTY_WRITERS = [Role.SUPER_ADMIN, Role.ADMIN, Role.FACULTY]

# Exams: everyone reads (student/parent see their own via view scoping); admins
# manage the schedule.
EXAM_MATRIX = {
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
    # custom action
    "upcoming": ALL_ROLES,
}

# Results: everyone reads (self/child scoped in the view); faculty + admins write.
EXAM_RESULT_MATRIX = {
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    "create": FACULTY_WRITERS,
    "update": FACULTY_WRITERS,
    "partial_update": FACULTY_WRITERS,
    "destroy": ADMINS,
    # custom actions
    "gpa": ALL_ROLES,
}

# Faculty marks entry: faculty own their sheets; admins may manage; hod/principal
# may read.
MARKS_SHEET_MATRIX = {
    "list": STAFF,
    "retrieve": STAFF,
    "create": FACULTY_WRITERS,
    "update": FACULTY_WRITERS,
    "partial_update": FACULTY_WRITERS,
    "destroy": ADMINS,
    # custom actions (faculty POST /marks, GET /faculty/marks)
    "save_marks": FACULTY_WRITERS,
    "faculty_marks": STAFF,
}
