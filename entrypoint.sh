#!/bin/sh
set -e

# Wait for Postgres to accept connections (only when configured)
if [ -n "$POSTGRES_HOST" ]; then
  echo "Waiting for Postgres at $POSTGRES_HOST:${POSTGRES_PORT:-5432} ..."
  while ! nc -z "$POSTGRES_HOST" "${POSTGRES_PORT:-5432}"; do
    sleep 0.5
  done
  echo "Postgres is up."
fi

# Migrate/collectstatic/superuser/seed happen once per deploy from the web
# process. This same image+entrypoint also boots the Celery worker (see
# docker-compose.yml), which would otherwise race the web container on
# migrations — so we skip init only for the worker. We match on the whole
# command ($*), not $1, because the Dockerfile CMD is shell-form: Docker
# runs it as `/bin/sh -c "gunicorn ..."`, so $1 is "/bin/sh", never "gunicorn".
case "$*" in
  *"celery "*worker*|*"celery "*beat*) RUN_DB_INIT=0 ;;
  *) RUN_DB_INIT=1 ;;
esac

if [ "$RUN_DB_INIT" = "1" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput

  # Create OR reset the admin account from env on every boot. We deliberately
  # do NOT use `createsuperuser --noinput`: it errors on an already-existing
  # user and can never fix a bad/unusable password — which strands you with no
  # way to log in on a no-seed DB. This upsert is idempotent: it creates the
  # user when missing and otherwise resets its password, role, and flags. The
  # password is read from os.environ *inside* Python so shell quoting can never
  # mangle special characters. No-op unless both EMAIL and PASSWORD are set.
  if [ "$DJANGO_CREATE_SUPERUSER" = "true" ] && [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "Ensuring superuser '$DJANGO_SUPERUSER_EMAIL' exists (create or reset) ..."
    python manage.py shell -c "import os; from accounts.models import User; email=os.environ['DJANGO_SUPERUSER_EMAIL']; u,created=User.all_objects.get_or_create(email=email, defaults={'full_name': os.environ.get('DJANGO_SUPERUSER_FULL_NAME') or 'Admin'}); u.full_name = u.full_name or os.environ.get('DJANGO_SUPERUSER_FULL_NAME') or 'Admin'; u.role='super_admin'; u.is_active=True; u.is_staff=True; u.is_superuser=True; u.is_deleted=False; u.set_password(os.environ['DJANGO_SUPERUSER_PASSWORD']); u.save(); print('superuser', 'created' if created else 'reset', u.email, u.role)"
  fi

  # Optional demo data (9 role logins, password campus123) so a fresh database
  # has something to log in with. Idempotent — safe to leave on, but you can
  # unset DJANGO_SEED_DEMO once you have real data.
  if [ "$DJANGO_SEED_DEMO" = "true" ]; then
    echo "Seeding demo data ..."
    python manage.py seed_demo || true
  fi
fi

exec "$@"
