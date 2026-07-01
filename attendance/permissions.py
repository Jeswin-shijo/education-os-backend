"""RBAC matrices for the attendance viewsets.

Contract (BUILD_CONTRACT attendance row):
``student R(self) · parent R(child) · faculty RW(own classes) · hod R(dept) ·
principal R · admin RW``.

Concretely, self-scoped student reads (``/attendance/summary``, ``/overall``,
``/records``) are open to any authenticated user; the view scopes the data to the
requesting user's own :class:`students.Student` record. The faculty session
endpoints (``POST /attendance``, ``GET /faculty/attendance``) admit faculty +
admins; object-level owner-scoping to a faculty's own classes is enforced in the
view/service.
"""
from core.permissions import Role

ADMINS = list(Role.ADMINS)
STAFF = list(Role.STAFF)
# Anyone authenticated may hit the self-scoped student reads; the view narrows
# the result to the caller's own student profile.
SELF_READERS = list(Role.ALL)
# Faculty session read/write + admin.
FACULTY_WRITERS = [Role.SUPER_ADMIN, Role.ADMIN, Role.FACULTY]


# AttendanceRecord viewset: admin full CRUD; student/parent/staff read.
ATTENDANCE_RECORD_MATRIX = {
    "list": STAFF,
    "retrieve": STAFF,
    "create": ADMINS,
    "update": ADMINS,
    "partial_update": ADMINS,
    "destroy": ADMINS,
    # self-scoped student reads
    "summary": SELF_READERS,
    "overall": SELF_READERS,
    "records": SELF_READERS,
    # faculty session endpoints
    "create_session": FACULTY_WRITERS,
    "faculty_sessions": FACULTY_WRITERS,
}
