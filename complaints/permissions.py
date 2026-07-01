"""RBAC matrix for the complaints viewset.

Contract (complaints row): student **RW(self)**, parent **RW(child)**, faculty
**R**, hod **R**, principal **R(monitor)**, admin **RW**. Concretely:

- ``list`` / ``retrieve`` — any authenticated role. Students/parents are scoped
  to their own complaints in the view; staff see the wider scope.
- ``create`` (``POST /complaints``) — the members who raise complaints
  (students + parents) plus admins.
- ``partial_update`` (``PATCH /complaints/{id}`` status transition) — staff only
  (they run the workflow); admins included.
- ``monitor`` (``GET /complaints/monitor``) — principal + admins only.
"""
from core.permissions import Role

ADMINS = list(Role.ADMINS)
ALL_ROLES = list(Role.ALL)

# Members who can raise a complaint.
COMPLAINANTS = [Role.STUDENT, Role.PARENT, *Role.ADMINS]
# Staff who run the status workflow (faculty/hod/principal + admins).
WORKFLOW_STAFF = [Role.FACULTY, Role.HOD, Role.PRINCIPAL, *Role.ADMINS]
# Institution monitors.
MONITORS = [Role.PRINCIPAL, *Role.ADMINS]

COMPLAINT_MATRIX = {
    # Reads: any authenticated role (object scoping applied in the view).
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    # Complainants file new complaints.
    "create": COMPLAINANTS,
    # Staff run the status workflow.
    "update": WORKFLOW_STAFF,
    "partial_update": WORKFLOW_STAFF,
    # No hard-delete surface for complaints; admins only if ever used.
    "destroy": ADMINS,
    # Principal/Admin institution monitor.
    "monitor": MONITORS,
}
