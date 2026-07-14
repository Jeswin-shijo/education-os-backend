"""I/O serializers for the dashboards app.

These are **output-only** serializers that shape the aggregated dashboard
payloads into the exact camelCase objects the mobile app expects
(``studentService.StudentDashboard``, ``parentService.ParentDashboard``,
``facultyService.FacultyDashboard``). They reuse the source apps' app-shaped
serializers for nested domain objects (``Student``/``ClassSession``/``Exam``/
``FacultyClass``) so a dashboard field is byte-for-byte identical to the same
object served by its own endpoint.

The services build plain dicts already in the right shape; these serializers
document the contract (and drive drf-spectacular's OpenAPI schema). The dict the
service produces is passed straight through the matching ``*Serializer`` for a
final, schema-validated shape.
"""
from rest_framework import serializers

from academics.serializers import ClassSessionAppSerializer
from exams.serializers import ExamAppSerializer
from faculty.serializers import FacultyClassAppSerializer
from students.serializers import StudentAppSerializer


# --- Mobile API contract v1: GET /dashboard/student/{user_id} ----------------
class NextExamSpecSerializer(serializers.Serializer):
    """The ``next_exam`` block of the contract student dashboard."""

    subject = serializers.CharField(allow_blank=True)
    time = serializers.CharField(allow_blank=True)
    room = serializers.CharField(allow_blank=True)


class StudentDashboardSpecSerializer(serializers.Serializer):
    """Spec-exact (snake_case) shape for ``GET /api/v1/dashboard/student/{user_id}``.

    Matches ``API_CONTRACT_V1`` §Dashboard:
    ``{ student_name, roll_no, department, program, semester, attendance_percentage,
    cgpa, pending_fees, pending_approvals, unread_chats, next_exam:{subject,time,room} }``.
    """

    student_name = serializers.CharField()
    roll_no = serializers.CharField()
    department = serializers.CharField(allow_blank=True)
    program = serializers.CharField(allow_blank=True)
    semester = serializers.IntegerField()
    attendance_percentage = serializers.IntegerField()
    cgpa = serializers.FloatField()
    pending_fees = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_approvals = serializers.IntegerField()
    unread_chats = serializers.IntegerField()
    next_exam = NextExamSpecSerializer(allow_null=True)


# --- Student dashboard -------------------------------------------------------
class StudentDashboardSerializer(serializers.Serializer):
    """Matches ``studentService.StudentDashboard``."""

    student = StudentAppSerializer()
    attendancePct = serializers.IntegerField()
    cgpa = serializers.FloatField()
    pendingAssignments = serializers.IntegerField()
    todayClasses = ClassSessionAppSerializer(many=True)
    dueFees = serializers.DecimalField(max_digits=12, decimal_places=2)
    unread = serializers.IntegerField()
    nextExam = ExamAppSerializer(required=False, allow_null=True)


# --- Parent dashboard --------------------------------------------------------
class ParentDashboardSerializer(serializers.Serializer):
    """Matches ``parentService.ParentDashboard``."""

    child = StudentAppSerializer()
    attendancePct = serializers.IntegerField()
    cgpa = serializers.FloatField()
    dueFees = serializers.DecimalField(max_digits=12, decimal_places=2)
    pendingApprovals = serializers.IntegerField()
    unreadChats = serializers.IntegerField()
    unreadNotifications = serializers.IntegerField()
    nextExam = ExamAppSerializer(required=False, allow_null=True)


# --- Faculty dashboard -------------------------------------------------------
class FacultyTodayEntrySerializer(serializers.Serializer):
    """One ``{ class, slot }`` entry in the faculty dashboard's todayClasses.

    Mirrors ``FacultyDashboard.todayClasses[n]`` — the faculty's class plus the
    single :class:`~faculty.models.FacultyClass` slot scheduled for today.
    """

    def to_representation(self, instance):
        return instance  # already-shaped dict from the service

    # Declared for OpenAPI documentation.
    _class = FacultyClassAppSerializer(source="class")
    slot = serializers.DictField()


class FacultyUserSerializer(serializers.Serializer):
    """The ``faculty`` user block of the faculty dashboard (``types.ts`` User)."""

    id = serializers.CharField()
    name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()
    avatarColor = serializers.CharField()


class FacultyDashboardSerializer(serializers.Serializer):
    """Matches ``facultyService.FacultyDashboard``."""

    faculty = FacultyUserSerializer()
    classCount = serializers.IntegerField()
    studentCount = serializers.IntegerField()
    todayClasses = serializers.ListField(child=serializers.DictField())
    pendingAssignments = serializers.IntegerField()
    quizCount = serializers.IntegerField()
    unreadNotifications = serializers.IntegerField()
