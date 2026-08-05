import io
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
        conn.execute(
            """INSERT INTO nutrition_meal_plans
               (plan_date, plan_type, plan_name, calories_kcal, protein_g)
               VALUES ('2026-07-27', 'A', '测试A餐', 520, 24)"""
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

    def test_parent_cannot_execute_or_export_recommendations(self):
        headers = {
            "X-User-Role": "parent",
            "X-Nutrition-Child-Code": "C059",
        }
        execute = self.client.post(
            "/api/nutrition/recommend",
            json={"plan_date": "2026-07-27"},
            headers=headers,
        )
        export = self.client.get(
            "/api/nutrition/recommendations/export?plan_date=2026-07-27",
            headers=headers,
        )

        self.assertEqual(execute.status_code, 403)
        self.assertEqual(export.status_code, 403)

    def test_parent_can_read_meal_data_used_by_own_recommendation(self):
        response = self.client.get(
            "/api/nutrition/meal-plans/by-date/2026-07-27",
            headers={
                "X-User-Role": "parent",
                "X-Nutrition-Child-Code": "C059",
            },
        )

        self.assertEqual(response.status_code, 200)
        meals = response.get_json()["meals"]
        self.assertEqual(len(meals), 1)
        self.assertEqual(meals[0]["plan_type"], "A")
        self.assertEqual(meals[0]["protein_g"], 24)

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
        self.client.get("/api/menus")
        conn = sqlite3.connect(server_app.DB_PATH)
        conn.executemany(
            """INSERT INTO weekly_menus
               (week_number, parity, date_start, date_end, selection_deadline)
               VALUES (?, ?, ?, ?, '2099-12-31T20:00')
               ON CONFLICT(week_number, parity) DO UPDATE SET
                 date_start=excluded.date_start,
                 date_end=excluded.date_end,
                 selection_deadline=excluded.selection_deadline""",
            [
                (17, "odd", "2026-07-27", "2026-07-31"),
                (18, "even", "2026-08-03", "2026-08-07"),
                (19, "odd", "2026-08-10", "2026-08-14"),
                (20, "even", "2026-08-17", "2026-08-21"),
            ],
        )
        conn.commit()
        conn.close()

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
            headers=headers or self._parent_headers("BS002"),
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

    def test_only_bound_parent_can_submit_and_teacher_cannot_modify(self):
        anonymous = self.client.post("/api/meal-choices", json=self._payload())
        teacher = self._submit(headers=self._teacher_headers(sub_role="class"))

        self.assertEqual(anonymous.status_code, 403)
        self.assertEqual(teacher.status_code, 403)
        self.assertEqual(self._meal_rows(), [])

        parent = self._submit()
        self.assertEqual(parent.status_code, 200)
        history = self.client.get(
            "/api/meal-choices/student/BS002",
            headers=self._parent_headers("BS002"),
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
            headers=self._parent_headers("BS002"),
        ).get_json()["choices"]
        self.assertEqual(len(updated_history), 10)
        self.assertEqual(
            {(item["parity"], item["choice"]) for item in updated_history},
            {("odd", "B"), ("even", "A")},
        )

    def test_teacher_cannot_submit_even_for_unknown_student(self):
        response = self.client.post(
            "/api/meal-choices",
            json=self._payload(student_id="UNKNOWN"),
            headers={"X-Demo-Role": "teacher"},
        )

        self.assertEqual(response.status_code, 403)

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

    def test_only_bound_class_teacher_can_list_own_students(self):
        parent = self.client.get(
            "/api/meal-choice-students",
            headers={"X-Demo-Role": "parent", "X-Demo-Kid": "BS001"},
        )
        class_teacher = self.client.get(
            "/api/meal-choice-students",
            headers=self._teacher_headers(
                sub_role="class", grade="五年级", klass="1班"
            ),
        )
        general_teacher = self.client.get(
            "/api/meal-choice-students",
            headers=self._teacher_headers(sub_role="general"),
        )

        self.assertEqual(parent.status_code, 403)
        self.assertEqual(general_teacher.status_code, 403)
        self.assertEqual(class_teacher.status_code, 200)
        self.assertEqual(
            {student["idCard"] for student in class_teacher.get_json()["students"]},
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

    def test_parent_cannot_submit_after_deadline_and_teacher_cannot_correct(self):
        self.client.get("/api/menus")
        conn = sqlite3.connect(server_app.DB_PATH)
        conn.executemany(
            """INSERT INTO weekly_menus
               (week_number, parity, date_start, date_end, selection_deadline)
               VALUES (?, ?, ?, ?, '2000-01-01T20:00')
               ON CONFLICT(week_number, parity) DO UPDATE SET
                 selection_deadline=excluded.selection_deadline""",
            [
                (17, "odd", "2026-07-27", "2026-07-31"),
                (18, "even", "2026-08-03", "2026-08-07"),
            ],
        )
        conn.commit()
        conn.close()

        parent = self._submit(
            self._payload(student_id="BS001"),
            headers=self._parent_headers("BS001"),
        )
        teacher = self._submit(
            self._payload(student_id="BS002"),
            headers=self._teacher_headers(sub_role="general"),
        )

        self.assertEqual(parent.status_code, 409)
        self.assertIn("已截止", parent.get_json()["error"])
        self.assertEqual(teacher.status_code, 403)
        self.assertEqual(self._meal_rows(), [])

    def test_parent_requires_complete_menu_pair_and_deadlines(self):
        conn = sqlite3.connect(server_app.DB_PATH)
        conn.execute(
            "DELETE FROM weekly_menus WHERE week_number=18 AND parity='even'"
        )
        conn.commit()
        conn.close()

        missing_menu = self._submit(
            headers=self._parent_headers("BS002"),
        )
        self.assertEqual(missing_menu.status_code, 409)
        self.assertIn("菜单尚未完整发布", missing_menu.get_json()["error"])

        conn = sqlite3.connect(server_app.DB_PATH)
        conn.execute(
            """INSERT INTO weekly_menus
               (week_number, parity, date_start, date_end, selection_deadline)
               VALUES (18, 'even', '2026-08-03', '2026-08-07', '')"""
        )
        conn.commit()
        conn.close()

        missing_deadline = self._submit(
            headers=self._parent_headers("BS002"),
        )
        self.assertEqual(missing_deadline.status_code, 409)
        self.assertIn("截止时间尚未发布", missing_deadline.get_json()["error"])

    def test_general_teacher_cannot_publish_menu_without_deadline(self):
        response = self.client.post(
            "/api/menus/upload",
            json={"week": 21, "parity": "odd"},
            headers=self._teacher_headers(sub_role="general"),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("selectionDeadline 必填", response.get_json()["error"])

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

    def test_parent_and_class_teacher_lists_are_scoped(self):
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
        class_teacher_week = self.client.get(
            "/api/meal-choices?week=19",
            headers=self._teacher_headers(
                sub_role="class", grade="五年级", klass="1班"
            ),
        )
        class_teacher_name = self.client.get(
            "/api/meal-choices?name=学生甲",
            headers=self._teacher_headers(
                sub_role="class", grade="五年级", klass="1班"
            ),
        )
        general_teacher = self.client.get(
            "/api/meal-choices",
            headers=self._teacher_headers(sub_role="general"),
        )

        self.assertEqual(parent.status_code, 200)
        self.assertEqual(parent.get_json()["total"], 10)
        self.assertEqual(
            {item["id_card"] for item in parent.get_json()["choices"]},
            {"BS001"},
        )
        self.assertEqual(class_teacher_week.get_json()["total"], 5)
        self.assertEqual(
            {item["id_card"] for item in class_teacher_week.get_json()["choices"]},
            {"BS002"},
        )
        self.assertEqual(class_teacher_name.get_json()["total"], 10)
        self.assertEqual(
            {item["id_card"] for item in class_teacher_name.get_json()["choices"]},
            {"BS001"},
        )
        self.assertEqual(general_teacher.status_code, 403)

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
            headers=self._teacher_headers(sub_role="general"),
        )
        class_summary = self.client.get(
            "/api/meal-stats/class-summary?grade=五年级&week=17&parity=odd",
            headers=self._teacher_headers(sub_role="general"),
        )
        grade_counts = self.client.get(
            "/api/grade-counts",
            headers=self._teacher_headers(sub_role="general"),
        )
        class_teacher_grade = self.client.get(
            "/api/meal-stats/grade?week=17",
            headers=self._teacher_headers(
                sub_role="class", grade="五年级", klass="1班"
            ),
        )
        class_teacher_summary = self.client.get(
            "/api/meal-stats/class-summary?week=17",
            headers=self._teacher_headers(
                sub_role="class", grade="五年级", klass="1班"
            ),
        )
        class_teacher_grade_counts = self.client.get(
            "/api/grade-counts",
            headers=self._teacher_headers(
                sub_role="class", grade="五年级", klass="1班"
            ),
        )

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(class_teacher_grade.status_code, 403)
        self.assertEqual(class_teacher_summary.status_code, 403)
        self.assertEqual(class_teacher_grade_counts.status_code, 403)
        self.assertEqual(grade.status_code, 200)
        self.assertEqual(grade_counts.status_code, 200)
        self.assertEqual(grade_counts.get_json()["total"], 2)
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
            "/api/meal-stats/class?grade=五年级&class=2班&week_odd=17&week_even=18",
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

    def test_class_teacher_stats_include_completion_and_exact_week_pair(self):
        self._submit(
            self._payload(student_id="BS001"),
            headers=self._parent_headers("BS001"),
        )
        later = self._payload(student_id="BS001")
        later["week_odd"] = 19
        later["week_even"] = 20
        later["choices"]["odd"] = {str(day): "B" for day in range(1, 6)}
        later["choices"]["even"] = {str(day): "A" for day in range(1, 6)}
        self._submit(later, headers=self._parent_headers("BS001"))

        response = self.client.get(
            "/api/meal-stats/class?week_odd=17&week_even=18",
            headers=self._teacher_headers(
                sub_role="class", grade="五年级", klass="1班"
            ),
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(
            data["summary"],
            {
                "studentCount": 2,
                "completeCount": 1,
                "incompleteCount": 1,
                "aCount": 5,
                "bCount": 5,
            },
        )
        by_id = {student["idCard"]: student for student in data["students"]}
        self.assertEqual(by_id["BS001"]["displayName"], "学生甲")
        self.assertEqual(by_id["BS001"]["selectedCount"], 10)
        self.assertEqual(by_id["BS001"]["missingCount"], 0)
        self.assertTrue(by_id["BS001"]["isComplete"])
        self.assertEqual(by_id["BS001"]["odd_1"], "A")
        self.assertEqual(by_id["BS001"]["even_1"], "B")
        self.assertEqual(by_id["BS002"]["selectedCount"], 0)
        self.assertEqual(by_id["BS002"]["missingCount"], 10)
        self.assertFalse(by_id["BS002"]["isComplete"])

    def test_class_stats_reject_unscoped_or_unbound_teacher(self):
        unspecified = self.client.get(
            "/api/meal-stats/class?grade=五年级&class=1班",
            headers=self._teacher_headers(),
        )
        unbound_class_teacher = self.client.get(
            "/api/meal-stats/class?grade=五年级&class=1班",
            headers=self._teacher_headers(sub_role="class"),
        )

        self.assertEqual(unspecified.status_code, 403)
        self.assertEqual(unbound_class_teacher.status_code, 403)

    def test_class_stats_require_consecutive_two_week_cycle(self):
        response = self.client.get(
            "/api/meal-stats/class?week_odd=17&week_even=20",
            headers=self._teacher_headers(
                sub_role="class", grade="五年级", klass="1班"
            ),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("连续", response.get_json()["error"])

    def test_class_teacher_demo_database_without_student_table_returns_empty(self):
        conn = sqlite3.connect(server_app.DB_PATH)
        conn.execute("DROP TABLE students")
        conn.commit()
        conn.close()

        response = self.client.get(
            "/api/meal-stats/class?week_odd=17&week_even=18",
            headers=self._teacher_headers(
                sub_role="class", grade="三年级", klass="1班"
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["students"], [])

    def test_general_teacher_can_publish_and_replace_weekly_menu(self):
        parent = self.client.post(
            "/api/menus/upload",
            json={
                "week": 17, "parity": "odd", "notes": "家长不可发布",
                "selectionDeadline": "2099-12-31T20:00",
            },
            headers=self._parent_headers(),
        )
        class_teacher = self.client.post(
            "/api/menus/upload",
            json={
                "week": 17, "parity": "odd", "notes": "班主任不可发布",
                "selectionDeadline": "2099-12-31T20:00",
            },
            headers=self._teacher_headers(sub_role="class"),
        )
        unspecified_teacher = self.client.post(
            "/api/menus/upload",
            json={
                "week": 17, "parity": "odd", "notes": "未分工老师不可发布",
                "selectionDeadline": "2099-12-31T20:00",
            },
            headers=self._teacher_headers(),
        )
        created = self.client.post(
            "/api/menus/upload",
            json={
                "week": 17, "parity": "odd", "notes": "第一版",
                "selectionDeadline": "2099-12-31T20:00",
            },
            headers=self._teacher_headers(sub_role="general"),
        )
        replaced = self.client.post(
            "/api/menus/upload",
            json={
                "week": 17, "parity": "odd", "notes": "第二版",
                "selectionDeadline": "2099-12-31T20:00",
            },
            headers=self._teacher_headers(sub_role="general"),
        )
        listed = self.client.get("/api/menus?week=17")

        self.assertEqual(parent.status_code, 403)
        self.assertEqual(class_teacher.status_code, 403)
        self.assertEqual(unspecified_teacher.status_code, 403)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(replaced.status_code, 200)
        self.assertEqual(created.get_json()["id"], replaced.get_json()["id"])
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.get_json()["menus"]), 1)
        self.assertEqual(listed.get_json()["menus"][0]["notes"], "第二版")

    def test_general_teacher_can_upload_menu_image(self):
        old_upload_dir = server_app.UPLOAD_DIR
        server_app.UPLOAD_DIR = self.temp_dir.name
        try:
            response = self.client.post(
                "/api/menus/upload",
                data={
                    "week": "17",
                    "parity": "odd",
                    "dateStart": "2026-09-01",
                    "dateEnd": "2026-09-05",
                    "selectionDeadline": "2099-12-31T20:00",
                    "image": (io.BytesIO(b"demo image"), "menu.png"),
                },
                content_type="multipart/form-data",
                headers=self._teacher_headers(sub_role="general"),
            )
        finally:
            server_app.UPLOAD_DIR = old_upload_dir

        self.assertEqual(response.status_code, 200)
        image_path = response.get_json()["imagePath"]
        self.assertTrue(image_path.endswith(".png"))
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir.name, os.path.basename(image_path))))


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

    @staticmethod
    def _general_headers():
        return {"X-Demo-Role": "teacher", "X-Demo-Sub": "general"}

    @staticmethod
    def _class_headers(grade="三年级", klass="1班"):
        return {
            "X-Demo-Role": "teacher",
            "X-Demo-Sub": "class",
            "X-Demo-Grade": grade,
            "X-Demo-Class": klass,
        }

    def _set_capacity(self, capacity):
        self.client.get("/api/clubs", headers=self._parent_headers())
        conn = sqlite3.connect(server_app.DB_PATH)
        try:
            conn.execute(
                """UPDATE club_course_catalog SET capacity = ?
                   WHERE id = ? AND semester = ?""",
                (capacity, self.course["id"], server_app.CLUB_SEMESTER),
            )
            conn.commit()
        finally:
            conn.close()

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

    def _student_signup_count(self, student_id="BS001"):
        conn = sqlite3.connect(server_app.DB_PATH)
        try:
            return conn.execute(
                """SELECT COUNT(*) FROM club_signups
                   WHERE student_id = ? AND semester = ?""",
                (student_id, server_app.CLUB_SEMESTER),
            ).fetchone()[0]
        finally:
            conn.close()

    def test_course_catalog_exposes_counts_only_to_teacher(self):
        self._signup()

        parent_response = self.client.get(
            "/api/clubs", headers=self._parent_headers()
        )
        teacher_response = self.client.get(
            "/api/clubs", headers=self._general_headers()
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

    def test_only_general_teacher_can_create_update_and_archive_club(self):
        payload = {
            "campus": "东校区",
            "name": "测试创意社",
            "teacher": "测试老师",
            "weekday": "周五",
            "location": "测试教室",
            "capacity": 12,
            "note": "测试备注",
        }
        parent_create = self.client.post(
            "/api/clubs", json=payload, headers=self._parent_headers()
        )
        class_create = self.client.post(
            "/api/clubs", json=payload, headers=self._class_headers()
        )
        created = self.client.post(
            "/api/clubs", json=payload, headers=self._general_headers()
        )

        self.assertEqual(parent_create.status_code, 403)
        self.assertEqual(class_create.status_code, 403)
        self.assertEqual(created.status_code, 201)
        course_id = created.get_json()["course"]["id"]

        class_update = self.client.patch(
            f"/api/clubs/{course_id}",
            json={"capacity": 18},
            headers=self._class_headers(),
        )
        updated = self.client.patch(
            f"/api/clubs/{course_id}",
            json={"capacity": 18},
            headers=self._general_headers(),
        )
        self.assertEqual(class_update.status_code, 403)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["course"]["capacity"], 18)

        parent_archive = self.client.delete(
            f"/api/clubs/{course_id}", headers=self._parent_headers()
        )
        class_archive = self.client.delete(
            f"/api/clubs/{course_id}", headers=self._class_headers()
        )
        archived = self.client.delete(
            f"/api/clubs/{course_id}", headers=self._general_headers()
        )
        self.assertEqual(parent_archive.status_code, 403)
        self.assertEqual(class_archive.status_code, 403)
        self.assertEqual(archived.status_code, 200)

        catalog = self.client.get(
            "/api/clubs", headers=self._general_headers()
        ).get_json()["clubs"]
        self.assertNotIn(course_id, {course["id"] for course in catalog})
        signup = self._signup(course_id=course_id)
        self.assertEqual(signup.status_code, 404)

    def test_capacity_cannot_be_lower_than_current_signup_count(self):
        self._set_capacity(3)
        self._signup(student_id="BS001")
        response = self.client.patch(
            f"/api/clubs/{self.course['id']}",
            json={"capacity": 0},
            headers=self._general_headers(),
        )
        self.assertEqual(response.status_code, 400)

        self._signup(student_id="BS002")
        response = self.client.patch(
            f"/api/clubs/{self.course['id']}",
            json={"capacity": 1},
            headers=self._general_headers(),
        )
        self.assertEqual(response.status_code, 409)

    def test_teacher_can_view_current_course_signup_students(self):
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
                ("BS002", "学生乙", "五年级", "2班"),
            ],
        )
        conn.commit()
        conn.close()
        self._signup(student_id="BS001")
        self._signup(student_id="BS002")

        response = self.client.get(
            f"/api/clubs/{self.course['id']}/signups",
            headers=self._general_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["semester"], server_app.CLUB_SEMESTER)
        self.assertEqual(data["course"]["id"], self.course["id"])
        self.assertEqual(data["course"]["count"], 2)
        self.assertEqual(
            data["students"],
            [
                {
                    "studentId": "BS001",
                    "name": "学生甲",
                    "grade": "五年级",
                    "class": "1班",
                    "registeredAt": data["students"][0]["registeredAt"],
                },
                {
                    "studentId": "BS002",
                    "name": "学生乙",
                    "grade": "五年级",
                    "class": "2班",
                    "registeredAt": data["students"][1]["registeredAt"],
                },
            ],
        )

    def test_course_signup_students_requires_teacher_and_valid_course(self):
        anonymous = self.client.get(
            f"/api/clubs/{self.course['id']}/signups"
        )
        parent = self.client.get(
            f"/api/clubs/{self.course['id']}/signups",
            headers=self._parent_headers(),
        )
        missing = self.client.get(
            "/api/clubs/missing-course/signups",
            headers=self._general_headers(),
        )
        class_teacher = self.client.get(
            f"/api/clubs/{self.course['id']}/signups",
            headers=self._class_headers(),
        )

        self.assertEqual(anonymous.status_code, 403)
        self.assertEqual(parent.status_code, 403)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(class_teacher.status_code, 403)

    def test_class_teacher_sees_every_student_and_their_clubs_in_bound_class(self):
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
                ("BS001", "学生甲", "三年级", "1班"),
                ("BS002", "学生乙", "三年级", "1班"),
                ("BS003", "学生丙", "三年级", "1班"),
                ("BS004", "其他班学生", "三年级", "2班"),
            ],
        )
        conn.commit()
        conn.close()
        self._signup(student_id="BS001")
        self._signup(student_id="BS004")

        response = self.client.get(
            "/api/clubs/class-signups?grade=三年级&class=2班",
            headers=self._class_headers("三年级", "1班"),
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["grade"], "三年级")
        self.assertEqual(data["class"], "1班")
        self.assertEqual(data["totalStudents"], 3)
        self.assertEqual(data["signedStudents"], 1)
        self.assertEqual(
            [student["name"] for student in data["students"]],
            ["学生丙", "学生乙", "学生甲"],
        )
        by_name = {student["name"]: student for student in data["students"]}
        self.assertEqual(
            {club["id"] for club in by_name["学生甲"]["clubs"]},
            {self.course["id"]},
        )
        self.assertEqual(by_name["学生乙"]["clubs"], [])
        self.assertEqual(by_name["学生丙"]["clubs"], [])
        self.assertNotIn("其他班学生", by_name)

    def test_class_signup_overview_rejects_other_roles_and_unbound_teacher(self):
        parent = self.client.get(
            "/api/clubs/class-signups", headers=self._parent_headers()
        )
        general = self.client.get(
            "/api/clubs/class-signups", headers=self._general_headers()
        )
        unbound_class = self.client.get(
            "/api/clubs/class-signups",
            headers={"X-Demo-Role": "teacher", "X-Demo-Sub": "class"},
        )

        self.assertEqual(parent.status_code, 403)
        self.assertEqual(general.status_code, 403)
        self.assertEqual(unbound_class.status_code, 403)

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

    def test_signup_rejects_course_on_same_weekday(self):
        same_weekday_course = server_app.COURSES[1]
        self.assertEqual(
            self.course["weekday"],
            same_weekday_course["weekday"],
        )
        first = self._signup()
        conflict = self._signup(course_id=same_weekday_course["id"])

        self.assertEqual(first.status_code, 201)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.get_json()["code"], "CLUB_TIME_CONFLICT")
        self.assertIn(self.course["name"], conflict.get_json()["error"])
        self.assertEqual(self._student_signup_count(), 1)

    def test_each_student_can_signup_for_at_most_one_course(self):
        courses = [
            server_app.COURSES[0],
            server_app.COURSES[3],
        ]
        self.assertEqual(len({course["weekday"] for course in courses}), 2)

        responses = [
            self._signup(course_id=course["id"])
            for course in courses
        ]

        self.assertEqual(
            [response.status_code for response in responses],
            [201, 409],
        )
        self.assertEqual(
            responses[-1].get_json()["code"],
            "CLUB_LIMIT_REACHED",
        )
        self.assertEqual(self._student_signup_count(), 1)

    def test_concurrent_requests_cannot_exceed_student_signup_limit(self):
        candidates = [server_app.COURSES[0], server_app.COURSES[3]]
        barrier = Barrier(2)

        def submit(course):
            client = server_app.app.test_client()
            barrier.wait(timeout=5)
            return self._signup(
                course_id=course["id"],
                client=client,
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(submit, candidates))

        self.assertEqual(sorted(statuses), [201, 409])
        self.assertEqual(self._student_signup_count(), 1)

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
        self._set_capacity(1)
        first = self._signup(student_id="BS001")
        second = self._signup(student_id="BS002")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(self._signup_count(), 1)

    def test_concurrent_signup_does_not_overbook(self):
        self._set_capacity(1)
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
