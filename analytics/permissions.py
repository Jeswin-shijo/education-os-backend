"""RBAC for the analytics endpoints.

Two role gates, matching the contract's analytics/reports row:

* ``/hod/*`` — HOD only (department-scoped reads).
* ``/principal/*`` — Principal and Admins (institution-wide reads).

The analytics ``APIView``s are read-only (``GET`` only), so a single
``HasRole`` gate per surface is sufficient; there is no per-action matrix.
"""
from core.permissions import HasRole, Role

# HOD department analytics.
IsHod = HasRole(Role.HOD)

# Principal institution analytics — principal plus super-admin/admin oversight.
IsPrincipalOrAdmin = HasRole(Role.PRINCIPAL, Role.ADMIN, Role.SUPER_ADMIN)
