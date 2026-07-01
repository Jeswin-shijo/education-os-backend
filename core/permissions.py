"""RBAC building blocks.

- :class:`Role` — the seven canonical role string constants.
- :func:`HasRole` — factory returning a permission that admits the given roles.
- :class:`RoleModelPermission` — maps a view action to allowed roles via a
  ``permission_matrix`` dict declared on the view.
- Convenience classes: :class:`IsAdmin`, :class:`IsStaffRole`, :class:`IsSelfOrStaff`.
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission


class Role:
    """Canonical role constants (one source of truth across the codebase)."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    PRINCIPAL = "principal"
    HOD = "hod"
    FACULTY = "faculty"
    PARENT = "parent"
    STUDENT = "student"

    ALL = (SUPER_ADMIN, ADMIN, PRINCIPAL, HOD, FACULTY, PARENT, STUDENT)
    # Roles that operate on institutional data rather than a single learner.
    STAFF = (SUPER_ADMIN, ADMIN, PRINCIPAL, HOD, FACULTY)
    ADMINS = (SUPER_ADMIN, ADMIN)

    CHOICES = [
        (SUPER_ADMIN, "Super Admin"),
        (ADMIN, "Admin"),
        (PRINCIPAL, "Principal"),
        (HOD, "HOD"),
        (FACULTY, "Faculty"),
        (PARENT, "Parent"),
        (STUDENT, "Student"),
    ]


def _role_of(user) -> str | None:
    return getattr(user, "role", None)


def HasRole(*roles: str) -> type[BasePermission]:
    """Return a permission class admitting authenticated users in ``roles``."""

    allowed = set(roles)

    class _HasRole(BasePermission):
        message = "You do not have the required role for this action."

        def has_permission(self, request, view):
            user = request.user
            return bool(
                user
                and user.is_authenticated
                and _role_of(user) in allowed
            )

    _HasRole.__name__ = "HasRole_" + "_".join(sorted(allowed)) if allowed else "HasRole_none"
    return _HasRole


class RoleModelPermission(BasePermission):
    """Action-aware permission driven by a per-view ``permission_matrix``.

    On the view declare::

        permission_matrix = {
            "list":    [Role.ADMIN, Role.FACULTY],
            "retrieve":[Role.ADMIN, Role.FACULTY, Role.STUDENT],
            "create":  [Role.ADMIN],
            "*":       [Role.ADMIN],   # fallback for unlisted actions
        }

    For non-viewset views without an ``action``, the HTTP method name
    (lowercased) is used as the key, with ``read``/``write`` group fallbacks.
    """

    message = "You do not have permission to perform this action."

    def _matrix(self, view) -> dict | None:
        return getattr(view, "permission_matrix", None)

    def _action_key(self, request, view) -> str:
        action = getattr(view, "action", None)
        if action:
            return action
        return request.method.lower()

    def _allowed_roles(self, matrix: dict, request, view):
        key = self._action_key(request, view)
        if key in matrix:
            return matrix[key]
        # Group fallbacks.
        if request.method in SAFE_METHODS and "read" in matrix:
            return matrix["read"]
        if request.method not in SAFE_METHODS and "write" in matrix:
            return matrix["write"]
        return matrix.get("*")

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        matrix = self._matrix(view)
        if matrix is None:
            # No matrix declared -> authenticated is sufficient.
            return True
        allowed = self._allowed_roles(matrix, request, view)
        if allowed is None:
            return False
        return _role_of(user) in set(allowed)


class IsAdmin(BasePermission):
    """Admin or super-admin only."""

    message = "Administrator access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and _role_of(user) in set(Role.ADMINS)
        )


class IsStaffRole(BasePermission):
    """Any staff-side role (super_admin/admin/principal/hod/faculty)."""

    message = "Staff access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and _role_of(user) in set(Role.STAFF)
        )


class IsSelfOrStaff(BasePermission):
    """Object-level: the owner of the object, or any staff role.

    Objects are matched by ``user``/``owner`` FK or by the object being the user.
    """

    message = "You can only access your own resource."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if _role_of(user) in set(Role.STAFF):
            return True
        owner = getattr(obj, "user", None) or getattr(obj, "owner", None)
        if owner is not None:
            return owner == user
        return obj == user
