# AI Campus OS Backend — Build Contract

Concrete spec for the build. Read with `CLAUDE.md`. Phase 1 = Foundation (build + verify first).
Phase 2 = domain modules against the verified foundation.

Verification for every phase (SQLite, no Docker needed):
```
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python manage.py makemigrations && python manage.py migrate && python manage.py check
```

---

## Phase 1 — Foundation

### requirements.txt (replace with)
```
Django>=5.2,<5.3
djangorestframework>=3.15
djangorestframework-simplejwt>=5.3
psycopg[binary]>=3.2
django-redis>=5.4
redis>=5.0
celery>=5.4
django-celery-results>=2.5
django-celery-beat>=2.7
channels>=4.1
channels-redis>=4.2
drf-spectacular>=0.27
django-filter>=24.3
django-cors-headers>=4.4
django-storages>=1.14
boto3>=1.35
gunicorn>=23.0
whitenoise>=6.7
```

### config/settings.py (extend the existing file)
- `AUTH_USER_MODEL = "accounts.User"`.
- INSTALLED_APPS += `rest_framework`, `rest_framework_simplejwt.token_blacklist`, `django_filters`,
  `drf_spectacular`, `corsheaders`, `channels`, `django_celery_results`, `django_celery_beat`,
  then the local apps: `core`, `accounts`, and every module app (add as built).
- MIDDLEWARE: add `corsheaders.middleware.CorsMiddleware` (top, after security).
- `REST_FRAMEWORK`: default auth = `JWTAuthentication`; default permission = `IsAuthenticated`;
  `DEFAULT_RENDERER_CLASSES` = `core.renderers.EnvelopeJSONRenderer` (+ Browsable in DEBUG);
  `EXCEPTION_HANDLER = "core.exceptions.envelope_exception_handler"`;
  `DEFAULT_PAGINATION_CLASS = "core.pagination.StandardPagination"`, `PAGE_SIZE = 20`;
  `DEFAULT_FILTER_BACKENDS` = django_filter + Search + Ordering;
  `DEFAULT_THROTTLE_CLASSES/RATES` (anon 60/min, user 1000/day sensible defaults);
  `DEFAULT_SCHEMA_CLASS = "drf_spectacular.openapi.AutoSchema"`.
- `SIMPLE_JWT`: access 30 min, refresh 7 days, rotate + blacklist after rotation.
- `SPECTACULAR_SETTINGS`: title "AI Campus OS API", version "1.0.0".
- `CACHES`: default = `django_redis` at `REDIS_URL` (env, default `redis://localhost:6379/1`);
  if Redis env absent, fall back to LocMemCache so `check`/dev work offline.
- Celery: `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` from env (Redis), `django-celery-results`.
- Channels: `ASGI_APPLICATION = "config.asgi.application"`, `CHANNEL_LAYERS` = redis (fallback InMemory).
- `CORS_ALLOWED_ORIGINS` / `CORS_ALLOW_ALL_ORIGINS` (dev) from env.
- Storages: S3 (`storages.backends.s3.S3Boto3Storage`) when `USE_S3` env true, else FileSystem.
- Keep existing DB (Postgres when `POSTGRES_DB`, else SQLite) and security blocks.

### config/ wiring
- `config/celery.py`: Celery app `app = Celery("config")`, autodiscover tasks; import in `config/__init__.py`.
- `config/asgi.py`: `ProtocolTypeRouter` — http = Django ASGI; websocket = JWT-auth middleware →
  `URLRouter` of module `routing.py` websocket urlpatterns (start empty, modules append).
- `config/urls.py`: `/api/v1/` includes each module's `urls.py`; `/api/schema/`, `/api/docs/`
  (Swagger via spectacular), `/health/` (JSON `{status:"ok"}`, no auth), keep `/admin/`.
  Remove the template `courses` routes (that app is replaced by the `academics` module).

### core app (the shared foundation) — files
- **models.py**:
  - `TimeStampedUUIDModel`/`BaseModel` (abstract): `id = UUIDField(pk, default uuid4)`,
    `created_at(auto_now_add)`, `updated_at(auto_now)`, `created_by`/`updated_by`
    (`FK(settings.AUTH_USER_MODEL, null=True, related_name="+")`), `is_deleted(bool, default False, db_index)`,
    `deleted_at(null)`. Managers: `objects = SoftDeleteManager()` (excludes deleted),
    `all_objects = models.Manager()`. Methods: `delete()` → soft (set is_deleted/deleted_at),
    `hard_delete()`, `restore()`.
  - `AuditLog(BaseModel-ish, but plain)`: `actor(FK user null)`, `action(choices: create/update/delete/login/...)`,
    `entity(str)`, `entity_id(uuid/str)`, `changes(JSONField)`, `at(auto_now_add)`, `ip(null)`.
- **repositories.py**: `BaseRepository` bound to a model — `get(id)`, `get_or_none(id)`,
  `list(**filters)`, `filter(qs...)`, `create(**data)`, `update(instance, **data)`,
  `soft_delete(instance)`, `exists(**f)`. Uses `objects` (soft-delete aware).
- **services.py**: `BaseService` — wraps a repository; `create/update/delete` set `created_by/updated_by`
  from `actor`, write an `AuditLog`, and call `invalidate_cache()` hook. Subclasses add business logic.
- **renderers.py**: `EnvelopeJSONRenderer` wrapping DRF data as
  `{success:true, message, data, errors:[], meta:{}}`; passes through already-enveloped payloads and
  paginated results (moves pagination info to `meta`).
- **exceptions.py**: `envelope_exception_handler(exc, context)` → DRF handler then reshape to
  `{success:false, message, data:null, errors:[...], meta:{}}` with correct status codes.
- **pagination.py**: `StandardPagination(PageNumberPagination)` — `page`/`page_size` (max 100),
  emits `meta: {count, page, page_size, total_pages, next, previous}`.
- **permissions.py**: `Role` string constants; `HasRole(*roles)` factory; `RoleModelPermission`
  (map action→allowed roles via a `permission_matrix` dict on the view); helpers `IsAdmin`,
  `IsStaffRole`, `IsSelfOrStaff`. RBAC matrix defaults per contract table below.
- **cache.py**: `cache_get_or_set(key, ttl, producer)`, `cache_key(*parts)`, `invalidate(*keys)`,
  `invalidate_prefix(prefix)`. TTLs: dashboards/analytics 300s, timetable/subjects 3600s,
  attendance 300s, notifications 60s, library 600s, reports 900s.
- **viewsets.py** (optional): `BaseModelViewSet` wiring service+repo+envelope+matrix so modules stay thin.
- **management/commands/seed_demo.py**: seeds demo data mirroring the app (student "Abin Thomas", the 6
  role users, departments CSE/ECE/MECH/CIVIL/MBA, subjects sub-ds..sub-cn equivalents, etc.).

### accounts app (auth + users)
- **models.py**: custom `User(AbstractBaseUser, PermissionsMixin, BaseModel)` — email (unique, USERNAME_FIELD),
  `full_name`, `role` (choices, indexed), `phone`, `is_active`, `is_staff`, `avatar_color`; `UserManager`.
  Optional `Device`/`Session` model for multi-device; `OTP` model (code, purpose, expires_at, used).
- **serializers.py**: Login (email+password), token pair (add `user`+`role` claims), Register (admin-only),
  User read, ChangePassword, ForgotPassword (request OTP), ResetPassword (OTP), Me.
- **services.py**: authenticate, issue tokens, logout (blacklist refresh), OTP issue/verify (Celery email),
  password reset. **repositories.py**: user queries.
- **views.py / urls.py** (`/api/v1/auth/`):
  `POST login` (→ `{user, access, refresh}` in envelope), `POST refresh`, `POST logout`,
  `GET me`, `POST change-password`, `POST forgot-password`, `POST reset-password`,
  `POST register` (admin). SimpleJWT views wrapped in the envelope.
- **permissions.py**: role checks. **tasks.py**: `send_otp_email`, `send_welcome_email`.
- Map to the app's auth contract (`/auth/login` → `{user, token}`): the app expects `token`; expose
  `access` as `token` (+ `refresh`) so `docs/BACKEND_MIGRATION.md` stays satisfied.

### docker-compose.yml
- Add `redis:` (image redis:7, healthcheck) service.
- Add `celery:` (same build, command `celery -A config worker -l info`, depends on db+redis) and
  optionally `celery-beat:`.
- `web` + `celery` get `REDIS_URL`, `CELERY_BROKER_URL` env; `web` depends on db (healthy) + redis.
- `entrypoint.sh` unchanged (migrate/collectstatic/superuser) — still runs for `web`.

---

## Phase 2 — Domain modules (each = the standard 9-file set, RBAC, cache, audit, tests)

Domain shapes mirror `…/education-os/src/data/types.ts`; endpoints mirror
`…/education-os/docs/BACKEND_MIGRATION.md`, re-expressed under `/api/v1/` inside the envelope.
Add the doc's extra fields (UUID PKs, audit, soft-delete, and Student FKs: department/course/semester/section,
plus Address/Guardian/Medical/Documents child tables).

Modules to build (full app parity):
1. **academics** — Department, Program/Course, Semester, Section, Subject, ClassSession (timetable). (Replaces the old `courses` app.)
2. **students** — Student (+ Address, Guardian, Medical, Document), roster reads.
3. **faculty** — FacultyProfile, FacultyClass, ClassRoster (teaching assignments).
4. **guardians/parents** — Guardian↔Student links, parent dashboard.
5. **attendance** — AttendanceRecord, AttendanceSession, summaries.
6. **assignments** — Assignment, Submission (student + faculty-created).
7. **exams** — Exam, ExamResult, GPA; MarksSheet/MarkEntry (faculty marks entry).
8. **fees** — FeeInvoice, Payment.
9. **library** — Book, BookLoan.
10. **hostel** — HostelInfo/allocation.
11. **transport** — BusRoute, stops, BusLiveStatus (+ Channels consumer for live tracking).
12. **notifications** — Notification (+ Celery push, Channels consumer, mark-read).
13. **events** — Event, registrations.
14. **complaints** — Complaint (+ status workflow / monitoring).
15. **leave** — LeaveRequest (+ approve/reject workflow).
16. **certificates** — Certificate.
17. **placement** — PlacementOpening, Application.
18. **chat** — ChatThread, ChatMessage (parent-teacher; Channels consumer).
19. **quizzes** — Quiz, QuizQuestion (faculty-created).
20. **materials** — Material (notes/videos; S3 upload).
21. **ai** — AIThread/AIMessage, feature endpoints (mentor/doubt/notes/quiz-gen) via Celery tasks (LLM pluggable; canned fallback).
22. **analytics** — HOD (department) + Principal (institution) aggregations (cached).
23. **dashboards** — per-role aggregated dashboards (student/parent/faculty/hod/principal), Redis-cached with invalidation.
24. **admin** — management endpoints + roles/permissions + audit-log browsing (thin layer over the above with admin RBAC).

### Standard list-endpoint query params (all list APIs)
`?page=&page_size=&search=&ordering=&<field filters>`; responses paginated via `meta`.

### RBAC matrix (defaults; refine per module)
| Area | student | parent | faculty | hod | principal | admin |
| --- | --- | --- | --- | --- | --- | --- |
| own profile/dashboard | RW(self) | R(child) | RW(self) | RW(self) | R | R |
| attendance | R(self) | R(child) | RW(own classes) | R(dept) | R | RW |
| marks/results | R(self) | R(child) | RW(own classes) | R(dept) | R | RW |
| fees | R(self) | R+pay(child) | – | R(dept) | R | RW |
| assignments/materials/quizzes | R+submit | R(child) | RW(own) | R(dept) | R | RW |
| library/hostel/transport/events/certificates | R | R(child) | R | R | R | RW |
| complaints | RW(self) | RW(child) | R | R | R(monitor) | RW |
| leave | RW(self) | approve(child) | RW(self)+approve(students) | approve | R | RW |
| notifications | R(self) | R(self) | R(self) | R | R | RW(broadcast) |
| analytics/reports | – | – | – | R(dept) | R(institution) | R |
| user/role/permission mgmt, all "manage *" | – | – | – | – | – | RW |

## Acceptance (whole build)
`makemigrations && migrate && check` clean on SQLite; Swagger lists all `/api/v1` endpoints; JWT login
returns `{user, access/token, refresh}`; RBAC enforced; lists paginated/filterable; writes audited +
cache-invalidated; `seed_demo` populates the app's demo data; tests pass. Then the mobile app flips
`EXPO_PUBLIC_USE_MOCK=false` + points `API_BASE_URL` at `/api/v1`.
