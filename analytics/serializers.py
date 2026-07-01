"""Response serializers for the analytics endpoints.

The analytics services already return plain, app-shaped dicts (matching the
mobile ``hodService`` / ``principalService`` types), so these serializers exist
mainly to document the response schemas in Swagger via ``@extend_schema``. Each
mirrors a ``types.ts`` / service-local shape referenced in the migration guide.

No input serializers are needed — every analytics endpoint is a ``GET`` with no
request body.
"""
from rest_framework import serializers


# -- shared primitives -------------------------------------------------------
class UserLiteSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()
    avatarColor = serializers.CharField()
    phone = serializers.CharField(required=False, allow_blank=True)


class GradeBandSerializer(serializers.Serializer):
    band = serializers.CharField()
    count = serializers.IntegerField()


class TrendPointSerializer(serializers.Serializer):
    label = serializers.CharField()
    percent = serializers.FloatField()


class NamedPercentSerializer(serializers.Serializer):
    subject = serializers.CharField()
    percent = serializers.FloatField()


class StudentPerfEntrySerializer(serializers.Serializer):
    name = serializers.CharField()
    rollNo = serializers.CharField()
    percent = serializers.FloatField()


class CodeCountSerializer(serializers.Serializer):
    code = serializers.CharField()
    count = serializers.IntegerField()


class StatusCountSerializer(serializers.Serializer):
    status = serializers.CharField()
    count = serializers.IntegerField()


class FacultyPerformanceSerializer(serializers.Serializer):
    facultyId = serializers.CharField()
    name = serializers.CharField()
    avatarColor = serializers.CharField()
    designation = serializers.CharField()
    subjects = serializers.ListField(child=serializers.CharField())
    classCount = serializers.IntegerField()
    studentCount = serializers.IntegerField()
    avgMarksPercent = serializers.FloatField()
    sessionsMarked = serializers.IntegerField()


# -- HOD ---------------------------------------------------------------------
class HodProfileSerializer(serializers.Serializer):
    hod = UserLiteSerializer()
    department = serializers.CharField()
    facultyCount = serializers.IntegerField()
    studentCount = serializers.IntegerField()


class HodDashboardSerializer(serializers.Serializer):
    department = serializers.CharField()
    facultyCount = serializers.IntegerField()
    studentCount = serializers.IntegerField()
    classCount = serializers.IntegerField()
    avgAttendancePercent = serializers.FloatField()
    avgMarksPercent = serializers.FloatField()
    passRatePercent = serializers.FloatField()
    lowAttendanceCount = serializers.IntegerField()
    topFaculty = FacultyPerformanceSerializer(allow_null=True)
    attendanceTrend = TrendPointSerializer(many=True)


class StudentPerformanceSerializer(serializers.Serializer):
    gradeBands = GradeBandSerializer(many=True)
    topPerformers = StudentPerfEntrySerializer(many=True)
    atRisk = StudentPerfEntrySerializer(many=True)


class AttendanceAnalyticsSerializer(serializers.Serializer):
    overallPercent = serializers.FloatField()
    trend = TrendPointSerializer(many=True)
    bySubject = NamedPercentSerializer(many=True)
    lowStudents = StudentPerfEntrySerializer(many=True)


# -- Principal ---------------------------------------------------------------
class DepartmentCardSerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()
    studentCount = serializers.IntegerField()
    facultyCount = serializers.IntegerField()
    avgAttendance = serializers.FloatField()
    avgCgpa = serializers.FloatField()
    passRate = serializers.FloatField()
    color = serializers.CharField()


class AdmissionPointSerializer(serializers.Serializer):
    year = serializers.CharField()
    count = serializers.IntegerField()


class PrincipalProfileSerializer(serializers.Serializer):
    principal = UserLiteSerializer()
    institution = serializers.CharField()


class PrincipalDashboardSerializer(serializers.Serializer):
    institution = serializers.CharField()
    totalStudents = serializers.IntegerField()
    totalFaculty = serializers.IntegerField()
    departmentCount = serializers.IntegerField()
    avgAttendance = serializers.FloatField()
    avgCgpa = serializers.FloatField()
    passRate = serializers.FloatField()
    feeCollectedPercent = serializers.FloatField()
    placementRatePercent = serializers.FloatField()
    departments = DepartmentCardSerializer(many=True)
    admissionsTrend = AdmissionPointSerializer(many=True)


class PrincipalStudentAnalyticsSerializer(serializers.Serializer):
    totalStudents = serializers.IntegerField()
    byDepartment = CodeCountSerializer(many=True)
    gradeBands = GradeBandSerializer(many=True)
    atRiskCount = serializers.IntegerField()


class PrincipalFacultyAnalyticsSerializer(serializers.Serializer):
    totalFaculty = serializers.IntegerField()
    byDepartment = CodeCountSerializer(many=True)
    topPerformers = FacultyPerformanceSerializer(many=True)


class FeeCollectionPointSerializer(serializers.Serializer):
    term = serializers.CharField()
    collected = serializers.FloatField()
    target = serializers.FloatField()


class PrincipalFeeAnalyticsSerializer(serializers.Serializer):
    collection = FeeCollectionPointSerializer(many=True)
    totalCollected = serializers.FloatField()
    totalTarget = serializers.FloatField()
    collectionPercent = serializers.FloatField()


class PlacementSummarySerializer(serializers.Serializer):
    placed = serializers.IntegerField()
    eligible = serializers.IntegerField()
    avgCtcLpa = serializers.FloatField()
    highestCtcLpa = serializers.FloatField()
    topRecruiters = serializers.ListField(child=serializers.CharField())


class PrincipalPlacementAnalyticsSerializer(serializers.Serializer):
    summary = PlacementSummarySerializer()
    ratePercent = serializers.FloatField()
    openings = serializers.IntegerField()


class ComplaintLiteSerializer(serializers.Serializer):
    id = serializers.CharField()
    category = serializers.CharField()
    subject = serializers.CharField()
    description = serializers.CharField()
    status = serializers.CharField()
    createdOn = serializers.CharField(allow_null=True)


class PrincipalComplaintMonitoringSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    byStatus = StatusCountSerializer(many=True)
    recent = ComplaintLiteSerializer(many=True)


class InsightCardSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    body = serializers.CharField()
    tone = serializers.ChoiceField(choices=["info", "success", "warning", "danger"])
    metric = serializers.CharField(required=False)
