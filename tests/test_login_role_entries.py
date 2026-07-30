import tempfile
import unittest
from pathlib import Path

from server import app as server_app
from server import manage_accounts


class LoginPageEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (
            Path(__file__).resolve().parents[1] / "login.html"
        ).read_text(encoding="utf-8")

    def test_page_exposes_exactly_three_identity_entries(self):
        self.assertEqual(self.html.count('class="role-entry-btn"'), 3)
        for entry in ("general_teacher", "class_teacher", "parent"):
            self.assertIn(f'data-entry="{entry}"', self.html)

    def test_selected_entry_is_sent_with_login_request(self):
        self.assertIn('id="loginForm" onsubmit="return doLogin(event)" hidden', self.html)
        self.assertIn(
            "JSON.stringify({username:u, password:p, entry})",
            self.html,
        )

    def test_each_entry_shows_a_fillable_demo_account(self):
        for username in ("demo_general", "demo_class", "demo_parent"):
            self.assertIn(f"username: '{username}'", self.html)
        self.assertIn("document.getElementById('fillExample').addEventListener", self.html)
        self.assertIn("value = '123456'", self.html)

    def test_local_preview_uses_the_local_api_server(self):
        self.assertIn("location.protocol === 'file:'", self.html)
        self.assertIn("'http://127.0.0.1:5051'", self.html)
        self.assertIn("fetch(`${LOCAL_API_BASE}/api/login`", self.html)


class NutritionRoleViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.health_html = (root / "island-health.html").read_text(encoding="utf-8")
        cls.recommendations_html = (
            root / "nutrition" / "recommendations.html"
        ).read_text(encoding="utf-8")
        cls.common_js = (root / "nutrition" / "common.js").read_text(encoding="utf-8")

    def test_health_island_passes_teacher_scope_to_nutrition(self):
        self.assertIn('data-show-for="teacher,parent,admin"', self.health_html)
        self.assertIn("params.set('subRole', subRole)", self.health_html)
        self.assertIn("params.set('grade', grade)", self.health_html)
        self.assertIn("params.set('class', klass)", self.health_html)

    def test_nutrition_page_has_three_role_specific_views(self):
        for view_id in (
            "parentRecommendationView",
            "generalTeacherView",
            "classTeacherView",
        ):
            self.assertIn(f'id="{view_id}"', self.recommendations_html)
        self.assertIn("/api/menus/upload", self.recommendations_html)
        self.assertIn("/api/meal-stats/grade", self.recommendations_html)
        self.assertIn("/api/meal-stats/class", self.recommendations_html)
        for element_id in (
            "menuPreview",
            "gtTotalCount",
            "gtACount",
            "gtBCount",
            "gtGradeCount",
            "gtStatsScope",
        ):
            self.assertIn(f'id="{element_id}"', self.recommendations_html)

    def test_nutrition_requests_include_teacher_scope(self):
        self.assertIn("'X-Demo-Sub': NUTRITION_SUB_ROLE", self.common_js)
        self.assertIn("'X-Demo-Grade': NUTRITION_GRADE", self.common_js)
        self.assertIn("'X-Demo-Class': NUTRITION_CLASS", self.common_js)

    def test_local_file_navigation_uses_repo_pages_and_local_api(self):
        self.assertIn("location.protocol === 'file:'", self.health_html)
        self.assertIn("`nutrition/recommendations.html?", self.health_html)
        self.assertIn(
            "location.protocol === 'file:' ? 'http://127.0.0.1:5051' : ''",
            self.common_js,
        )
        self.assertIn("'../island-health.html'", self.common_js)
        self.assertIn("NUTRITION_PLATFORM_BASE + path", self.common_js)
        self.assertIn(
            "NUTRITION_PLATFORM_BASE + '/api/menus/upload'",
            self.recommendations_html,
        )


class LoginRoleEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = server_app.DB_PATH
        self.old_manage_db_path = manage_accounts.DB
        db_path = str(Path(self.temp_dir.name) / "accounts.db")
        server_app.DB_PATH = db_path
        manage_accounts.DB = db_path
        server_app.app.config["TESTING"] = True

        db = manage_accounts.conn()
        for account in manage_accounts.DEMO:
            manage_accounts.upsert(db, **account)
        db.close()
        self.client = server_app.app.test_client()

    def tearDown(self):
        server_app.DB_PATH = self.old_db_path
        manage_accounts.DB = self.old_manage_db_path
        self.temp_dir.cleanup()

    def login(self, username, entry=None):
        payload = {"username": username, "password": "123456"}
        if entry is not None:
            payload["entry"] = entry
        return self.client.post("/api/login", json=payload)

    def test_each_entry_accepts_its_matching_account(self):
        cases = [
            ("demo_general", "general_teacher", "teacher", "general"),
            ("demo_class", "class_teacher", "teacher", "class"),
            ("demo_parent", "parent", "parent", None),
        ]
        for username, entry, role, sub_role in cases:
            with self.subTest(entry=entry):
                response = self.login(username, entry)
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertTrue(payload["sessionToken"])
                user = payload["user"]
                self.assertEqual(user["role"], role)
                self.assertEqual(user["sub_role"], sub_role)

    def test_password_login_token_preserves_server_side_role_scope(self):
        login = self.login("demo_class", "class_teacher").get_json()
        old_disable_demo = server_app.DISABLE_DEMO
        server_app.DISABLE_DEMO = True
        try:
            response = self.client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {login['sessionToken']}"},
            )
        finally:
            server_app.DISABLE_DEMO = old_disable_demo

        self.assertEqual(response.status_code, 200)
        user = response.get_json()
        self.assertEqual(user["role"], "teacher")
        self.assertEqual(user["subRole"], "class")
        self.assertEqual(user["boundGrade"], "三年级")
        self.assertEqual(user["boundClass"], "1班")

    def test_entry_rejects_an_account_from_another_identity(self):
        response = self.login("demo_general", "class_teacher")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.get_json()["error"],
            "该账号不属于所选身份入口",
        )

    def test_invalid_entry_is_rejected(self):
        response = self.login("demo_general", "administrator")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "登录身份入口无效")

    def test_legacy_login_without_entry_remains_compatible(self):
        response = self.login("demo_general")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["role"], "teacher")


if __name__ == "__main__":
    unittest.main()
