"""The administration app is a thin admin-console layer.

It defines **no models of its own** — it aggregates and manages records that
already live in other apps:

- ``core.AuditLog`` — browsed read-only through ``GET /admin/audit-logs``.
- ``accounts.User`` — managed (list/create/role/activate) through
  ``/admin/users`` (reusing ``accounts`` services + repository).
- system-wide counts across every domain app for ``GET /admin/dashboard``.
- the RBAC matrix from ``core.permissions`` exposed via
  ``/admin/roles`` and ``/admin/permissions``.

Keeping this module model-free avoids a duplicate ``django.contrib.admin``-style
schema and keeps the admin console a pure read/aggregate + reuse layer.
"""
