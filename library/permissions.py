"""RBAC matrices for the library viewsets.

Per the BUILD_CONTRACT matrix, ``library`` is **read for everyone** and
**read-write for admins**: every authenticated role may browse the catalogue and
their own loans; only super_admin/admin may mutate books/loans.
"""
from core.permissions import Role

ADMINS = list(Role.ADMINS)      # super_admin, admin
ALL_ROLES = list(Role.ALL)

# Book catalogue: all roles read; admins write. The ``books`` custom action is
# the app-facing GET /library/books search and is open to every role.
BOOK_MATRIX = {
    "list": ALL_ROLES,
    "retrieve": ALL_ROLES,
    "books": ALL_ROLES,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
}

# Loans: admins manage the full loan table; the ``loans`` custom action serves
# the requesting student's own loans and is reachable by any authenticated role
# (object scoping in the action limits non-staff to their own records).
LOAN_MATRIX = {
    "list": ADMINS,
    "retrieve": ADMINS,
    "loans": ALL_ROLES,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
}
