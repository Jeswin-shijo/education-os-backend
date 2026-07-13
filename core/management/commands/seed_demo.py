"""Seed demo data for AI Campus OS.

Idempotent seeder mirroring the mobile app demo data (see
``education-os/src/data/seed/index.ts``). Safe to run repeatedly: every row is
created via ``get_or_create`` keyed on a stable natural key, so a second run
neither duplicates nor crashes. Runnable on SQLite.

Centre of gravity is the student "Abin Thomas" (Sem 5 CSE, CGPA 8.4), linked to
the seven role logins (all password ``campus123``): student, parent, faculty,
hod, principal, admin, and a superadmin.
"""
from datetime import date, datetime, timedelta, time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.permissions import Role

# Reference "today" mirrors the mobile seed (app "today" = 2026-06-29).
TODAY = timezone.make_aware(datetime(2026, 6, 29, 9, 0, 0))
DEMO_PASSWORD = "campus123"
# Academic year label applied to subjects and timetable sessions.
ACADEMIC_SESSION = "2026-2027"

# Palette (mirrors the app's theme colors used in the seed).
NAVY = "#13327F"
INFO = "#2563EB"
PURPLE = "#7C3AED"
TEAL = "#0D9488"
PINK = "#DB2777"
WARNING = "#CA8A04"
SUCCESS = "#16A34A"
DANGER = "#DC2626"


def days(n: int) -> datetime:
    return TODAY + timedelta(days=n)


def days_date(n: int) -> date:
    return (TODAY + timedelta(days=n)).date()


def hours(n: int) -> datetime:
    return TODAY + timedelta(hours=n)


class Command(BaseCommand):
    help = "Seed idempotent demo data mirroring the AI Campus OS mobile app."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Hard-delete existing demo rows before seeding (rarely needed).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding AI Campus OS demo data...")
        users = self._seed_users()
        acad = self._seed_academics(users)
        student = self._seed_student(users, acad)
        self._seed_guardian_link(users, student)
        faculty = self._seed_faculty(users, acad)
        self._seed_timetable(acad, users)
        self._seed_attendance(student, acad, faculty)
        self._seed_assignments(student, acad, faculty)
        self._seed_exams(student, acad, faculty)
        self._seed_fees(student)
        self._seed_library(student)
        self._seed_hostel(student)
        self._seed_transport()
        self._seed_campus()
        self._seed_materials(acad, faculty)
        self._seed_quizzes(acad, faculty)
        self._seed_notifications(users)
        self._seed_events(users)
        self._seed_complaints(users)
        self._seed_leave(users)
        self._seed_certificates(student)
        self._seed_placements(student)
        self._seed_chat(users)
        self._seed_ai(users)
        self._seed_audit(users)
        self.stdout.write(self.style.SUCCESS("Demo data seeded (idempotent)."))

    # -- users ------------------------------------------------------------
    def _seed_users(self):
        from accounts.models import User

        specs = [
            ("student", "abin.thomas@campus.edu.in", "Abin Thomas", Role.STUDENT, "+91 98470 12345", NAVY),
            ("parent", "thomas.varghese@gmail.com", "Thomas Varghese", Role.PARENT, "+91 98460 55512", TEAL),
            ("faculty", "rajesh.menon@campus.edu.in", "Dr. Rajesh Menon", Role.FACULTY, "+91 98470 33221", PURPLE),
            ("faculty_anita", "anita.nair@campus.edu.in", "Prof. Anita Nair", Role.FACULTY, "+91 98470 33222", INFO),
            ("faculty_priya", "priya.verghese@campus.edu.in", "Dr. Priya Verghese", Role.FACULTY, "+91 98470 33223", TEAL),
            ("hod", "suresh.pillai@campus.edu.in", "Dr. Suresh Pillai", Role.HOD, "+91 98470 77654", WARNING),
            ("principal", "principal@campus.edu.in", "Dr. Geetha Krishnan", Role.PRINCIPAL, "+91 98470 99001", PINK),
            ("admin", "admin@campus.edu.in", "Campus Admin", Role.ADMIN, "+91 98470 10000", INFO),
            ("superadmin", "superadmin@campus.edu.in", "System Super Admin", Role.SUPER_ADMIN, "+91 98470 00000", NAVY),
        ]
        users = {}
        for key, email, name, role, phone, color in specs:
            user, created = User.all_objects.get_or_create(
                email=email,
                defaults={
                    "full_name": name,
                    "role": role,
                    "phone": phone,
                    "avatar_color": color,
                    "is_active": True,
                    "is_staff": role in (Role.ADMIN, Role.SUPER_ADMIN),
                    "is_superuser": role == Role.SUPER_ADMIN,
                },
            )
            # Always (re)set the known demo password so login is deterministic.
            user.set_password(DEMO_PASSWORD)
            if user.is_deleted:
                user.is_deleted = False
                user.deleted_at = None
            user.save()
            users[key] = user
        self.stdout.write(f"  users: {len(users)}")
        return users

    # -- academics --------------------------------------------------------
    def _seed_academics(self, users):
        from academics.models import (
            Department, Program, Semester, Section, Subject,
            SHIFT_MORNING, SHIFT_AFTERNOON,
        )

        # EXACTLY the ten client-approved engineering departments (code : name).
        # CSE is kept so student Abin's data stays valid.
        dept_specs = [
            ("CSE", "Computer Science & Engineering"),
            ("CSE-AI", "Computer Science & Engineering (Artificial Intelligence)"),
            ("CSE-DS", "Computer Science & Engineering (Data Science)"),
            ("IT", "Information Technology"),
            ("ECE", "Electronics & Communication Engineering"),
            ("EEE", "Electrical & Electronics Engineering"),
            ("MECH", "Mechanical Engineering"),
            ("CIVIL", "Civil Engineering"),
            ("AI&DS", "Artificial Intelligence & Data Science"),
            ("BME", "Biomedical Engineering"),
        ]
        departments = {}
        for code, name in dept_specs:
            dept, _ = Department.objects.get_or_create(code=code, defaults={"name": name})
            departments[code] = dept
        cse = departments["CSE"]

        # EXACTLY ten B.Tech programs, one per department (code -> department code).
        program_specs = [
            ("BT-CSE", "CSE"),
            ("BT-CSE-AI", "CSE-AI"),
            ("BT-CSE-DS", "CSE-DS"),
            ("BT-IT", "IT"),
            ("BT-ECE", "ECE"),
            ("BT-EEE", "EEE"),
            ("BT-MECH", "MECH"),
            ("BT-CIVIL", "CIVIL"),
            ("BT-AIDS", "AI&DS"),
            ("BT-BME", "BME"),
        ]
        programs = {}
        for pcode, dcode in program_specs:
            dept = departments[dcode]
            prog, _ = Program.objects.get_or_create(
                code=pcode,
                defaults={
                    "name": f"B.Tech {dept.name}",
                    "department": dept,
                    "duration_years": 4,
                    "intake": 120,
                },
            )
            # Creating a program must yield its full set of semesters (4yr -> 1..8).
            for number in range(1, (prog.duration_years or 4) * 2 + 1):
                Semester.objects.get_or_create(program=prog, number=number)
            programs[pcode] = prog

        program = programs["BT-CSE"]
        semester, _ = Semester.objects.get_or_create(program=program, number=5)
        # Two sections with a Morning/Afternoon shift mix; "A" carries Abin's data.
        section, _ = Section.objects.get_or_create(
            semester=semester, name="A", defaults={"shift": SHIFT_MORNING},
        )
        Section.objects.get_or_create(
            semester=semester, name="B", defaults={"shift": SHIFT_AFTERNOON},
        )

        # (code, name, credits, faculty_name, color, faculty_user_key)
        # ``faculty_user_key`` links the legacy single-faculty ``faculty`` FK to a
        # seeded user so the attendance ``by_faculty`` rollup has buckets; None
        # keeps the display name only (no user account for that lecturer).
        subject_specs = [
            ("CS301", "Data Structures", 4, "Dr. Rajesh Menon", NAVY, "faculty"),
            ("CS302", "Database Management Systems", 4, "Prof. Anita Nair", INFO, "faculty_anita"),
            ("CS303", "Operating Systems", 4, "Dr. Suresh Pillai", PURPLE, "hod"),
            ("MA301", "Mathematics III", 3, "Dr. Lakshmi Iyer", TEAL, None),
            ("PH301", "Physics Lab", 2, "Prof. Mohan Das", PINK, None),
            ("CS304", "Computer Networks", 4, "Dr. Priya Verghese", WARNING, "faculty_priya"),
        ]
        subjects = {}
        for code, name, credits, faculty_name, color, fkey in subject_specs:
            faculty_user = users.get(fkey) if fkey else None
            subj, _ = Subject.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "credits": credits,
                    "department": cse,
                    "program": program,
                    "semester": semester,
                    "academic_session": ACADEMIC_SESSION,
                    "faculty": faculty_user,
                    "faculty_name": faculty_name,
                    "color": color,
                },
            )
            subjects[code] = subj

        self.stdout.write(
            f"  departments: {len(departments)}, programs: {len(programs)}, "
            f"subjects: {len(subjects)}"
        )
        return {
            "departments": departments,
            "programs": programs,
            "cse": cse,
            "program": program,
            "semester": semester,
            "section": section,
            "subjects": subjects,
        }

    # -- student ----------------------------------------------------------
    def _seed_student(self, users, acad):
        from students.models import Student, StudentAddress, Guardian, Medical

        student, _ = Student.objects.get_or_create(
            roll_no="CSE21-042",
            defaults={
                "user": users["student"],
                "admission_no": "ADM2021CSE042",
                "program": acad["program"],
                "department": acad["cse"],
                "semester": acad["semester"],
                "section": acad["section"],
                "first_name": "Abin",
                "last_name": "Thomas",
                "full_name": "Abin Thomas",
                "gender": Student.GENDER_MALE,
                "phone": "+91 98470 12345",
                "email": "abin.thomas@campus.edu.in",
                "cgpa": Decimal("8.40"),
                "blood_group": "O+",
                "mentor_name": "Dr. Rajesh Menon",
                "avatar_color": NAVY,
                "status": Student.STATUS_ACTIVE,
            },
        )
        # Ensure user link (in case a prior partial run left it null).
        if student.user_id != users["student"].id:
            student.user = users["student"]
            student.save(update_fields=["user", "updated_at"])

        StudentAddress.objects.get_or_create(
            student=student,
            line1="12 Marthanda Lane",
            defaults={
                "city": "Kochi",
                "state": "Kerala",
                "pincode": "682001",
                "country": "India",
            },
        )
        Guardian.objects.get_or_create(
            student=student,
            name="Thomas Varghese",
            defaults={
                "relation": "father",
                "phone": "+91 98460 55512",
                "email": "thomas.varghese@gmail.com",
                "is_primary": True,
            },
        )
        Medical.objects.get_or_create(
            student=student,
            defaults={"blood_group": "O+", "allergies": "", "conditions": ""},
        )
        self.stdout.write(f"  student: {student.full_name} ({student.roll_no})")
        return student

    def _seed_guardian_link(self, users, student):
        from guardians.models import ParentLink

        ParentLink.objects.get_or_create(
            parent=users["parent"],
            student=student,
            defaults={"relation": ParentLink.RELATION_FATHER, "is_primary": True},
        )
        self.stdout.write("  guardian link: parent -> Abin")

    # -- faculty ----------------------------------------------------------
    def _seed_faculty(self, users, acad):
        from faculty.models import FacultyProfile, FacultyClass, RosterEntry

        # (user_key, designation, subject_codes, qualifications, experience, photo_url)
        # Personal-info fields (qualifications/experience/photo_url) are surfaced
        # by the admin console; phone lives on the linked user (set in _seed_users).
        faculty_specs = [
            ("faculty", "Associate Professor", ["CS301", "CS501", "CS391"],
             "Ph.D. in Computer Science (IISc Bangalore); M.Tech CSE (NIT Trichy)",
             "12 years",
             "https://ui-avatars.com/api/?name=Rajesh+Menon&background=7C3AED&color=fff"),
            ("faculty_anita", "Assistant Professor", ["CS301", "CS391"],
             "M.Tech Information Technology (NIT Calicut); B.Tech CSE",
             "8 years",
             "https://ui-avatars.com/api/?name=Anita+Nair&background=2563EB&color=fff"),
            ("faculty_priya", "Assistant Professor", ["CS501", "CS304"],
             "Ph.D. in Computer Networks (Anna University); M.E. Communication Systems",
             "6 years",
             "https://ui-avatars.com/api/?name=Priya+Verghese&background=0D9488&color=fff"),
        ]
        profiles = {}
        for key, designation, codes, quals, experience, photo_url in faculty_specs:
            fac_user = users.get(key)
            if fac_user is None:
                continue
            prof, _ = FacultyProfile.objects.get_or_create(
                user=fac_user,
                defaults={
                    "department": acad["cse"],
                    "designation": designation,
                    "subject_codes": codes,
                    "qualifications": quals,
                    "experience": experience,
                    "photo_url": photo_url,
                },
            )
            profiles[key] = prof
        profile = profiles["faculty"]

        # Assign the multi-faculty M2M on subjects (idempotent ``set``). Keys map
        # to the FacultyProfiles created above; CS301/CS304 get two teachers so
        # the admin console shows a multi-faculty subject.
        subject_faculty_map = {
            "CS301": ["faculty", "faculty_anita"],
            "CS302": ["faculty_anita"],
            "CS303": ["faculty_priya"],
            "MA301": ["faculty"],
            "PH301": ["faculty_anita"],
            "CS304": ["faculty_priya", "faculty"],
        }
        for code, keys in subject_faculty_map.items():
            subj = acad["subjects"].get(code)
            if subj is None:
                continue
            subj.faculties.set([profiles[k] for k in keys if k in profiles])

        ds = acad["subjects"]["CS301"]
        semester = acad["semester"]
        section = acad["section"]

        class_specs = [
            ("Data Structures A", ds, NAVY, 8,
             [{"day": "Mon", "start": "09:00", "end": "09:50", "room": "B-201"},
              {"day": "Wed", "start": "11:10", "end": "12:00", "room": "B-201"},
              {"day": "Fri", "start": "13:00", "end": "14:50", "room": "Lab-1"}]),
            ("Advanced Algorithms A", ds, PURPLE, 6,
             [{"day": "Mon", "start": "11:10", "end": "12:00", "room": "B-305"},
              {"day": "Wed", "start": "09:00", "end": "09:50", "room": "B-305"}]),
        ]
        classes = {}
        for label, subj, color, count, slots in class_specs:
            # Natural key: (subject, section, faculty) + color/label proxy via slots.
            fc, created = FacultyClass.objects.get_or_create(
                subject=subj,
                section=section,
                faculty=profile,
                color=color,
                defaults={
                    "semester": semester,
                    "slots": slots,
                    "student_count": count,
                },
            )
            classes[label] = fc

        # Roster for the Advanced Algorithms class includes Abin.
        algo = classes["Advanced Algorithms A"]
        roster = [
            ("CSE21-042", "Abin Thomas", NAVY),
            ("CSE21-007", "Hari Narayan", INFO),
            ("CSE21-015", "Pooja Ramesh", PURPLE),
            ("CSE21-022", "Tarun Anil", TEAL),
            ("CSE21-031", "Ishita Bose", PINK),
            ("CSE21-038", "Devan Krishnan", WARNING),
        ]
        for roll, name, color in roster:
            RosterEntry.objects.get_or_create(
                faculty_class=algo,
                roll_no=roll,
                defaults={"student_name": name, "avatar_color": color},
            )
        # DS-A roster (different students).
        ds_a = classes["Data Structures A"]
        ds_roster = [
            ("CSE23-001", "Aarav Menon"), ("CSE23-002", "Diya Krishnan"),
            ("CSE23-003", "Rohan Pillai"), ("CSE23-004", "Sneha Nair"),
            ("CSE23-005", "Karthik Raj"), ("CSE23-006", "Meera Sundaram"),
            ("CSE23-007", "Aditya Varma"), ("CSE23-008", "Lakshmi Suresh"),
        ]
        for i, (roll, name) in enumerate(ds_roster):
            RosterEntry.objects.get_or_create(
                faculty_class=ds_a,
                roll_no=roll,
                defaults={"student_name": name, "avatar_color": WARNING},
            )
        self.stdout.write(f"  faculty classes: {len(classes)}")
        return {"profile": profile, "classes": classes}

    # -- timetable --------------------------------------------------------
    def _seed_timetable(self, acad, users):
        """Weekly timetable ``ClassSession`` rows for section A.

        These back ``GET /api/v1/timetable`` (incl. the ``?faculty=`` filter) and
        carry the client-change fields: ``academic_session``, ``shift`` and
        ``status``. Natural key is (subject, section, day, start).
        """
        from academics.models import ClassSession, SHIFT_MORNING

        subjects = acad["subjects"]
        section = acad["section"]
        # (code, day, start, end, room, type, faculty_user_key)
        session_specs = [
            ("CS301", "Mon", "09:00", "09:50", "B-201", ClassSession.TYPE_LECTURE, "faculty"),
            ("CS302", "Tue", "10:00", "10:50", "B-201", ClassSession.TYPE_LECTURE, "faculty_anita"),
            ("CS303", "Wed", "11:10", "12:00", "B-203", ClassSession.TYPE_LECTURE, "hod"),
            ("CS304", "Thu", "14:00", "14:50", "B-202", ClassSession.TYPE_LECTURE, "faculty_priya"),
            ("CS301", "Fri", "13:00", "14:50", "Lab-1", ClassSession.TYPE_LAB, "faculty"),
            ("MA301", "Mon", "11:10", "12:00", "B-201", ClassSession.TYPE_TUTORIAL, None),
        ]
        n = 0
        for code, day, start, end, room, typ, fkey in session_specs:
            subj = subjects.get(code)
            if subj is None:
                continue
            faculty_user = users.get(fkey) if fkey else None
            _, created = ClassSession.objects.get_or_create(
                subject=subj,
                section=section,
                day=day,
                start=start,
                defaults={
                    "end": end,
                    "room": room,
                    "type": typ,
                    "faculty": faculty_user,
                    "academic_session": ACADEMIC_SESSION,
                    "shift": SHIFT_MORNING,
                    "status": ClassSession.STATUS_ACTIVE,
                },
            )
            if created:
                n += 1
        self.stdout.write(f"  timetable sessions: {len(session_specs)} (+{n})")

    # -- attendance -------------------------------------------------------
    def _seed_attendance(self, student, acad, faculty):
        from attendance.models import (
            AttendanceRecord, AttendanceSession, AttendanceEntry, AttendanceStatus,
        )

        # Per-subject student-facing records (a handful each, mixed statuses).
        targets = {
            "CS301": (10, 9), "CS302": (10, 8), "CS303": (10, 8),
            "MA301": (8, 7), "PH301": (6, 5), "CS304": (10, 9),
        }
        n = 0
        for code, (total, attended) in targets.items():
            subj = acad["subjects"][code]
            absent = total - attended
            for i in range(total):
                if i < absent:
                    status = AttendanceStatus.LATE if i == 0 else AttendanceStatus.ABSENT
                else:
                    status = AttendanceStatus.PRESENT
                _, created = AttendanceRecord.objects.get_or_create(
                    student=student,
                    subject=subj,
                    date=days_date(-(i * 2 + 2)),
                    defaults={"status": status},
                )
                if created:
                    n += 1

        # A faculty-recorded session on the Advanced Algorithms class (has Abin).
        algo = faculty["classes"]["Advanced Algorithms A"]
        session, _ = AttendanceSession.objects.get_or_create(
            faculty_class=algo,
            date=days_date(-2),
        )
        roster_rolls = [
            ("CSE21-042", AttendanceStatus.PRESENT),
            ("CSE21-007", AttendanceStatus.PRESENT),
            ("CSE21-015", AttendanceStatus.PRESENT),
            ("CSE21-022", AttendanceStatus.ABSENT),
            ("CSE21-031", AttendanceStatus.PRESENT),
            ("CSE21-038", AttendanceStatus.LATE),
        ]
        for roll, status in roster_rolls:
            AttendanceEntry.objects.get_or_create(
                session=session,
                roll_no=roll,
                defaults={"status": status},
            )
        self.stdout.write(f"  attendance records: +{n} (session +entries)")

    # -- assignments ------------------------------------------------------
    def _seed_assignments(self, student, acad, faculty):
        from assignments.models import Assignment, Submission

        subs = acad["subjects"]
        specs = [
            ("AVL Tree Implementation", "CS301", 4, 20, Assignment.STATUS_PENDING, None, None),
            ("Normalization Case Study", "CS302", 2, 15, Assignment.STATUS_PENDING, None, None),
            ("CPU Scheduling Simulation", "CS303", -1, 25, Assignment.STATUS_SUBMITTED, -2, None),
            ("Fourier Series Problem Set", "MA301", -5, 10, Assignment.STATUS_GRADED, -6, 9),
            ("Subnetting Worksheet", "CS304", -8, 15, Assignment.STATUS_GRADED, -9, 13),
            ("Lab Record — Experiments 1-4", "PH301", -12, 20, Assignment.STATUS_LATE, -10, 14),
        ]
        n = 0
        for title, code, due_off, max_marks, status, sub_off, grade in specs:
            asg, _ = Assignment.objects.get_or_create(
                title=title,
                subject=subs[code],
                defaults={
                    "description": f"{title} — see brief.",
                    "due_date": days(due_off),
                    "max_marks": max_marks,
                    "status": status,
                },
            )
            if sub_off is not None:
                _, created = Submission.objects.get_or_create(
                    assignment=asg,
                    student=student,
                    defaults={
                        "file_name": title.lower().replace(" ", "_")[:40] + ".pdf",
                        "submitted_at": days(sub_off),
                        "grade": grade,
                    },
                )
                if created:
                    n += 1
        self.stdout.write(f"  assignments: {len(specs)} (submissions +{n})")

    # -- exams ------------------------------------------------------------
    def _seed_exams(self, student, acad, faculty):
        from exams.models import Exam, ExamResult, MarksSheet, MarkEntry

        subs = acad["subjects"]
        exam_specs = [
            ("Internal Assessment II", "CS301", 3, "10:00", "B-201", 90, Exam.TYPE_INTERNAL),
            ("Internal Assessment II", "CS302", 5, "10:00", "B-201", 90, Exam.TYPE_INTERNAL),
            ("Surprise Quiz", "CS303", 1, "09:00", "B-203", 30, Exam.TYPE_QUIZ),
            ("Internal Assessment II", "CS304", 8, "14:00", "B-202", 90, Exam.TYPE_INTERNAL),
            ("Semester Examination", "MA301", 25, "09:30", "Hall-A", 180, Exam.TYPE_SEMESTER),
        ]
        for name, code, off, t, room, dur, typ in exam_specs:
            Exam.objects.get_or_create(
                name=name,
                subject=subs[code],
                date=days_date(off),
                defaults={"time": t, "room": room, "duration_mins": dur, "type": typ},
            )

        # Results (Semester 4 Final) → CGPA ≈ 8.4.
        result_specs = [
            ("CS301", 86, 9, 4), ("CS302", 82, 8, 4), ("CS303", 78, 8, 4),
            ("MA301", 88, 9, 3), ("PH301", 91, 9, 2), ("CS304", 72, 7, 4),
        ]
        grade_map = {10: "O", 9: "A+", 8: "A", 7: "B+", 6: "B"}
        for code, marks, gp, credits in result_specs:
            ExamResult.objects.get_or_create(
                student=student,
                subject=subs[code],
                exam="Semester 4 Final",
                defaults={
                    "marks": Decimal(marks),
                    "max_marks": Decimal(100),
                    "grade": grade_map.get(gp, "C"),
                    "grade_point": Decimal(gp),
                    "credits": Decimal(credits),
                },
            )

        # Faculty marks sheet for the Advanced Algorithms class.
        algo = faculty["classes"]["Advanced Algorithms A"]
        sheet, _ = MarksSheet.objects.get_or_create(
            faculty_class=algo,
            exam="Internal Assessment I",
            defaults={"max_marks": Decimal(30), "entered_on": days(-8)},
        )
        MarkEntry.objects.get_or_create(
            sheet=sheet, student=student, defaults={"marks": Decimal(27)},
        )
        self.stdout.write(f"  exams: {len(exam_specs)}, results: {len(result_specs)}")

    # -- fees -------------------------------------------------------------
    def _seed_fees(self, student):
        from fees.models import FeeInvoice, Payment

        FeeInvoice.objects.get_or_create(
            student=student,
            title="Tuition Fee",
            term="Semester 5",
            defaults={
                "amount": Decimal("87500.00"),
                "due_date": days_date(12),
                "status": FeeInvoice.STATUS_DUE,
            },
        )
        paid, _ = FeeInvoice.objects.get_or_create(
            student=student,
            title="Hostel & Mess Fee",
            term="Semester 5",
            defaults={
                "amount": Decimal("62000.00"),
                "due_date": days_date(-30),
                "status": FeeInvoice.STATUS_PAID,
                "paid_on": days(-35),
            },
        )
        Payment.objects.get_or_create(
            invoice=paid,
            reference="HOSTEL-2026-001",
            defaults={
                "amount": Decimal("62000.00"),
                "method": Payment.METHOD_UPI,
                "paid_at": days(-35),
            },
        )
        self.stdout.write("  fees: 2 invoices (1 due, 1 paid)")

    # -- library ----------------------------------------------------------
    def _seed_library(self, student):
        from library.models import Book, BookLoan

        book_specs = [
            ("Introduction to Algorithms", "Cormen et al.", "Algorithms", True),
            ("Database System Concepts", "Silberschatz et al.", "Databases", False),
            ("Operating System Concepts", "Silberschatz, Galvin", "Operating Systems", True),
            ("Computer Networks", "Andrew S. Tanenbaum", "Networks", True),
            ("Compilers: Principles, Techniques & Tools", "Aho et al.", "Compilers", False),
            ("Cracking the Coding Interview", "Gayle L. McDowell", "Interview Prep", True),
        ]
        books = {}
        for title, author, category, available in book_specs:
            book, _ = Book.objects.get_or_create(
                title=title,
                defaults={
                    "author": author,
                    "category": category,
                    "available": available,
                    "copies_total": 3,
                    "copies_available": 3 if available else 0,
                },
            )
            books[title] = book

        BookLoan.objects.get_or_create(
            book=books["Database System Concepts"],
            student=student,
            issued_on=days_date(-10),
            defaults={"due_on": days_date(4), "status": BookLoan.STATUS_BORROWED},
        )
        BookLoan.objects.get_or_create(
            book=books["Compilers: Principles, Techniques & Tools"],
            student=student,
            issued_on=days_date(-25),
            defaults={"due_on": days_date(-3), "status": BookLoan.STATUS_OVERDUE},
        )
        self.stdout.write(f"  library: {len(books)} books, 2 loans")

    # -- hostel -----------------------------------------------------------
    def _seed_hostel(self, student):
        from hostel.models import HostelBlock, HostelRoom, HostelAllocation

        block, _ = HostelBlock.objects.get_or_create(
            name="Nila Block",
            defaults={"warden": "Mr. Ramesh Kumar", "warden_phone": "+91 98470 44556"},
        )
        room, _ = HostelRoom.objects.get_or_create(
            block=block, room_no="C-214", defaults={"capacity": 3},
        )
        HostelAllocation.objects.get_or_create(
            student=student,
            defaults={
                "room": room,
                "bed": "Bed 2",
                "mess_plan": "Veg + Non-Veg (Standard)",
                "fees": Decimal("62000.00"),
            },
        )
        self.stdout.write("  hostel: block/room/allocation for Abin")

    # -- transport --------------------------------------------------------
    def _seed_transport(self):
        from transport.models import BusRoute, BusStop, BusLiveStatus

        route_specs = [
            ("City Center Route", "R1", "Sajeev P", "+91 98470 60011",
             [("City Center", "07:15"), ("Railway Station", "07:30"),
              ("Tech Park", "08:00"), ("Campus Gate", "08:20")]),
            ("Eastside Route", "R2", "Biju M", "+91 98470 60022",
             [("East Market", "07:20"), ("Lake View", "07:35"),
              ("Campus Gate", "08:15")]),
        ]
        for name, number, driver, phone, stops in route_specs:
            route, _ = BusRoute.objects.get_or_create(
                number=number,
                defaults={"name": name, "driver": driver, "driver_phone": phone},
            )
            for order, (stop_name, t) in enumerate(stops):
                BusStop.objects.get_or_create(
                    route=route,
                    order=order,
                    defaults={"name": stop_name, "time": t},
                )
            BusLiveStatus.objects.get_or_create(
                route=route,
                defaults={
                    "current_stop": stops[0][0],
                    "next_stop": stops[1][0] if len(stops) > 1 else "",
                    "eta_mins": 12,
                    "occupancy": 55,
                },
            )
        self.stdout.write(f"  transport: {len(route_specs)} routes")

    # -- campus -----------------------------------------------------------
    def _seed_campus(self):
        from campus.models import CampusLocation

        # Mirrors the mobile seed (`src/data/seed`: 10 campus locations).
        location_specs = [
            ("Main Academic Block", "academic", "Block B", "Ground-4", 3),
            ("Central Library", "academic", "Block L", "1-3", 5),
            ("Computer Science Labs", "academic", "Block B", "2", 4),
            ("Main Canteen", "food", "Food Court", "Ground", 6),
            ("Coffee Hub", "food", "Block A", "Ground", 2),
            ("Sports Complex", "sports", "Sports Arena", "", 9),
            ("Administrative Office", "admin", "Admin Block", "1", 4),
            ("Examination Cell", "admin", "Admin Block", "2", 4),
            ("Nila Hostel Block", "hostel", "Hostel Zone", "", 8),
            ("Health Centre", "medical", "Block M", "Ground", 7),
        ]
        for name, category, building, floor, eta in location_specs:
            CampusLocation.objects.get_or_create(
                name=name,
                defaults={
                    "category": category,
                    "building": building,
                    "floor": floor,
                    "eta_mins": eta,
                },
            )
        self.stdout.write(f"  campus: {len(location_specs)} locations")

    # -- materials --------------------------------------------------------
    def _seed_materials(self, acad, faculty):
        from materials.models import Material

        specs = [
            ("Trees & Balancing — Lecture Notes", "CS301", Material.KIND_NOTE, "1.2 MB"),
            ("Graph Algorithms Slides", "CS301", Material.KIND_SLIDE, "3.4 MB"),
            ("Normalization Explained", "CS302", Material.KIND_VIDEO, "48 min"),
            ("Process Scheduling Slides", "CS303", Material.KIND_SLIDE, "2.1 MB"),
            ("TCP/IP Model Notes", "CS304", Material.KIND_NOTE, "980 KB"),
        ]
        for title, code, kind, size in specs:
            Material.objects.get_or_create(
                title=title,
                subject=acad["subjects"][code],
                defaults={"kind": kind, "size_label": size},
            )
        self.stdout.write(f"  materials: {len(specs)}")

    # -- quizzes ----------------------------------------------------------
    def _seed_quizzes(self, acad, faculty):
        from quizzes.models import Quiz, QuizQuestion

        ds = acad["subjects"]["CS301"]
        quiz, _ = Quiz.objects.get_or_create(
            title="Data Structures Basics",
            subject=ds,
        )
        questions = [
            ("Which data structure uses LIFO ordering?", ["Queue", "Stack", "Tree", "Graph"], 1),
            ("Worst-case time to search an unsorted array of n elements?",
             ["O(1)", "O(log n)", "O(n)", "O(n log n)"], 2),
            ("A binary tree node has at most how many children?", ["1", "2", "3", "Unlimited"], 1),
        ]
        for order, (text, options, ans) in enumerate(questions):
            QuizQuestion.objects.get_or_create(
                quiz=quiz,
                order=order,
                defaults={"text": text, "options": options, "answer_index": ans},
            )
        self.stdout.write("  quizzes: 1 quiz, 3 questions")

    # -- notifications ----------------------------------------------------
    def _seed_notifications(self, users):
        from notifications.models import Notification

        student = users["student"]
        specs = [
            ("Internal Assessment II Schedule",
             "IA-II for Data Structures is on 2 Jul at 10:00 AM in B-201.",
             Notification.CATEGORY_ACADEMIC, False),
            ("Tuition Fee Due",
             "Your Semester 5 tuition fee of Rs.87,500 is due on 11 Jul.",
             Notification.CATEGORY_FEE, False),
            ("Surprise Quiz Tomorrow",
             "Operating Systems surprise quiz scheduled for tomorrow 9:00 AM.",
             Notification.CATEGORY_ALERT, False),
            ("TechFest 2026 Registrations Open",
             "Register now for TechFest 2026. Limited slots for the AI workshop.",
             Notification.CATEGORY_EVENT, True),
            ("Assignment Graded",
             "Your Mathematics III Fourier Series Problem Set scored 9/10.",
             Notification.CATEGORY_ACADEMIC, True),
        ]
        for title, body, category, read in specs:
            Notification.objects.get_or_create(
                recipient=student,
                title=title,
                defaults={"body": body, "category": category, "read": read},
            )
        self.stdout.write(f"  notifications: {len(specs)} for student")

    # -- events -----------------------------------------------------------
    def _seed_events(self, users):
        from events.models import Event, EventRegistration

        specs = [
            ("TechFest 2026", 10, "09:00", "Main Auditorium", Event.CATEGORY_TECH, False),
            ("AI & ML Workshop", 6, "10:00", "Seminar Hall B", Event.CATEGORY_WORKSHOP, True),
            ("Cultural Night — Onam Special", 14, "18:00", "Open Air Theatre", Event.CATEGORY_CULTURAL, False),
            ("Inter-College Football Cup", 18, "15:00", "Sports Complex", Event.CATEGORY_SPORTS, False),
        ]
        for title, off, t, venue, category, registered in specs:
            event, _ = Event.objects.get_or_create(
                title=title,
                date=days_date(off),
                defaults={"time": t, "venue": venue, "category": category},
            )
            if registered:
                EventRegistration.objects.get_or_create(
                    event=event, user=users["student"],
                )
        self.stdout.write(f"  events: {len(specs)}")

    # -- complaints -------------------------------------------------------
    def _seed_complaints(self, users):
        from complaints.models import Complaint

        student = users["student"]
        specs = [
            ("Hostel", "Wi-Fi connectivity issue in C-Block",
             "Internet keeps dropping in the evening hours in room C-214.",
             Complaint.STATUS_IN_PROGRESS),
            ("Mess", "Request for more veg options",
             "Dinner menu has limited vegetarian choices on weekdays.",
             Complaint.STATUS_OPEN),
            ("Academics", "Lab projector not working",
             "Projector in Lab-1 has display flicker, affecting demos.",
             Complaint.STATUS_RESOLVED),
        ]
        for category, subject, description, status in specs:
            Complaint.objects.get_or_create(
                user=student,
                subject=subject,
                defaults={"category": category, "description": description, "status": status},
            )
        self.stdout.write(f"  complaints: {len(specs)}")

    # -- leave ------------------------------------------------------------
    def _seed_leave(self, users):
        from leave.models import LeaveRequest

        student = users["student"]
        specs = [
            (LeaveRequest.TYPE_MEDICAL, -20, -18, "Viral fever, advised rest.", LeaveRequest.STATUS_APPROVED),
            (LeaveRequest.TYPE_CASUAL, 2, 3, "Family function at hometown.", LeaveRequest.STATUS_PENDING),
            (LeaveRequest.TYPE_MEDICAL, 1, 1, "Dental appointment in the morning.", LeaveRequest.STATUS_PENDING),
        ]
        for typ, from_off, to_off, reason, status in specs:
            LeaveRequest.objects.get_or_create(
                user=student,
                type=typ,
                start_date=days_date(from_off),
                end_date=days_date(to_off),
                defaults={"reason": reason, "status": status},
            )
        self.stdout.write(f"  leave: {len(specs)} requests")

    # -- certificates -----------------------------------------------------
    def _seed_certificates(self, student):
        from certificates.models import Certificate

        specs = [
            ("Python for Data Science", "NPTEL", -120, Certificate.KIND_COURSE),
            ("Runner-up — SmartHack 2025", "IEEE Student Branch", -200, Certificate.KIND_ACHIEVEMENT),
            ("Cloud Computing Fundamentals", "AWS Academy", -60, Certificate.KIND_COURSE),
        ]
        for title, issuer, off, kind in specs:
            Certificate.objects.get_or_create(
                student=student,
                title=title,
                defaults={"issuer": issuer, "issued_on": days_date(off), "kind": kind},
            )
        self.stdout.write(f"  certificates: {len(specs)}")

    # -- placements -------------------------------------------------------
    def _seed_placements(self, student):
        from placement.models import PlacementOpening, PlacementApplication

        specs = [
            ("Infosys", "Systems Engineer", 650000, "Bengaluru", "CGPA >= 7.0", 7, False),
            ("TCS", "Assistant System Engineer", 700000, "Kochi", "CGPA >= 6.5", 5, True),
            ("Zoho", "Software Developer", 900000, "Chennai", "CGPA >= 7.5", 9, False),
            ("Freshworks", "Associate SDE", 1200000, "Chennai", "CGPA >= 8.0", 15, False),
        ]
        for company, role, ctc, location, elig, off, applied in specs:
            opening, _ = PlacementOpening.objects.get_or_create(
                company=company,
                role=role,
                defaults={
                    "ctc": Decimal(ctc),
                    "location": location,
                    "eligibility": elig,
                    "last_date": days_date(off),
                    "logo_color": INFO,
                    "is_active": True,
                },
            )
            if applied:
                PlacementApplication.objects.get_or_create(
                    opening=opening, student=student,
                )
        self.stdout.write(f"  placements: {len(specs)} openings")

    # -- chat -------------------------------------------------------------
    def _seed_chat(self, users):
        from chat.models import ChatThread, ChatMessage

        parent = users["parent"]
        teacher = users["faculty"]
        thread, _ = ChatThread.objects.get_or_create(
            teacher=teacher,
            parent=parent,
            subject_label="Class Tutor",
            defaults={
                "teacher_name": teacher.full_name,
                "avatar_color": NAVY,
                "last_message_at": hours(-3),
                "unread_count": {str(parent.id): 1},
            },
        )
        msgs = [
            (ChatMessage.SENDER_TEACHER, teacher,
             "Reminder: the Semester 5 tuition fee of Rs.87,500 is due on 11 July.", days(-2)),
            (ChatMessage.SENDER_PARENT, parent,
             "Noted, we will clear it before the due date.", hours(-40)),
            (ChatMessage.SENDER_TEACHER, teacher,
             "Thank you. Parent-teacher meeting is on 5 July at 10:00 AM.", hours(-3)),
        ]
        for sender_role, sender, text, at in msgs:
            ChatMessage.objects.get_or_create(
                thread=thread,
                sender=sender,
                at=at,
                defaults={"sender_role": sender_role, "text": text},
            )
        self.stdout.write("  chat: 1 parent<->faculty thread, 3 messages")

    # -- ai ---------------------------------------------------------------
    def _seed_ai(self, users):
        from ai.models import AIThread, AIMessage, AIFeature, FEATURE_TITLES

        student = users["student"]
        thread, created = AIThread.objects.get_or_create(
            user=student,
            feature=AIFeature.MENTOR,
            defaults={"title": FEATURE_TITLES[AIFeature.MENTOR]},
        )
        if created:
            AIMessage.objects.create(
                thread=thread, role=AIMessage.ROLE_USER,
                text="How should I prepare for my Data Structures internal?",
            )
            AIMessage.objects.create(
                thread=thread, role=AIMessage.ROLE_ASSISTANT,
                text="Focus on trees and balancing; practice AVL rotations and revise BFS/DFS.",
            )
        self.stdout.write("  ai: 1 mentor thread")

    # -- audit ------------------------------------------------------------
    def _seed_audit(self, users):
        from core.models import AuditLog

        admin = users["admin"]
        specs = [
            (AuditLog.ACTION_CREATE, "Student", "Added student Abin Thomas (CSE21-042)."),
            (AuditLog.ACTION_UPDATE, "Subject", "Updated faculty for CS304 to Dr. Priya Verghese."),
            (AuditLog.ACTION_CREATE, "Course", "Created program B.Tech CSE (intake 120)."),
        ]
        for action, entity, detail in specs:
            AuditLog.objects.get_or_create(
                actor=admin,
                action=action,
                entity=entity,
                changes={"detail": detail},
            )
        self.stdout.write(f"  audit logs: {len(specs)}")
