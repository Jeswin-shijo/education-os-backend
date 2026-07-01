"""Dashboards app — models.

The dashboards app is a **read-only aggregation layer**: it composes the other
domain apps' data (students, attendance, exams, assignments, academics/timetable,
fees, notifications, guardians, faculty, quizzes, chat) into the per-role
dashboard shapes the mobile app expects, and caches each result in Redis.

It therefore defines **no models of its own** — there is nothing to persist. All
writes (and their audit rows) happen in the source apps' services; this app only
reads and caches. Cache invalidation is documented in :mod:`dashboards.services`.
"""
