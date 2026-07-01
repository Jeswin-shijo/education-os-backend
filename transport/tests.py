"""Transport endpoint tests: happy path + permission/validation cases.

The module's routes are not mounted in ``config/urls`` until the integrate step,
so these tests mount the router under a local ``ROOT_URLCONF`` for isolation.
"""
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path, reverse
from rest_framework.test import APITestCase

from core.permissions import Role

from transport.models import BusLiveStatus, BusRoute, BusStop
from transport.urls import router

User = get_user_model()

# Local urlconf mounting the transport router at the root for tests.
urlpatterns = [path("", include((router.urls, "transport"), namespace="transport"))]


@override_settings(ROOT_URLCONF=__name__)
class TransportAPITests(APITestCase):
    def setUp(self):
        pwd = "Str0ng-Pass!23"
        self.admin = User.objects.create_user(
            email="admin@example.com", password=pwd, full_name="Admin", role=Role.ADMIN
        )
        self.student = User.objects.create_user(
            email="abin@example.com", password=pwd, full_name="Abin", role=Role.STUDENT
        )

        self.route = BusRoute.objects.create(
            name="City Center Loop", number="R1",
            driver="Suresh", driver_phone="+91-99999-00000",
        )
        BusStop.objects.create(route=self.route, name="Main Gate", time="08:00", order=1)
        BusStop.objects.create(route=self.route, name="Library", time="08:15", order=2)
        self.live = BusLiveStatus.objects.create(
            route=self.route, current_stop="Main Gate", next_stop="Library",
            eta_mins=7, occupancy=42, lat=10.5, lng=76.2,
        )

    # -- reads open to any authenticated role ----------------------------
    def test_list_routes_app_shape(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(reverse("transport:busroute-list"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        route = data[0]
        # App-shaped BusRoute: camelCase `driverPhone`, nested `stops`.
        self.assertEqual(route["number"], "R1")
        self.assertEqual(route["driverPhone"], "+91-99999-00000")
        self.assertEqual(len(route["stops"]), 2)
        self.assertEqual(route["stops"][0], {"name": "Main Gate", "time": "08:00"})

    def test_list_requires_auth(self):
        self.assertEqual(
            self.client.get(reverse("transport:busroute-list")).status_code, 401
        )

    def test_route_live_app_shape(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(
            reverse("transport:busroute-live", args=[self.route.id])
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        # App-shaped BusLiveStatus: camelCase keys, routeId string.
        self.assertEqual(data["routeId"], str(self.route.id))
        self.assertEqual(data["currentStop"], "Main Gate")
        self.assertEqual(data["nextStop"], "Library")
        self.assertEqual(data["etaMins"], 7)
        self.assertEqual(data["occupancy"], 42)

    def test_route_live_404_when_absent(self):
        route2 = BusRoute.objects.create(name="No Live", number="R2")
        self.client.force_authenticate(self.student)
        resp = self.client.get(reverse("transport:busroute-live", args=[route2.id]))
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.json()["success"])

    # -- write RBAC ------------------------------------------------------
    def test_student_cannot_create_route(self):
        self.client.force_authenticate(self.student)
        resp = self.client.post(
            reverse("transport:busroute-list"),
            {"name": "New", "number": "R9"}, format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_create_route_and_it_is_audited(self):
        from core.models import AuditLog

        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("transport:busroute-list"),
            {"name": "New Route", "number": "R9", "driver": "Ravi",
             "driver_phone": "+91-88888-00000"}, format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(BusRoute.objects.filter(number="R9").exists())
        self.assertTrue(
            AuditLog.objects.filter(entity="BusRoute", action="create").exists()
        )

    def test_create_route_validation_error(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            reverse("transport:busroute-list"),
            {"name": "Missing Number"}, format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])
