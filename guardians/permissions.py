"""RBAC matrix for the guardians viewset.

Contract: parent **R own** links; admin **full**. Concretely:

- Admin/super-admin get full CRUD over :class:`~guardians.models.ParentLink`
  rows and may list every link.
- The self-scoped ``children`` action is open to authenticated parents (and
  admins for support); object-level scoping to "own" links is applied in the
  view (a parent only ever sees their own children).

List/retrieve of the raw link table is admin-only — parents read their children
through the dedicated ``/parent/children`` action, not the CRUD list.
"""
from core.permissions import Role

ADMINS = list(Role.ADMINS)

PARENT_LINK_MATRIX = {
    "list": ADMINS,
    "retrieve": ADMINS,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
    # self-scoped custom action: parents read their own children.
    "children": ADMINS + [Role.PARENT],
}
