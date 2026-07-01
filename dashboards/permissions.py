"""RBAC for the dashboards app.

Each dashboard endpoint is a self-scoped read for the owning role, with staff /
admin allowed to read (for support/monitoring). The matrices drive
:class:`core.permissions.RoleModelPermission`; the views additionally enforce
object-level self-scoping (a student only ever sees their own dashboard, a parent
only their child's, a faculty only their own) by resolving the current user's
linked record — the role check here is the coarse gate.

Per the BUILD_CONTRACT RBAC matrix ("own profile/dashboard"):
    student RW(self) · parent R(child) · faculty RW(self) · hod RW(self) ·
    principal R · admin R
"""
from core.permissions import Role

# GET /students/me/dashboard — the student's own dashboard; staff/admin may read.
STUDENT_DASHBOARD_MATRIX = {
    "retrieve": [
        Role.STUDENT,
        Role.ADMIN,
        Role.SUPER_ADMIN,
        Role.PRINCIPAL,
    ],
    "*": [Role.STUDENT, Role.ADMIN, Role.SUPER_ADMIN, Role.PRINCIPAL],
}

# GET /parent/dashboard — the parent's child summary; staff/admin may read.
PARENT_DASHBOARD_MATRIX = {
    "retrieve": [
        Role.PARENT,
        Role.ADMIN,
        Role.SUPER_ADMIN,
        Role.PRINCIPAL,
    ],
    "*": [Role.PARENT, Role.ADMIN, Role.SUPER_ADMIN, Role.PRINCIPAL],
}

# GET /faculty/dashboard — the faculty's own dashboard; hod/principal/admin read.
FACULTY_DASHBOARD_MATRIX = {
    "retrieve": [
        Role.FACULTY,
        Role.HOD,
        Role.PRINCIPAL,
        Role.ADMIN,
        Role.SUPER_ADMIN,
    ],
    "*": [Role.FACULTY, Role.HOD, Role.PRINCIPAL, Role.ADMIN, Role.SUPER_ADMIN],
}
