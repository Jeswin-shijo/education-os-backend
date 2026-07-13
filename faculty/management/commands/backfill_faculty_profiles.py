"""Backfill missing ``FacultyProfile`` rows for existing faculty users.

Every faculty/HOD user should have a :class:`~faculty.models.FacultyProfile`
(they are auto-provisioned at registration and on subject assignment). Users
created before that was true can be left without one, which hides them from
profile-backed features. This command creates the missing rows.

``FacultyProfile.department`` is required and ``on_delete=PROTECT``, so this
command **never guesses** a department: it only backfills a faculty user whose
department can be inferred from a subject they already teach (the legacy
``Subject.faculty`` FK). Anyone who cannot be placed is reported and skipped —
they get a profile lazily the first time they are assigned to a subject.

Idempotent: profiles are created via ``get_or_create``. Use ``--dry-run`` to
preview without writing.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from core.permissions import Role


class Command(BaseCommand):
    help = "Create missing FacultyProfile rows for existing faculty/HOD users."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from accounts.models import User
        from academics.models import Subject
        from faculty.models import FacultyProfile

        dry_run = options["dry_run"]

        missing = (
            User.objects.filter(role__in=[Role.FACULTY, Role.HOD])
            .exclude(faculty_profile__isnull=False)
            .order_by("full_name")
        )

        created = 0
        skipped = []
        for user in missing:
            # Infer department from a subject this faculty already teaches.
            dept_id = (
                Subject.objects.filter(faculty=user)
                .values_list("department_id", flat=True)
                .first()
            )
            if dept_id is None:
                skipped.append(user)
                continue

            if dry_run:
                self.stdout.write(
                    f"  would create profile for {user.full_name} "
                    f"(dept {dept_id})"
                )
            else:
                FacultyProfile.objects.get_or_create(
                    user=user, defaults={"department_id": dept_id}
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  created profile for {user.full_name}"
                    )
                )
            created += 1

        for user in skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"  skipped {user.full_name} — no department can be inferred "
                    f"(will get a profile when first assigned to a subject)"
                )
            )

        verb = "would create" if dry_run else "created"
        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone: {verb} {created} profile(s), skipped {len(skipped)}."
            )
        )

        if dry_run:
            # Nothing was written, but be explicit and unwind the atomic block.
            transaction.set_rollback(True)
