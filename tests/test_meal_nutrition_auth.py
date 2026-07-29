import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from flask import Flask

from nutrition import models as nutrition_models
from nutrition import routes as nutrition_routes
from server import app as server_app


class NutritionAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = nutrition_models.DB_PATH
        nutrition_models.DB_PATH = os.path.join(self.temp_dir.name, "nutrition.db")

        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config["NUTRITION_ALLOW_DEMO_HEADERS"] = True
        nutrition_routes.init_app(self.app)
        self.client = self.app.test_client()

        conn = nutrition_models.get_db()
        for index in range(60):
            child_code = f"C{index:03d}"
            child_id = conn.execute(
                """INSERT INTO nutrition_children
                   (child_code, display_name, age, gender, data_status)
                   VALUES (?, ?, 10, '男', 'complete')""",
                (child_code, f"学生{index:03d}"),
            ).lastrowid
            conn.execute(
                """INSERT INTO nutrition_recommendations
                   (child_id, plan_date, rule_version, recommended_plan, confirmed)
                   VALUES (?, '2026-07-27', 'test', 'A', 0)""",
                (child_id,),
            )
        conn.commit()
        conn.close()

    def tearDown(self):
        nutrition_models.DB_PATH = self.old_db_path
        self.temp_dir.cleanup()

    def test_parent_scope_is_applied_before_pagination(self):
        response = self.client.get(
            "/api/nutrition/recommendations?page=1&page_size=1",
            headers={
                "X-User-Role": "parent",
                "X-Nutrition-Child-Code": "C059",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual([item["child_code"] for item in payload["items"]], ["C059"])

    def test_parent_cannot_read_another_child_detail(self):
        own = self.client.get(
            "/api/nutrition/recommendations?page_size=1",
            headers={
                "X-User-Role": "parent",
                "X-Nutrition-Child-Code": "C059",
            },
        ).get_json()["items"][0]
        other = nutrition_models.list_recommendations(
            child_code="C000", page_size=1
        )["items"][0]

        own_response = self.client.get(
            f"/api/nutrition/recommendations/{own['id']}",
            headers={
                "X-User-Role": "parent",
                "X-Nutrition-Child-Code": "C059",
            },
        )
        other_response = self.client.get(
            f"/api/nutrition/recommendations/{other['id']}",
            headers={
                "X-User-Role": "parent",
                "X-Nutrition-Child-Code": "C059",
            },
        )

        self.assertEqual(own_response.status_code, 200)
        self.assertEqual(other_response.status_code, 404)

    def test_teacher_can_list_all_recommendations_and_parent_without_child_gets_none(self):
        teacher = self.client.get(
            "/api/nutrition/recommendations?page_size=200",
            headers={"X-User-Role": "teacher"},
        )
        unbound_parent = self.client.get(
            "/api/nutrition/recommendations",
            headers={"X-User-Role": "parent"},
        )

        self.assertEqual(teacher.status_code, 200)
        self.assertEqual(teacher.get_json()["total"], 60)
        self.assertEqual(unbound_parent.status_code, 200)
        self.assertEqual(unbound_parent.get_json()["total"], 0)
        self.assertEqual(unbound_parent.get_json()["items"], [])

    def test_parent_recommendation_stats_are_scoped_to_bound_child(self):
        response = self.client.get(
            "/api/nutrition/recommendations/stats?plan_date=2026-07-27",
            headers={
                "X-User-Role": "parent",
                "X-Nutrition-Child-Code": "C059",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "plan_date": "2026-07-27",
                "total": 1,
                "a_count": 1,
                "b_count": 0,
                "manual_count": 0,
                "confirmed_count": 0,
            },
        )

    def test_only_teacher_can_confirm_recommendation(self):
        recommendation = nutrition_models.list_recommendations(
            child_code="C059", page_size=1
        )["items"][0]
        parent = self.client.post(
            f"/api/nutrition/recommendations/{recommendation['id']}/confirm",
            headers={
                "X-User-Role": "parent",
                "X-Nutrition-Child-Code": "C059",
            },
        )
        teacher = self.client.post(
            f"/api/nutrition/recommendations/{recommendation['id']}/confirm",
            json={"operator": "teacher-test"},
            headers={"X-User-Role": "teacher"},
        )

        self.assertEqual(parent.status_code, 403)
        self.assertEqual(teacher.status_code, 200)
        self.assertEqual(teacher.get_json()["confirmed"], 1)
        self.assertEqual(teacher.get_json()["confirmed_by"], "teacher-test")

    def test_legacy_role_header_is_ignored_unless_explicitly_enabled(self):
        locked_app = Flask("nutrition-locked")
        locked_app.config["TESTING"] = True
        locked_app.config["NUTRITION_ALLOW_DEMO_HEADERS"] = False
        locked_app.register_blueprint(nutrition_routes.nutrition_bp)

        response = locked_app.test_client().get(
            "/api/nutrition/recommendations",
            headers={"X-User-Role": "teacher"},
        )

        self.assertEqual(response.status_code, 403)


class MealChoiceAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = server_app.DB_PATH
        self.old_disable_demo = server_app.DISABLE_DEMO
        server_app.DB_PATH = os.path.join(self.temp_dir.name, "student_data.db")
        server_app.DISABLE_DEMO = False

        conn = sqlite3.connect(server_app.DB_PATH)
        conn.execute(
            """CREATE TABLE students(
                id_card TEXT PRIMARY KEY,
                name TEXT,
                grade_name TEXT,
                class_name TEXT
            )"""
        )
        conn.executemany(
            "INSERT INTO students VALUES (?, ?, ?, ?)",
            [
                ("BS001", "学生甲", "五年级", "1班"),
                ("BS002", "学生乙", "五年级", "1班"),
            ],
        )
        conn.commit()
        conn.close()
        self.client = server_app.app.test_client()

    def tearDown(self):
        server_app.DB_PATH = self.old_db_path
        server_app.DISABLE_DEMO = self.old_disable_demo
        self.temp_dir.cleanup()

    @staticmethod
    def _payload(student_id="BS002"):
        return {
            "studentIdCard": student_id,
            "studentName": "学生乙",
            "week_odd": 17,
            "week_even": 18,
            "choices": {
                "odd": {str(day): "A" for day in range(1, 6)},
                "even": {str(day): "B" for day in range(1, 6)},
            },
        }

    @staticmethod
    def _parent_headers(student_id="BS001"):
        headers = {"X-Demo-Role": "parent"}
        if student_id:
            headers["X-Demo-Kid"] = student_id
        return headers

    @staticmethod
    def _teacher_headers(sub_role=None, grade=None, klass=None):
        headers = {"X-Demo-Role": "teacher"}
        if sub_role:
            headers["X-Demo-Sub"] = sub_role
        if grade:
            headers["X-Demo-Grade"] = grade
        if klass:
            headers["X-Demo-Class"] = klass
        return headers

    def _submit(self, payload=None, headers=None):
        return self.client.post(
            "/api/meal-choices",
            json=payload or self._payload(),
            headers=headers or self._teacher_headers(),
        )

    def _meal_rows(self):
        conn = sqlite3.connect(server_app.DB_PATH)
        try:
            table_exists = conn.execute(
                """SELECT 1 FROM sqlite_master
                   WHERE type = 'table' AND name = 'meal_choices'"""
            ).fetchone()
            if table_exists is None:
                return []
            return conn.execute(
                """SELECT id_card, name, grade_name, class_name, week_number,
                          parity, weekday, choice, chosen_by
                   FROM meal_choices
                   ORDER BY id_card, week_number, parity, weekday"""
            ).fetchall()
        finally:
            conn.close()

    def test_anonymous_cannot_submit_and_teacher_can_manage_student(self):
        anonymous = self.client.post("/api/meal-choices", json=self._payload())
        teacher = self._submit()

        self.assertEqual(anonymous.status_code, 403)
        self.assertEqual(teacher.status_code, 200)
        history = self.client.get(
            "/api/meal-choices/student/BS002",
            headers={"X-Demo-Role": "teacher"},
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.get_json()["choices"]), 10)

        changed = self._payload()
        changed["choices"]["odd"] = {str(day): "B" for day in range(1, 6)}
        changed["choices"]["even"] = {str(day): "A" for day in range(1, 6)}
        updated = self._submit(changed)
        self.assertEqual(updated.status_code, 200)
        updated_history = self.client.get(
            "/api/meal-choices/student/BS002",
            headers={"X-Demo-Role": "teacher"},
        ).get_json()["choices"]
        self.assertEqual(len(updated_history), 10)
        self.assertEqual(
            {(item["parity"], item["choice"]) for item in updated_history},
            {("odd", "B"), ("even", "A")},
        )

    def test_teacher_cannot_manage_unknown_student(self):
        response = self.client.post(
            "/api/meal-choices",
            json=self._payload(student_id="UNKNOWN"),
            headers={"X-Demo-Role": "teacher"},
        )

        self.assertEqual(response.status_code, 404)

    def test_parent_must_be_bound_to_a_student(self):
        response = self._submit(
            headers=self._parent_headers(student_id=None),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._meal_rows(), [])

    def test_url_demo_parent_identity_remains_supported(self):
        response = self.client.post(
            "/api/meal-choices?role=parent&kid=BS001",
            json=self._payload(student_id="BS002"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual({row[0] for row in self._meal_rows()}, {"BS001"})

    def test_only_teacher_can_list_manageable_students(self):
        parent = self.client.get(
            "/api/meal-choice-students",
            headers={"X-Demo-Role": "parent", "X-Demo-Kid": "BS001"},
        )
        teacher = self.client.get(
            "/api/meal-choice-students",
            headers={"X-Demo-Role": "teacher"},
        )

        self.assertEqual(parent.status_code, 403)
        self.assertEqual(teacher.status_code, 200)
        self.assertEqual(
            {student["idCard"] for student in teacher.get_json()["students"]},
            {"BS001", "BS002"},
        )

    def test_invalid_submissions_are_rejected_without_partial_writes(self):
        cases = []

        missing_week = self._payload()
        missing_week.pop("week_even")
        cases.append(("missing week", missing_week))

        invalid_week = self._payload()
        invalid_week["week_odd"] = "not-a-week"
        cases.append(("invalid week", invalid_week))

        incomplete = self._payload()
        incomplete["choices"]["even"].pop("5")
        cases.append(("incomplete", incomplete))

        invalid_day = self._payload()
        invalid_day["choices"]["odd"]["6"] = invalid_day["choices"]["odd"].pop("5")
        cases.append(("invalid day", invalid_day))

        invalid_choice = self._payload()
        invalid_choice["choices"]["odd"]["1"] = "C"
        cases.append(("invalid choice", invalid_choice))

        for label, payload in cases:
            with self.subTest(label=label):
                response = self._submit(
                    payload,
                    headers=self._parent_headers(),
                )
                self.assertEqual(response.status_code, 400)

        self.assertEqual(self._meal_rows(), [])

    def test_parent_submission_uses_canonical_bound_student_data(self):
        payload = self._payload(student_id="BS002")
        payload.update(
            {
                "studentName": "伪造姓名",
                "grade": "伪造年级",
                "class": "伪造班级",
            }
        )
        response = self._submit(
            payload,
            headers=self._parent_headers("BS001"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["saved"], 10)
        rows = self._meal_rows()
        self.assertEqual(len(rows), 10)
        self.assertEqual({row[0] for row in rows}, {"BS001"})
        self.assertEqual({row[1] for row in rows}, {"学生甲"})
        self.assertEqual({row[2] for row in rows}, {"五年级"})
        self.assertEqual({row[3] for row in rows}, {"1班"})
        self.assertEqual({row[8] for row in rows}, {"demo:parent"})

    def test_parent_resubmission_replaces_same_ten_days(self):
        self._submit(
            self._payload(student_id="BS001"),
            headers=self._parent_headers(),
        )
        changed = self._payload(student_id="BS001")
        changed["choices"]["odd"] = {str(day): "B" for day in range(1, 6)}
        changed["choices"]["even"] = {str(day): "A" for day in range(1, 6)}

        response = self._submit(changed, headers=self._parent_headers())

        self.assertEqual(response.status_code, 200)
        rows = self._meal_rows()
        self.assertEqual(len(rows), 10)
        self.assertEqual(
            {(row[5], row[7]) for row in rows},
            {("odd", "B"), ("even", "A")},
        )

    def test_student_history_and_list_require_authorized_scope(self):
        self._submit(
            self._payload(student_id="BS001"),
            headers=self._parent_headers("BS001"),
        )

        own = self.client.get(
            "/api/meal-choices/student/BS001",
            headers={"X-Demo-Role": "parent", "X-Demo-Kid": "BS001"},
        )
        other = self.client.get(
            "/api/meal-choices/student/BS002",
            headers={"X-Demo-Role": "parent", "X-Demo-Kid": "BS001"},
        )
        guessed_name = self.client.get(
            "/api/meal-choices/student/name:学生甲",
            headers={"X-Demo-Role": "parent", "X-Demo-Kid": "BS001"},
        )
        anonymous_list = self.client.get("/api/meal-choices")

        self.assertEqual(own.status_code, 200)
        self.assertEqual(other.status_code, 403)
        self.assertEqual(guessed_name.status_code, 403)
        self.assertEqual(anonymous_list.status_code, 403)

    def test_parent_list_is_scoped_and_teacher_filters_work(self):
        self._submit(
            self._payload(student_id="BS001"),
            headers=self._parent_headers("BS001"),
        )
        second = self._payload(student_id="BS002")
        second["week_odd"] = 19
        second["week_even"] = 20
        self._submit(second)

        parent = self.client.get(
            "/api/meal-choices?week=19&name=学生乙",
            headers=self._parent_headers("BS001"),
        )
        teacher_week = self.client.get(
            "/api/meal-choices?week=19",
            headers=self._teacher_headers(),
        )
        teacher_name = self.client.get(
            "/api/meal-choices?name=学生甲",
            headers=self._teacher_headers(),
        )

        self.assertEqual(parent.status_code, 200)
        self.assertEqual(parent.get_json()["total"], 10)
        self.assertEqual(
            {item["id_card"] for item in parent.get_json()["choices"]},
            {"BS001"},
        )
        self.assertEqual(teacher_week.get_json()["total"], 5)
        self.assertEqual(
            {item["id_card"] for item in teacher_week.get_json()["choices"]},
            {"BS002"},
        )
        self.assertEqual(teacher_name.get_json()["total"], 10)
        self.assertEqual(
            {item["id_card"] for item in teacher_name.get_json()["choices"]},
            {"BS001"},
        )

    def test_meal_statistics_require_teacher_and_aggregate_choices(self):
        self._submit(
            self._payload(student_id="BS001"),
            headers=self._parent_headers("BS001"),
        )
        second = self._payload(student_id="BS002")
        second["choices"]["odd"]["1"] = "B"
        self._submit(second)

        denied = self.client.get(
            "/api/meal-stats/grade",
            headers=self._parent_headers("BS001"),
        )
        grade = self.client.get(
            "/api/meal-stats/grade?week=17",
            headers=self._teacher_headers(),
        )
        class_summary = self.client.get(
            "/api/meal-stats/class-summary?grade=五年级&week=17&parity=odd",
            headers=self._teacher_headers(),
        )

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(grade.status_code, 200)
        grade_row = grade.get_json()["rows"][0]
        self.assertEqual(grade_row["gradeName"], "五年级")
        self.assertEqual(grade_row["week"], 17)
        self.assertEqual(grade_row["1A"], 1)
        self.assertEqual(grade_row["1B"], 1)

        self.assertEqual(class_summary.status_code, 200)
        class_row = class_summary.get_json()["rows"][0]
        self.assertEqual(class_row["grade"], "五年级")
        self.assertEqual(class_row["class"], "1班")
        self.assertEqual(class_row["1A"], 1)
        self.assertEqual(class_row["1B"], 1)

    def test_class_teacher_is_locked_to_bound_class(self):
        conn = sqlite3.connect(server_app.DB_PATH)
        conn.execute(
            "INSERT INTO students VALUES (?, ?, ?, ?)",
            ("BS003", "学生丙", "五年级", "2班"),
        )
        conn.commit()
        conn.close()
        headers = self._teacher_headers(
            sub_role="class", grade="五年级", klass="1班"
        )

        response = self.client.get(
            "/api/meal-stats/class?grade=五年级&class=2班",
            headers=headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["grade"], "五年级")
        self.assertEqual(data["class"], "1班")
        self.assertEqual(
            {student["idCard"] for student in data["students"]},
            {"BS001", "BS002"},
        )

    def test_general_teacher_can_publish_and_replace_weekly_menu(self):
        parent = self.client.post(
            "/api/menus/upload",
            json={"week": 17, "parity": "odd", "notes": "家长不可发布"},
            headers=self._parent_headers(),
        )
        class_teacher = self.client.post(
            "/api/menus/upload",
            json={"week": 17, "parity": "odd", "notes": "班主任不可发布"},
            headers=self._teacher_headers(sub_role="class"),
        )
        created = self.client.post(
            "/api/menus/upload",
            json={"week": 17, "parity": "odd", "notes": "第一版"},
            headers=self._teacher_headers(sub_role="general"),
        )
        replaced = self.client.post(
            "/api/menus/upload",
            json={"week": 17, "parity": "odd", "notes": "第二版"},
            headers=self._teacher_headers(sub_role="general"),
        )
        listed = self.client.get("/api/menus?week=17")

        self.assertEqual(parent.status_code, 403)
        self.assertEqual(class_teacher.status_code, 403)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(replaced.status_code, 200)
        self.assertEqual(created.get_json()["id"], replaced.get_json()["id"])
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.get_json()["menus"]), 1)
        self.assertEqual(listed.get_json()["menus"][0]["notes"], "第二版")


class ClubSignupRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = server_app.DB_PATH
        self.old_disable_demo = server_app.DISABLE_DEMO
        server_app.DB_PATH = os.path.join(self.temp_dir.name, "student_data.db")
        server_app.DISABLE_DEMO = False
        self.client = server_app.app.test_client()
        self.course = server_app.COURSES[0]
        self.old_capacity = self.course["capacity"]

    def tearDown(self):
        self.course["capacity"] = self.old_capacity
        server_app.DB_PATH = self.old_db_path
        server_app.DISABLE_DEMO = self.old_disable_demo
        self.temp_dir.cleanup()

    @staticmethod
    def _parent_headers(student_id="BS001"):
        return {"X-Demo-Role": "parent", "X-Demo-Kid": student_id}

    def _signup(self, course_id=None, student_id="BS001", client=None):
        return (client or self.client).post(
            "/api/clubs/signups",
            json={"course_id": course_id or self.course["id"]},
            headers=self._parent_headers(student_id),
        )

    def _signup_count(self, course_id=None, semester=None):
        conn = sqlite3.connect(server_app.DB_PATH)
        try:
            table_exists = conn.execute(
                """SELECT 1 FROM sqlite_master
                   WHERE type = 'table' AND name = 'club_signups'"""
            ).fetchone()
            if table_exists is None:
                return 0
            return conn.execute(
                """SELECT COUNT(*) FROM club_signups
                   WHERE course_id = ? AND semester = ?""",
                (course_id or self.course["id"], semester or server_app.CLUB_SEMESTER),
            ).fetchone()[0]
        finally:
            conn.close()

    def test_course_catalog_exposes_counts_only_to_teacher(self):
        self._signup()

        parent_response = self.client.get(
            "/api/clubs", headers=self._parent_headers()
        )
        teacher_response = self.client.get(
            "/api/clubs", headers={"X-Demo-Role": "teacher"}
        )

        self.assertEqual(parent_response.status_code, 200)
        self.assertEqual(teacher_response.status_code, 200)
        parent_data = parent_response.get_json()
        teacher_data = teacher_response.get_json()
        self.assertEqual(parent_data["total"], len(server_app.COURSES))
        self.assertEqual(parent_data["semester"], server_app.CLUB_SEMESTER)

        parent_course = next(
            item for item in parent_data["clubs"] if item["id"] == self.course["id"]
        )
        teacher_course = next(
            item for item in teacher_data["clubs"] if item["id"] == self.course["id"]
        )
        for sensitive_count in ("capacity", "count", "max", "remaining"):
            self.assertNotIn(sensitive_count, parent_course)
        self.assertEqual(teacher_course["capacity"], self.course["capacity"])
        self.assertEqual(teacher_course["count"], 1)
        self.assertEqual(
            teacher_course["remaining"], self.course["capacity"] - 1
        )
        self.assertFalse(teacher_course["full"])

    def test_course_catalog_filters_by_campus(self):
        campus = self.course["campus"]
        response = self.client.get(
            f"/api/clubs?campus={campus}", headers=self._parent_headers()
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        expected = [
            course for course in server_app.COURSES
            if course["campus"] == campus
        ]
        self.assertEqual(data["total"], len(expected))
        self.assertTrue(data["clubs"])
        self.assertEqual(
            {course["campus"] for course in data["clubs"]},
            {campus},
        )

    def test_signup_requires_bound_parent(self):
        anonymous = self.client.post(
            "/api/clubs/signups", json={"course_id": self.course["id"]}
        )
        unbound_parent = self.client.post(
            "/api/clubs/signups",
            json={"course_id": self.course["id"]},
            headers={"X-Demo-Role": "parent"},
        )
        teacher = self.client.post(
            "/api/clubs/signups",
            json={"course_id": self.course["id"]},
            headers={"X-Demo-Role": "teacher"},
        )

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(unbound_parent.status_code, 401)
        self.assertEqual(teacher.status_code, 401)

    def test_signup_records_bound_student_and_rejects_duplicate(self):
        created = self._signup()
        duplicate = self._signup()

        self.assertEqual(created.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertTrue(created.get_json()["success"])
        self.assertEqual(created.get_json()["course"]["id"], self.course["id"])

        conn = sqlite3.connect(server_app.DB_PATH)
        try:
            row = conn.execute(
                """SELECT student_id, semester, registered_by
                   FROM club_signups WHERE course_id = ?""",
                (self.course["id"],),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(
            row,
            ("BS001", server_app.CLUB_SEMESTER, "demo:parent"),
        )

    def test_signup_rejects_unknown_course_without_writing(self):
        response = self._signup(course_id="missing-course")

        self.assertEqual(response.status_code, 404)
        conn = sqlite3.connect(server_app.DB_PATH)
        try:
            table_exists = conn.execute(
                """SELECT 1 FROM sqlite_master
                   WHERE type = 'table' AND name = 'club_signups'"""
            ).fetchone()
            count = (
                conn.execute("SELECT COUNT(*) FROM club_signups").fetchone()[0]
                if table_exists else 0
            )
        finally:
            conn.close()
        self.assertEqual(count, 0)

    def test_capacity_check_prevents_overbooking(self):
        self.course["capacity"] = 1
        first = self._signup(student_id="BS001")
        second = self._signup(student_id="BS002")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(self._signup_count(), 1)

    def test_concurrent_signup_does_not_overbook(self):
        self.course["capacity"] = 1
        barrier = Barrier(2)

        def submit(student_id):
            client = server_app.app.test_client()
            barrier.wait(timeout=5)
            return self._signup(student_id=student_id, client=client).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(submit, ("BS001", "BS002")))

        self.assertEqual(sorted(statuses), [201, 409])
        self.assertEqual(self._signup_count(), 1)

    def test_signup_list_is_scoped_to_bound_student_and_current_semester(self):
        second_course = server_app.COURSES[1]
        stale_course = server_app.COURSES[2]
        self._signup(student_id="BS001")
        self._signup(course_id=second_course["id"], student_id="BS002")

        conn = sqlite3.connect(server_app.DB_PATH)
        try:
            conn.execute(
                """INSERT INTO club_signups
                   (student_id, course_id, semester, registered_by)
                   VALUES (?, ?, ?, ?)""",
                ("BS001", stale_course["id"], "旧学期", "test"),
            )
            conn.commit()
        finally:
            conn.close()

        first = self.client.get(
            "/api/clubs/signups", headers=self._parent_headers("BS001")
        )
        second = self.client.get(
            "/api/clubs/signups", headers=self._parent_headers("BS002")
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            [item["id"] for item in first.get_json()["signups"]],
            [self.course["id"]],
        )
        self.assertEqual(
            [item["id"] for item in second.get_json()["signups"]],
            [second_course["id"]],
        )
        self.assertEqual(
            first.get_json()["semester"],
            server_app.CLUB_SEMESTER,
        )

    def test_signup_list_requires_bound_parent(self):
        anonymous = self.client.get("/api/clubs/signups")
        unbound_parent = self.client.get(
            "/api/clubs/signups", headers={"X-Demo-Role": "parent"}
        )
        teacher = self.client.get(
            "/api/clubs/signups", headers={"X-Demo-Role": "teacher"}
        )

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(unbound_parent.status_code, 401)
        self.assertEqual(teacher.status_code, 401)

    def test_cancel_only_removes_bound_students_signup(self):
        self._signup(student_id="BS001")

        other_student = self.client.delete(
            f"/api/clubs/signups/{self.course['id']}",
            headers=self._parent_headers("BS002"),
        )
        removed = self.client.delete(
            f"/api/clubs/signups/{self.course['id']}",
            headers=self._parent_headers("BS001"),
        )
        removed_again = self.client.delete(
            f"/api/clubs/signups/{self.course['id']}",
            headers=self._parent_headers("BS001"),
        )

        self.assertEqual(other_student.status_code, 404)
        self.assertEqual(removed.status_code, 200)
        self.assertTrue(removed.get_json()["success"])
        self.assertEqual(removed_again.status_code, 404)
        self.assertEqual(self._signup_count(), 0)

    def test_cancel_rejects_unknown_course_and_non_parent(self):
        unknown = self.client.delete(
            "/api/clubs/signups/missing-course",
            headers=self._parent_headers(),
        )
        teacher = self.client.delete(
            f"/api/clubs/signups/{self.course['id']}",
            headers={"X-Demo-Role": "teacher"},
        )

        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(teacher.status_code, 401)

    def test_demo_headers_are_ignored_when_demo_is_disabled(self):
        server_app.DISABLE_DEMO = True
        response = self._signup()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self._signup_count(), 0)

    def test_database_error_rolls_back_and_returns_busy(self):
        class FailingConnection:
            def __init__(self):
                self.rolled_back = False

            def execute(self, sql, params=()):
                if sql == "BEGIN IMMEDIATE":
                    return None
                raise sqlite3.OperationalError("database unavailable")

            def rollback(self):
                self.rolled_back = True

        failing_db = FailingConnection()
        with patch.object(server_app, "_ensure_club_signups_table"), patch.object(
            server_app, "get_db", return_value=failing_db
        ):
            response = self._signup()

        self.assertEqual(response.status_code, 503)
        self.assertTrue(failing_db.rolled_back)


if __name__ == "__main__":
    unittest.main()
