"""Library URLs. ``config/urls.py`` mounts this under ``/api/v1/`` so the paths
resolve to:

* ``GET  /api/v1/library/books``        — app-shaped catalogue search (``?q=``)
* ``GET  /api/v1/library/loans``        — requesting student's own loans
* ``GET/POST/PATCH/DELETE /api/v1/library/books-admin/…`` — admin book CRUD
* ``…/library/loans-admin/…``           — admin loan management

The app-facing ``books``/``loans`` reads are bound as explicit collection routes
so their paths match the mobile contract exactly; the admin CRUD resources live
under distinct basenames to avoid colliding with those fixed paths.
"""
from django.urls import path
from rest_framework.routers import DefaultRouter

from library.views import BookLoanViewSet, BookViewSet

app_name = "library"

router = DefaultRouter()
router.register("library/books-admin", BookViewSet, basename="book")
router.register("library/loans-admin", BookLoanViewSet, basename="book-loan")

urlpatterns = [
    path(
        "library/books",
        BookViewSet.as_view({"get": "books"}),
        name="book-search",
    ),
    path(
        "library/loans",
        BookLoanViewSet.as_view({"get": "loans"}),
        name="loan-list",
    ),
    *router.urls,
]
