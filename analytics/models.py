"""Analytics app — read-only aggregation only.

This module owns **no** database tables. Every endpoint aggregates over the
existing domain apps (``academics``, ``students``, ``faculty``, ``attendance``,
``exams``, ``fees``, ``placement``, ``complaints``) and returns cached
(TTL 300s) rollups shaped to the mobile app's ``hodService`` / ``principalService``
contracts. The heavy lifting lives in :mod:`analytics.repositories` (data access)
and :mod:`analytics.services` (aggregation), consumed by thin ``APIView``s in
:mod:`analytics.views`.

There are intentionally no models here.
"""
