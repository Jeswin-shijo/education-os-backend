"""Accounts-specific permissions (re-exporting the shared RBAC primitives)."""
from core.permissions import (  # noqa: F401  (re-exported for convenience)
    HasRole,
    IsAdmin,
    IsSelfOrStaff,
    IsStaffRole,
    Role,
    RoleModelPermission,
)

# Only admins/super-admins may register (create) new users.
CanRegisterUser = IsAdmin
