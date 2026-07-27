import os
import sqlite3
import tempfile
import unittest

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

    def test_anonymous_and_teacher_cannot_submit(self):
        anonymous = self.client.post("/api/meal-choices", json=self._payload())
        teacher = self.client.post(
            "/api/meal-choices",
            json=self._payload(),
            headers={"X-Demo-Role": "teacher"},
        )

        self.assertEqual(anonymous.status_code, 403)
        self.assertEqual(teacher.status_code, 403)

    def test_incomplete_submission_is_rejected(self):
        payload = self._payload()
        payload["choices"]["even"].pop("5")

        response = self.client.post(
            "/api/meal-choices",
            json=payload,
            headers={"X-Demo-Role": "parent", "X-Demo-Kid": "BS001"},
        )

        self.assertEqual(response.status_code, 400)
        conn = sqlite3.connect(server_app.DB_PATH)
        try:
            table_exists = conn.execute(
                """SELECT 1 FROM sqlite_master
                   WHERE type = 'table' AND name = 'meal_choices'"""
            ).fetchone()
            count = (
                conn.execute("SELECT COUNT(*) FROM meal_choices").fetchone()[0]
                if table_exists else 0
            )
        finally:
            conn.close()
        self.assertEqual(count, 0)

    def test_parent_submission_uses_server_bound_student(self):
        response = self.client.post(
            "/api/meal-choices",
            json=self._payload(student_id="BS002"),
            headers={"X-Demo-Role": "parent", "X-Demo-Kid": "BS001"},
        )

        self.assertEqual(response.status_code, 200)
        conn = sqlite3.connect(server_app.DB_PATH)
        ids = {row[0] for row in conn.execute("SELECT id_card FROM meal_choices")}
        conn.close()
        self.assertEqual(ids, {"BS001"})

    def test_student_history_and_list_require_authorized_scope(self):
        self.client.post(
            "/api/meal-choices",
            json=self._payload(student_id="BS001"),
            headers={"X-Demo-Role": "parent", "X-Demo-Kid": "BS001"},
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

    def test_signup_requires_bound_parent_and_rejects_duplicate(self):
        anonymous = self.client.post(
            "/api/clubs/signups", json={"course_id": self.course["id"]}
        )
        headers = {"X-Demo-Role": "parent", "X-Demo-Kid": "BS001"}
        created = self.client.post(
            "/api/clubs/signups",
            json={"course_id": self.course["id"]},
            headers=headers,
        )
        duplicate = self.client.post(
            "/api/clubs/signups",
            json={"course_id": self.course["id"]},
            headers=headers,
        )

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)

    def test_capacity_check_prevents_overbooking(self):
        self.course["capacity"] = 1
        first = self.client.post(
            "/api/clubs/signups",
            json={"course_id": self.course["id"]},
            headers={"X-Demo-Role": "parent", "X-Demo-Kid": "BS001"},
        )
        second = self.client.post(
            "/api/clubs/signups",
            json={"course_id": self.course["id"]},
            headers={"X-Demo-Role": "parent", "X-Demo-Kid": "BS002"},
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        conn = sqlite3.connect(server_app.DB_PATH)
        count = conn.execute(
            "SELECT COUNT(*) FROM club_signups WHERE course_id = ?",
            (self.course["id"],),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
