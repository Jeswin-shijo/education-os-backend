"""Background jobs for the materials app.

Materials have no long-running request-path work today. ``notify_class_material``
is provided as a Celery hook so a class can be notified off-request when new
material is shared (wired to the notifications module at integrate time).
"""
from __future__ import annotations

from celery import shared_task

from materials.models import Material


@shared_task(name="materials.notify_class_material")
def notify_class_material(material_id: str) -> str:
    """Placeholder: announce a newly shared material to its class.

    Returns the material id it processed (a no-op until the notifications
    module is wired in). Kept off the request path per the Celery contract.
    """
    material = Material.objects.filter(pk=material_id).first()
    if material is None:
        return ""
    # Integrate step will enqueue push/notification fan-out here.
    return str(material.pk)
