"""RBAC matrix for the leave viewset.

Contract (leave row): student **RW(self)**, parent **approve(child)**, faculty
**RW(self) + approve(students)**, hod **approve**, principal **R**, admin
**RW**. Concretely:

- ``list``/``retrieve`` (own requests) — any authenticated role; the view scopes
  the queryset to the requester (staff/parent see the requests they can act on).
- ``create`` (apply) — anyone who can file leave: student/parent/faculty/hod +
  admins. (Principal is read-only per the matrix.)
- ``approve``/``reject`` — parent/faculty/hod + admins; object-level scoping in
  the service enforces *whose* leave each approver may decide (parent→child,
  faculty/hod→students in their department, admin→all).
- ``update``/``destroy`` — the owner refines their own pending request; admins
  may manage any.
"""
from core.permissions import Role

ADMINS = list(Role.ADMINS)

# Roles that may file a leave request.
APPLICANTS = [Role.STUDENT, Role.PARENT, Role.FACULTY, Role.HOD, *Role.ADMINS]
# Roles that may approve/reject (subject to object-level scoping in the service).
APPROVERS = [Role.PARENT, Role.FACULTY, Role.HOD, *Role.ADMINS]

LEAVE_MATRIX = {
    # Reads: any authenticated role (queryset scoped in the view).
    "list": list(Role.ALL),
    "retrieve": list(Role.ALL),
    # Apply.
    "create": APPLICANTS,
    # Owner-managed edits (+ admins); object scoping refined in the view.
    "update": [Role.STUDENT, Role.PARENT, Role.FACULTY, Role.HOD, *Role.ADMINS],
    "partial_update": [Role.STUDENT, Role.PARENT, Role.FACULTY, Role.HOD, *Role.ADMINS],
    "destroy": [Role.STUDENT, Role.PARENT, Role.FACULTY, Role.HOD, *Role.ADMINS],
    # Approval workflow.
    "approve": APPROVERS,
    "reject": APPROVERS,
}
