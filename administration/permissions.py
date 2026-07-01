"""RBAC matrices for the administration app.

Every admin-console endpoint is restricted to :data:`core.permissions.Role.ADMINS`
(``super_admin`` / ``admin``). The matrices below plug into
:class:`core.permissions.RoleModelPermission` on each view.
"""
from core.permissions import Role

# All admin-console surfaces: admins only, for every action.
ADMIN_ONLY_MATRIX = {"*": list(Role.ADMINS)}
