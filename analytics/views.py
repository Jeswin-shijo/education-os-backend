"""HTTP layer for the analytics app — read-only aggregation endpoints.

Two role surfaces, each a set of thin ``APIView``s that delegate to a service
(which caches under the ``analytics`` prefix, TTL 300s) and return the app-shaped
dict inside the standard envelope:

HOD (department-scoped; role ``hod``):
    ``GET /api/v1/hod/dashboard``    — department rollup (``HodDashboard``)
    ``GET /api/v1/hod/me``           — HOD profile (``HodProfile``)
    ``GET /api/v1/hod/faculty``      — faculty performance list
    ``GET /api/v1/hod/faculty/{id}`` — one faculty's performance
    ``GET /api/v1/hod/students``     — student performance + grade bands
    ``GET /api/v1/hod/attendance``   — attendance analytics

Principal (institution-wide; roles ``principal``/``admin``/``super_admin``):
    ``GET /api/v1/principal/dashboard``   — institution rollup
    ``GET /api/v1/principal/me``          — principal profile
    ``GET /api/v1/principal/students``    — student analytics
    ``GET /api/v1/principal/faculty``     — faculty analytics
    ``GET /api/v1/principal/fees``        — fee analytics
    ``GET /api/v1/principal/placements``  — placement analytics
    ``GET /api/v1/principal/complaints``  — complaint monitoring
    ``GET /api/v1/principal/insights``    — AI-style insight cards

Every endpoint is ``GET`` only — the analytics app performs no writes.
"""
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics import serializers as s
from analytics.permissions import IsHod, IsPrincipalOrAdmin
from analytics.services import HodAnalyticsService, PrincipalAnalyticsService


# ============================================================================
# HOD (department-scoped)
# ============================================================================
class _HodView(APIView):
    permission_classes = [IsAuthenticated, IsHod]

    def service(self, request) -> HodAnalyticsService:
        return HodAnalyticsService(request.user)


class HodDashboardView(_HodView):
    @extend_schema(responses={200: s.HodDashboardSerializer}, tags=["HOD Analytics"])
    def get(self, request):
        return Response(self.service(request).dashboard())


class HodProfileView(_HodView):
    @extend_schema(responses={200: s.HodProfileSerializer}, tags=["HOD Analytics"])
    def get(self, request):
        return Response(self.service(request).profile())


class HodFacultyView(_HodView):
    @extend_schema(
        responses={200: s.FacultyPerformanceSerializer(many=True)},
        tags=["HOD Analytics"],
    )
    def get(self, request):
        return Response(self.service(request).faculty_performance())


class HodFacultyDetailView(_HodView):
    @extend_schema(
        responses={200: s.FacultyPerformanceSerializer}, tags=["HOD Analytics"]
    )
    def get(self, request, faculty_id):
        detail = self.service(request).faculty_detail(faculty_id)
        if detail is None:
            raise NotFound("Faculty not found in your department.")
        return Response(detail)


class HodStudentsView(_HodView):
    @extend_schema(
        responses={200: s.StudentPerformanceSerializer}, tags=["HOD Analytics"]
    )
    def get(self, request):
        return Response(self.service(request).student_performance())


class HodAttendanceView(_HodView):
    @extend_schema(
        responses={200: s.AttendanceAnalyticsSerializer}, tags=["HOD Analytics"]
    )
    def get(self, request):
        return Response(self.service(request).attendance_analytics())


# ============================================================================
# Principal (institution-wide)
# ============================================================================
class _PrincipalView(APIView):
    permission_classes = [IsAuthenticated, IsPrincipalOrAdmin]

    def service(self, request) -> PrincipalAnalyticsService:
        return PrincipalAnalyticsService(request.user)


class PrincipalDashboardView(_PrincipalView):
    @extend_schema(
        responses={200: s.PrincipalDashboardSerializer}, tags=["Principal Analytics"]
    )
    def get(self, request):
        return Response(self.service(request).dashboard())


class PrincipalProfileView(_PrincipalView):
    @extend_schema(
        responses={200: s.PrincipalProfileSerializer}, tags=["Principal Analytics"]
    )
    def get(self, request):
        return Response(self.service(request).profile())


class PrincipalStudentsView(_PrincipalView):
    @extend_schema(
        responses={200: s.PrincipalStudentAnalyticsSerializer},
        tags=["Principal Analytics"],
    )
    def get(self, request):
        return Response(self.service(request).student_analytics())


class PrincipalFacultyView(_PrincipalView):
    @extend_schema(
        responses={200: s.PrincipalFacultyAnalyticsSerializer},
        tags=["Principal Analytics"],
    )
    def get(self, request):
        return Response(self.service(request).faculty_analytics())


class PrincipalFeesView(_PrincipalView):
    @extend_schema(
        responses={200: s.PrincipalFeeAnalyticsSerializer},
        tags=["Principal Analytics"],
    )
    def get(self, request):
        return Response(self.service(request).fee_analytics())


class PrincipalPlacementsView(_PrincipalView):
    @extend_schema(
        responses={200: s.PrincipalPlacementAnalyticsSerializer},
        tags=["Principal Analytics"],
    )
    def get(self, request):
        return Response(self.service(request).placement_analytics())


class PrincipalComplaintsView(_PrincipalView):
    @extend_schema(
        responses={200: s.PrincipalComplaintMonitoringSerializer},
        tags=["Principal Analytics"],
    )
    def get(self, request):
        return Response(self.service(request).complaint_monitoring())


class PrincipalInsightsView(_PrincipalView):
    @extend_schema(
        responses={200: s.InsightCardSerializer(many=True)},
        tags=["Principal Analytics"],
    )
    def get(self, request):
        return Response(self.service(request).ai_insights())
