"""Celery tasks for the administration app.

The admin console is a synchronous read/aggregate + management layer, so it has
no long-running background jobs today. This module exists to keep the standard
app file-set complete and gives a home for future exports (e.g. audit-log CSV
exports, scheduled admin reports) enqueued from the service layer.
"""
