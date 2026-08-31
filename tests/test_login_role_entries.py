import sqlite3
import tempfile
import time
import unittest
import base64
import json
from pathlib import Path
from unittest import mock
from werkzeug.security import generate_password_hash

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
            "JSON.stringify({username:u, password:p, entry, campus:CAMPUS_ID})",
            self.html,
        )
        self.assertIn("new URLSearchParams(location.search).get('campus')", self.html)

    def test_manual_login_does_not_expose_demo_credentials(self):
        for username in ("demo_general", "demo_class", "demo_parent"):
            self.assertNotIn(f"username: '{username}'", self.html)
        self.assertNotIn("document.getElementById('fillExample').addEventListener", self.html)
        self.assertNotIn("value = '123456'", self.html)
        self.assertIn('id="username"', self.html)
        self.assertIn('id="password"', self.html)

    def test_local_preview_uses_the_local_api_server(self):
        self.assertIn("location.protocol === 'file:'", self.html)
        self.assertIn("'http://127.0.0.1:5051'", self.html)
        self.assertIn("fetch(`${LOCAL_API_BASE}/api/login`", self.html)

    def test_login_page_is_password_only(self):
        self.assertNotIn("dingtalk.open.js", self.html)
        self.assertNotIn("dingtalk-bootstrap.js", self.html)
        self.assertNotIn("autoJumpOnDingtalkAuth", self.html)
        self.assertIn("sessionStorage.clear();", self.html)
        self.assertIn("bs_persistent_session_${CAMPUS_ID}", self.html)
        self.assertIn("restoreSavedLogin();", self.html)
        self.assertIn("user.campus !== CAMPUS_ID", self.html)
        self.assertIn(
            "location.replace(`island-homepage.html?campus=${encodeURIComponent(user.campus || CAMPUS_ID)}&auth=1`)",
            self.html,
        )
        self.assertNotIn("/nutrition/recommendations.html?${params.toString()}#parentSelection", self.html)
        self.assertIn("user.campus || CAMPUS_ID", self.html)

    def test_logout_clears_persistent_session_for_current_campus(self):
        user_auth = (
            Path(__file__).resolve().parents[1] / "assets" / "user-auth.js"
        ).read_text(encoding="utf-8")
        self.assertIn("localStorage.removeItem('bs_persistent_session_' + campus)", user_auth)
        self.assertIn("login.html?campus=' + encodeURIComponent(campus)", user_auth)


class StudentHomepageIslandVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (
            Path(__file__).resolve().parents[1] / "island-homepage.html"
        ).read_text(encoding="utf-8")

    def test_student_parent_homepage_exposes_all_six_islands(self):
        island_keys = ("growth", "interest", "art", "health", "literacy", "labor")
        for key in island_keys:
            self.assertIn(f"onclick=\"enterIsland('{key}'", self.html)
        self.assertEqual(self.html.count('class="hotspot"'), 6)
        self.assertNotIn('class="hotspot" data-hide-for="parent"', self.html)
        self.assertNotIn("location.replace(`/dingtalk-health?campus=", self.html)

    def test_cached_login_student_keeps_grade_and_class(self):
        user_auth = (
            Path(__file__).resolve().parents[1] / "assets" / "user-auth.js"
        ).read_text(encoding="utf-8")
        self.assertIn("stu.grade_name || stu.grade", user_auth)
        self.assertIn("stu.class_name || stu.class", user_auth)
        self.assertIn("stu.id_card || stu.idCard", user_auth)


class DingTalkSourceSafetyTests(unittest.TestCase):
    def test_auth_code_material_is_not_written_to_logs(self):
        source = (
            Path(__file__).resolve().parents[1] / "server" / "app.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("auth_code[:", source)
        self.assertNotIn("auth_code_clean[:", source)

    def test_legacy_dingtalk_html_routes_receive_injected_campus_config(self):
        client = server_app.app.test_client()
        with mock.patch.object(
            server_app,
            "_get_campus_dt",
            return_value={"corpId": "ding-test-corp", "name": "本部"},
        ):
            for path in (
                "/island-homepage.html?campus=benbu&auth=1",
                "/login.html?campus=benbu",
                "/island-health.html?campus=benbu",
            ):
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200)
                    html = response.get_data(as_text=True)
                    if path == "/login.html?campus=benbu":
                        self.assertNotIn("ding-test-corp", html)
                        self.assertNotIn("dingtalk.open.js", html)
                    else:
                        self.assertIn("ding-test-corp", html)
                        self.assertIn('window.BS_CAMPUS_ID = \'benbu\'', html)
                    self.assertNotIn("__INJECT_CORP_ID__", html)
                    self.assertNotIn("__INJECT_CAMPUS_ID__", html)
                    self.assertEqual(
                        response.headers["Cache-Control"],
                        "no-cache, no-store, must-revalidate",
                    )

    def test_password_accounts_do_not_offer_cross_role_or_child_switching(self):
        root = Path(__file__).resolve().parents[1]
        bootstrap = (root / "assets" / "dingtalk-bootstrap.js").read_text(encoding="utf-8")
        self.assertIn("BS_PASSWORD_LOGIN_ONLY", bootstrap)
        self.assertIn("BS_DINGTALK_AUTH_DISABLED", bootstrap)

    def test_password_mode_application_entries_force_login(self):
        client = server_app.app.test_client()
        with mock.patch.object(server_app, 'PASSWORD_LOGIN_ONLY', True):
            for path in ('/', '/dingtalk-home?campus=benbu', '/dingtalk-health?campus=benbu', '/island-homepage.html?campus=benbu'):
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 302)
                    self.assertIn('/login.html?campus=benbu', response.headers['Location'])
            response = client.get('/island-homepage.html?campus=benbu&auth=1')
            self.assertEqual(response.status_code, 200)

    def test_frontend_has_no_default_teacher_identity(self):
        root = Path(__file__).resolve().parents[1]
        user_auth = (root / 'assets' / 'user-auth.js').read_text(encoding='utf-8')
        nutrition_common = (root / 'nutrition' / 'common.js').read_text(encoding='utf-8')
        self.assertIn("role: 'none'", user_auth)
        self.assertIn("!global.BS_DINGTALK_AUTH_DISABLED", user_auth)
        self.assertNotIn("data.role || 'teacher'", user_auth)
        self.assertIn("!NUTRITION_SESSION_TOKEN", nutrition_common)
        self.assertIn("sessionStorage.getItem('bs_role')", nutrition_common)

    def test_parent_student_requests_reuse_password_session(self):
        root = Path(__file__).resolve().parents[1]
        user_auth = (root / "assets" / "user-auth.js").read_text(encoding="utf-8")
        health = (root / "island-health.html").read_text(encoding="utf-8")
        self.assertIn("headers: _sessionHeaders()", user_auth)
        self.assertIn("authHeaders(includeJson){ return _sessionHeaders(includeJson); }", user_auth)
        self.assertIn("fetch(url, {headers})", health)
        self.assertNotIn("?role=parent&kid=", health)


class IndependentPasswordAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_auth_db = server_app.AUTH_DB_PATH
        self.old_student_db = server_app.DB_PATH
        server_app.AUTH_DB_PATH = str(Path(self.temp_dir.name) / "auth.db")
        server_app.DB_PATH = str(Path(self.temp_dir.name) / "students.db")
        db = sqlite3.connect(server_app.AUTH_DB_PATH)
        db.execute('''CREATE TABLE auth_accounts(
            id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT,
            role TEXT, sub_role TEXT, campus_id TEXT, display_name TEXT,
            bound_student_userid TEXT, bound_id_card TEXT, bound_grade TEXT,
            bound_class TEXT, is_active INTEGER, auth_version INTEGER,
            failed_attempts INTEGER, locked_until INTEGER, last_login_at TEXT
        )''')
        accounts = [
            (1, "STUDENT-UID", "parent", None, "测试学生", "STUDENT-UID", "S001", "一年级", "2班"),
            (2, "TEACHER-UID", "teacher", "class", "测试班主任", None, None, "一年级", "2班"),
            (3, "GENERAL-UID", "teacher", "general", "测试总务", None, None, None, None),
        ]
        for account in accounts:
            db.execute(
                '''INSERT INTO auth_accounts VALUES(
                    ?, ?, ?, ?, ?, 'benbu', ?, ?, ?, ?, ?, 1, 1, 0, NULL, NULL
                )''',
                (account[0], account[1], generate_password_hash("Pass-123", method="pbkdf2:sha256:1000"),
                 account[2], account[3], account[4], account[5], account[6], account[7], account[8]),
            )
        db.commit()
        db.close()
        db = sqlite3.connect(server_app.DB_PATH)
        db.execute('''CREATE TABLE students_benbu(
            dingtalk_userid TEXT PRIMARY KEY, id_card TEXT, name TEXT,
            grade_name TEXT, class_name TEXT
        )''')
        db.execute("INSERT INTO students_benbu VALUES('STUDENT-UID','S001','测试学生','一年级','2班')")
        db.commit()
        db.close()
        self.client = server_app.app.test_client()

    def tearDown(self):
        server_app.AUTH_DB_PATH = self.old_auth_db
        server_app.DB_PATH = self.old_student_db
        self.temp_dir.cleanup()

    def _login(self, username, entry):
        return self.client.post('/api/login', json={
            'username': username, 'password': 'Pass-123', 'entry': entry,
            'campus': 'benbu',
        })

    def test_three_accounts_have_exactly_one_allowed_entry(self):
        cases = [
            ('STUDENT-UID', 'parent', 'parent', None),
            ('TEACHER-UID', 'class_teacher', 'teacher', 'class'),
            ('GENERAL-UID', 'general_teacher', 'teacher', 'general'),
        ]
        for username, entry, role, sub_role in cases:
            with self.subTest(username=username):
                response = self._login(username, entry)
                self.assertEqual(response.status_code, 200)
                user = response.get_json()['user']
                self.assertEqual(user['role'], role)
                self.assertEqual(user['sub_role'], sub_role)

    def test_wrong_identity_entry_is_rejected(self):
        response = self._login('STUDENT-UID', 'class_teacher')
        self.assertEqual(response.status_code, 403)

    def test_token_contains_no_role_or_student_scope(self):
        token = self._login('STUDENT-UID', 'parent').get_json()['sessionToken']
        payload = json.loads(base64.urlsafe_b64decode(token.split('.')[0]).decode())
        self.assertEqual(set(payload), {'accountId', 'authVersion', 'campus', 'exp'})
        self.assertEqual(payload['campus'], 'benbu')

    def test_account_auth_me_returns_restore_fields(self):
        login = self._login('STUDENT-UID', 'parent').get_json()
        response = self.client.get(
            '/api/auth/me',
            headers={'Authorization': f"Bearer {login['sessionToken']}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['owner'], 'account:1')
        self.assertEqual(data['campus'], 'benbu')
        self.assertEqual(data['displayName'], '测试学生')

    def test_dingtalk_sso_endpoint_is_disabled(self):
        with mock.patch.object(server_app, 'PASSWORD_LOGIN_ONLY', True):
            response = self.client.post('/api/auth/dingtalk', json={'authCode': 'unused'})
        self.assertEqual(response.status_code, 410)

    def test_account_cannot_use_role_switch_endpoint(self):
        token = self._login('TEACHER-UID', 'class_teacher').get_json()['sessionToken']
        response = self.client.post(
            '/api/switch-role', json={'role': 'parent'},
            headers={'Authorization': f'Bearer {token}'},
        )
        self.assertEqual(response.status_code, 403)


class CampusDatabaseIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.old_paths = (
            server_app.DB_PATH, server_app.AUTH_DB_PATH,
            server_app.BAOLIN_DB_PATH, server_app.BAOLIN_AUTH_DB_PATH,
        )
        server_app.DB_PATH = str(root / 'benbu-students.db')
        server_app.AUTH_DB_PATH = str(root / 'benbu-auth.db')
        server_app.BAOLIN_DB_PATH = str(root / 'baolin-students.db')
        server_app.BAOLIN_AUTH_DB_PATH = str(root / 'baolin-auth.db')
        self._seed_campus('benbu', '本部学生')
        self._seed_campus('baolin', '宝林学生')
        self.client = server_app.app.test_client()

    def tearDown(self):
        (
            server_app.DB_PATH, server_app.AUTH_DB_PATH,
            server_app.BAOLIN_DB_PATH, server_app.BAOLIN_AUTH_DB_PATH,
        ) = self.old_paths
        self.temp_dir.cleanup()

    def _seed_campus(self, campus, display_name):
        auth_path = server_app._campus_db_path(campus, auth=True)
        auth = sqlite3.connect(auth_path)
        auth.execute('''CREATE TABLE auth_accounts(
            id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT,
            role TEXT, sub_role TEXT, campus_id TEXT, display_name TEXT,
            bound_student_userid TEXT, bound_id_card TEXT, bound_grade TEXT,
            bound_class TEXT, is_active INTEGER, auth_version INTEGER,
            failed_attempts INTEGER, locked_until INTEGER, last_login_at TEXT
        )''')
        auth.execute(
            '''INSERT INTO auth_accounts VALUES(
                1, 'SHARED-USER', ?, 'parent', NULL, ?, ?,
                'SHARED-USER', ?, '一年级', '1班', 1, 1, 0, NULL, NULL
            )''',
            (generate_password_hash('Pass-123', method='pbkdf2:sha256:1000'),
             campus, display_name, f'{campus}-S001'),
        )
        auth.commit()
        auth.close()

        business = sqlite3.connect(server_app._campus_db_path(campus))
        table = server_app._students_table(campus)
        business.execute(f'''CREATE TABLE {table}(
            dingtalk_userid TEXT PRIMARY KEY, id_card TEXT, name TEXT,
            grade_name TEXT, class_name TEXT
        )''')
        business.execute(
            f'INSERT INTO {table} VALUES(?,?,?,?,?)',
            ('SHARED-USER', f'{campus}-S001', display_name, '一年级', '1班'),
        )
        business.commit()
        business.close()

    def test_baolin_token_selects_baolin_auth_and_business_databases(self):
        response = self.client.post('/api/login', json={
            'username': 'SHARED-USER', 'password': 'Pass-123',
            'entry': 'parent', 'campus': 'baolin',
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['user']['displayName'], '宝林学生')
        token_data = json.loads(base64.urlsafe_b64decode(
            payload['sessionToken'].split('.')[0]
        ).decode())
        self.assertEqual(token_data['campus'], 'baolin')

        me = self.client.get(
            '/api/auth/me?campus=benbu',
            headers={'Authorization': f"Bearer {payload['sessionToken']}"},
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.get_json()['boundStudent']['displayName'], '宝林学生')

    def test_login_rejects_missing_or_unknown_campus(self):
        base = {'username': 'SHARED-USER', 'password': 'Pass-123', 'entry': 'parent'}
        self.assertEqual(self.client.post('/api/login', json=base).status_code, 400)
        self.assertEqual(
            self.client.post('/api/login', json={**base, 'campus': 'other'}).status_code,
            400,
        )

    def test_baolin_entry_is_fixed_and_unknown_entry_is_rejected(self):
        response = self.client.get('/dingtalk-home?campus=baolin')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login.html?campus=baolin', response.headers['Location'])
        self.assertEqual(self.client.get('/dingtalk-home?campus=other').status_code, 400)


class ParentNickBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = server_app.DB_PATH
        server_app.DB_PATH = str(Path(self.temp_dir.name) / "parent-nick.db")

    def tearDown(self):
        server_app.DB_PATH = self.old_db_path
        self.temp_dir.cleanup()

    def _seed(self, students, union_id="parent-union"):
        with server_app.app.app_context():
            server_app._ensure_user_bindings_table()
            server_app._ensure_parent_kids_table()
            db = server_app.get_db()
            db.execute(
                """CREATE TABLE students_benbu(
                       dingtalk_userid TEXT PRIMARY KEY,
                       id_card TEXT UNIQUE,
                       name TEXT NOT NULL,
                       grade_name TEXT,
                       class_name TEXT
                   )"""
            )
            db.executemany(
                "INSERT INTO students_benbu VALUES(?,?,?,?,?)", students
            )
            db.execute(
                """INSERT INTO user_bindings(
                       dingtalk_unionid, role, bound_name, dingtalk_userid
                   ) VALUES(?, 'parent', '待绑定家长', 'PARENT-USER-ID')""",
                (union_id,),
            )
            db.commit()

    def test_unique_parent_nick_binds_child_by_authoritative_student_userid(self):
        self._seed([
            ("student-user-001", "BS_00045", "示例学生甲", "一年级", "2班")
        ])

        with server_app.app.app_context():
            db = server_app.get_db()
            result = server_app._auto_bind_parent_kids_from_nick(
                db, "parent-union", "benbu", "示例学生甲妈妈"
            )
            binding = db.execute(
                """SELECT dingtalk_userid, bound_student_userid, bound_name,
                          bound_grade, bound_class
                   FROM user_bindings WHERE dingtalk_unionid='parent-union'"""
            ).fetchone()
            kid = db.execute(
                """SELECT kid_dingtalk_userid, kid_name, is_active
                   FROM parent_kids WHERE union_id='parent-union'"""
            ).fetchone()

        self.assertEqual(len(result), 1)
        self.assertEqual(binding[0], "PARENT-USER-ID")
        self.assertEqual(binding[1:], ("student-user-001", "示例学生甲", "一年级", "2班"))
        self.assertEqual(tuple(kid), ("student-user-001", "示例学生甲", 1))

    def test_multi_child_parent_nick_creates_switchable_relationships(self):
        self._seed([
            ("student-user-002", "KID-1", "示例学生乙", "二年级", "1班"),
            ("student-user-003", "KID-2", "示例学生丙", "四年级", "2班"),
        ])

        with server_app.app.app_context():
            db = server_app.get_db()
            result = server_app._auto_bind_parent_kids_from_nick(
                db, "parent-union", "benbu", "示例学生乙妈妈/示例学生丙妈妈"
            )
            kids = db.execute(
                """SELECT kid_name, is_active FROM parent_kids
                   WHERE union_id='parent-union' ORDER BY id"""
            ).fetchall()

        self.assertEqual(len(result), 2)
        self.assertEqual([tuple(row) for row in kids], [("示例学生乙", 1), ("示例学生丙", 0)])

    def test_duplicate_student_name_is_never_auto_bound(self):
        self._seed([
            ("STUDENT-1", "KID-1", "同名学生", "二年级", "1班"),
            ("STUDENT-2", "KID-2", "同名学生", "五年级", "4班"),
        ])

        with server_app.app.app_context():
            db = server_app.get_db()
            result = server_app._auto_bind_parent_kids_from_nick(
                db, "parent-union", "benbu", "同名学生妈妈"
            )
            count = db.execute(
                "SELECT COUNT(*) FROM parent_kids WHERE union_id='parent-union'"
            ).fetchone()[0]
            binding = db.execute(
                """SELECT bound_student_userid FROM user_bindings
                   WHERE dingtalk_unionid='parent-union'"""
            ).fetchone()[0]

        self.assertEqual(result, [])
        self.assertEqual(count, 0)
        self.assertIsNone(binding)


class NutritionRoleViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.health_html = (root / "island-health.html").read_text(encoding="utf-8")
        cls.recommendations_html = (
            root / "nutrition" / "recommendations.html"
        ).read_text(encoding="utf-8")
        cls.common_js = (root / "nutrition" / "common.js").read_text(encoding="utf-8")

    def test_health_island_has_scoped_parent_and_teacher_nutrition_entries(self):
        self.assertIn(
            'id="parent-nutrition-entry" data-show-for="parent"',
            self.health_html,
        )
        self.assertIn('id="parent-nutrition-entry" data-show-for="parent" class="meal-flow-card meal-flow-toggle" href="nutrition/recommendations.html" onclick="enterNutritionRecommendations(event)" style="display:none!important"', self.health_html)
        self.assertIn('id="parent-growth-panel" style="display:none!important"', self.health_html)
        self.assertIn('id="parent-daily-panel" class="meal-flow" hidden style="display:none!important"', self.health_html)
        self.assertIn(
            'id="nutrition-entry" data-show-for="teacher,admin"',
            self.health_html,
        )
        self.assertIn("params.set('subRole', subRole)", self.health_html)
        self.assertIn("params.set('grade', grade)", self.health_html)
        self.assertIn("params.set('class', klass)", self.health_html)

    def test_general_teacher_health_island_redirects_to_nutrition_stats(self):
        self.assertIn("if(event) event.preventDefault()", self.health_html)
        self.assertIn(
            """} else if(UserAuth.isGeneralTeacher()){
      enterNutritionRecommendations();
      return;""",
            self.health_html,
        )

    def test_class_teacher_health_island_redirects_to_nutrition_stats(self):
        self.assertIn(
            """} else if(UserAuth.isClassTeacher()){
      enterNutritionRecommendations();
      return;""",
            self.health_html,
        )

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
            "gradeStatsWeekOdd",
            "gradeStatsWeekEven",
            "classMealTitle",
            "classMenuBoard",
            "classIncompleteOnly",
            "ctStudentCount",
            "ctCompleteCount",
            "ctIncompleteCount",
            "ctACount",
            "ctBCount",
            "classMealStats",
            "parentChildTitle",
            "parentRecommendationDate",
            "parentRecommendationSummary",
            "parentHealthChips",
            "parentAiInsights",
            "parentRiskNote",
            "parentPlanWeeks",
            "parentPlanStatus",
            "parentDeadlineStatus",
            "parentSubmitBtn",
            "parentSubmitMessage",
            "menuSelectionDeadline",
        ):
            self.assertIn(f'id="{element_id}"', self.recommendations_html)
        self.assertIn("仅显示当前班主任账号绑定班级", self.recommendations_html)
        self.assertIn("只看未完成", self.recommendations_html)
        self.assertIn("student.isComplete", self.recommendations_html)
        self.assertIn("系统只读取当前账号绑定孩子的数据", self.recommendations_html)
        self.assertIn("loadParentRecommendations()", self.recommendations_html)
        self.assertIn("buildParentMealPlan()", self.recommendations_html)
        self.assertIn("submitRecommendedMealPlan()", self.recommendations_html)
        self.assertIn("isParentSelectionClosed()", self.recommendations_html)
        self.assertIn("parentPlanSummary(day.mealA)", self.recommendations_html)
        self.assertIn("parentSubmittedChoices.find", self.recommendations_html)
        self.assertIn("menu.image_path", self.recommendations_html)
        self.assertIn("renderClassMenuBoard", self.recommendations_html)
        self.assertIn("ctMealPlans", self.recommendations_html)
        self.assertIn("gradeStatsWeekEven", self.recommendations_html)
        self.assertIn("rootApiFetch('/api/meal-choices'", self.recommendations_html)
        self.assertIn("/api/meal-choices/student/", self.recommendations_html)
        self.assertNotIn('id="parentRecommendationHistory"', self.recommendations_html)
        self.assertNotIn('id="parentMealHistory"', self.recommendations_html)
        self.assertNotIn('id="runBtn"', self.recommendations_html)
        self.assertNotIn('id="recommendationActions"', self.recommendations_html)

    def test_nutrition_requests_include_teacher_scope(self):
        self.assertIn("'X-Demo-Sub': NUTRITION_SUB_ROLE", self.common_js)
        self.assertIn("'X-Demo-Grade': NUTRITION_GRADE", self.common_js)
        self.assertIn("'X-Demo-Class': NUTRITION_CLASS", self.common_js)

    def test_teacher_nutrition_back_button_returns_home(self):
        self.assertIn(
            "['general', 'class'].includes(NUTRITION_SUB_ROLE)",
            self.common_js,
        )
        self.assertIn("'../island-homepage.html'", self.common_js)
        self.assertIn("returnsHome ? '‹ 返回主页' : '‹ 返回健康岛'", self.common_js)

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

    def test_meal_views_use_published_service_days_instead_of_forcing_fourteen(self):
        self.assertIn("let _pmRequiredDays = {odd:[1,2,3,4,5], even:[1,2,3,4,5]}", self.health_html)
        self.assertIn("_pmRequiredDays[parity].map", self.health_html)
        self.assertIn("data.requiredDays?.odd", self.health_html)
        self.assertIn("let ctRequiredDays = {odd:[1,2,3,4,5], even:[1,2,3,4,5]}", self.recommendations_html)
        self.assertIn("data.requiredDays?.odd", self.recommendations_html)
        self.assertIn("Number(day.weekday) <= 7", self.recommendations_html)
        self.assertNotIn("已完成 14 天", self.recommendations_html)


class DemoChildSeedTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_manage_db_path = manage_accounts.DB
        self.main_db_path = str(Path(self.temp_dir.name) / "student_data.db")
        manage_accounts.DB = self.main_db_path

    def tearDown(self):
        manage_accounts.DB = self.old_manage_db_path
        self.temp_dir.cleanup()

    def test_demo_child_seed_adds_parent_visible_mock_data_idempotently(self):
        db = manage_accounts.conn()
        first = manage_accounts.seed_demo_child_data(db)
        second = manage_accounts.seed_demo_child_data(db)

        self.assertEqual(first, second)
        self.assertEqual(first["child_code"], "BS_99999")
        student = db.execute(
            """SELECT name, gender, birth_date, grade_name, class_name, school_name
               FROM students WHERE id_card='BS_99999'"""
        ).fetchone()
        self.assertIsNotNone(student)
        self.assertEqual(
            tuple(student),
            ("示例学生", None, None, "三年级", "1班", "本部校区"),
        )
        meal_rows = db.execute(
            """SELECT week_number, parity, weekday, choice
               FROM meal_choices
               WHERE id_card='BS_99999'
               ORDER BY week_number, weekday"""
        ).fetchall()
        self.assertEqual(len(meal_rows), 10)
        self.assertEqual({row["week_number"] for row in meal_rows}, {17, 18})
        self.assertEqual({row["choice"] for row in meal_rows}, {"A", "B"})

        child = db.execute(
            """SELECT id, display_name, data_status
               FROM nutrition_children WHERE child_code='BS_99999'"""
        ).fetchone()
        self.assertIsNotNone(child)
        self.assertEqual(child[1], "示例学生")
        self.assertEqual(child[2], "complete")
        recommendations = db.execute(
            """SELECT plan_date, recommended_plan
               FROM nutrition_recommendations
               WHERE child_id=?
               ORDER BY plan_date""",
            (child[0],),
        ).fetchall()
        db.close()
        self.assertEqual(len(recommendations), 10)
        self.assertEqual(
            [row[0] for row in recommendations],
            [
                "2026-07-27",
                "2026-07-28",
                "2026-07-29",
                "2026-07-30",
                "2026-07-31",
                "2026-08-03",
                "2026-08-04",
                "2026-08-05",
                "2026-08-06",
                "2026-08-07",
            ],
        )
        self.assertEqual({row[1] for row in recommendations}, {"A", "B"})
        meal_plan_db = manage_accounts.conn()
        self.assertEqual(
            meal_plan_db.execute(
                """SELECT COUNT(*) FROM nutrition_meal_plans
                   WHERE plan_date BETWEEN '2026-07-27' AND '2026-08-07'"""
            ).fetchone()[0],
            20,
        )
        meal_plan_db.close()
        menu_db = manage_accounts.conn()
        menus = menu_db.execute(
            """SELECT week_number, parity, date_start, date_end,
                      selection_deadline
               FROM weekly_menus ORDER BY week_number"""
        ).fetchall()
        menu_db.close()
        self.assertEqual(
            [tuple(row) for row in menus],
            [
                (17, "odd", "2026-07-27", "2026-07-31", menus[0][4]),
                (18, "even", "2026-08-03", "2026-08-07", menus[1][4]),
            ],
        )
        self.assertTrue(all(row[4] for row in menus))


class LoginRoleEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = server_app.DB_PATH
        self.old_auth_db_path = server_app.AUTH_DB_PATH
        self.old_manage_db_path = manage_accounts.DB
        self.old_dual_role_userids = server_app.BENBU_DUAL_ROLE_TEACHER_USERIDS
        db_path = str(Path(self.temp_dir.name) / "accounts.db")
        auth_db_path = str(Path(self.temp_dir.name) / "auth-accounts.db")
        server_app.DB_PATH = db_path
        server_app.AUTH_DB_PATH = auth_db_path
        server_app.BENBU_DUAL_ROLE_TEACHER_USERIDS = frozenset({'teacher-user-dual-001'})
        manage_accounts.DB = db_path
        server_app.app.config["TESTING"] = True

        db = manage_accounts.conn()
        for account in manage_accounts.DEMO:
            manage_accounts.upsert(db, **account)
        db.execute(
            """CREATE TABLE IF NOT EXISTS user_bindings(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   dingtalk_unionid TEXT UNIQUE,
                   role TEXT NOT NULL DEFAULT 'parent',
                   sub_role TEXT,
                   bound_id_card TEXT,
                   bound_grade TEXT,
                   bound_class TEXT,
                   bound_name TEXT,
                   created_at TEXT DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        db.commit()
        db.close()
        auth_db = sqlite3.connect(auth_db_path)
        auth_db.execute('''CREATE TABLE auth_accounts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE, password_hash TEXT, role TEXT, sub_role TEXT,
            campus_id TEXT, display_name TEXT, bound_student_userid TEXT,
            bound_id_card TEXT, bound_grade TEXT, bound_class TEXT,
            is_active INTEGER, auth_version INTEGER, failed_attempts INTEGER,
            locked_until INTEGER, last_login_at TEXT
        )''')
        for account in manage_accounts.DEMO:
            auth_db.execute(
                '''INSERT INTO auth_accounts(
                       username, password_hash, role, sub_role, campus_id,
                       display_name, bound_student_userid, bound_id_card,
                       bound_grade, bound_class, is_active, auth_version,
                       failed_attempts
                   ) VALUES(?, ?, ?, ?, 'benbu', ?, NULL, ?, ?, ?, 1, 1, 0)''',
                (
                    account['username'],
                    generate_password_hash('123456', method='pbkdf2:sha256:1000'),
                    account['role'], account.get('sub_role'),
                    account.get('display_name') or account['username'],
                    account.get('bound_id_card'), account.get('bound_grade'),
                    account.get('bound_class'),
                ),
            )
        auth_db.commit()
        auth_db.close()
        self.client = server_app.app.test_client()

    def tearDown(self):
        server_app.DB_PATH = self.old_db_path
        server_app.AUTH_DB_PATH = self.old_auth_db_path
        server_app.BENBU_DUAL_ROLE_TEACHER_USERIDS = self.old_dual_role_userids
        manage_accounts.DB = self.old_manage_db_path
        self.temp_dir.cleanup()

    def login(self, username, entry=None):
        payload = {"username": username, "password": "123456", "campus": "benbu"}
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

    def test_dingtalk_class_teacher_uses_binding_grade_and_class(self):
        union_id = "class-teacher-union"
        db = sqlite3.connect(server_app.DB_PATH)
        db.execute(
            """INSERT INTO user_bindings(
                   dingtalk_unionid, role, sub_role, bound_grade, bound_class, bound_name
               ) VALUES(?, 'teacher', 'class', '三年级', '5班', '测试班主任')""",
            (union_id,),
        )
        db.commit()
        db.close()
        token = server_app._sign_session({"unionId": union_id, "ts": int(time.time())})
        old_disable_demo = server_app.DISABLE_DEMO
        server_app.DISABLE_DEMO = True
        try:
            response = self.client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        finally:
            server_app.DISABLE_DEMO = old_disable_demo

        self.assertEqual(response.status_code, 200)
        user = response.get_json()
        self.assertEqual(user["role"], "teacher")
        self.assertEqual(user["subRole"], "class")
        self.assertEqual(user["boundGrade"], "三年级")
        self.assertEqual(user["boundClass"], "5班")

    def test_benbu_whitelisted_class_teacher_can_switch_to_unbound_parent(self):
        union_id = "wang-ruocheng-union"
        db = sqlite3.connect(server_app.DB_PATH)
        db.execute(
            """INSERT INTO user_bindings(
                   dingtalk_unionid, role, sub_role, bound_grade, bound_class, bound_name
               ) VALUES(?, 'teacher', 'class', '四年级', '2班', '示例教师')""",
            (union_id,),
        )
        db.commit()
        db.close()
        token = server_app._sign_session({
            "unionId": union_id,
            "dingtalkUserId": "teacher-user-dual-001",
            "campus": "benbu",
            "ts": int(time.time()),
        })
        headers = {"Authorization": f"Bearer {token}"}
        old_disable_demo = server_app.DISABLE_DEMO
        server_app.DISABLE_DEMO = True
        try:
            teacher = self.client.get("/api/auth/me", headers=headers).get_json()
            switched = self.client.post(
                "/api/switch-role", json={"role": "parent"}, headers=headers
            )
            parent = self.client.get("/api/auth/me", headers=headers).get_json()
        finally:
            server_app.DISABLE_DEMO = old_disable_demo

        self.assertEqual(teacher["availableRoles"], ["teacher", "parent"])
        self.assertEqual(switched.status_code, 200)
        self.assertEqual(parent["role"], "parent")
        self.assertIsNone(parent["boundStudentUserId"])
        self.assertIsNone(parent["boundIdCard"])

    def test_dual_role_userid_whitelist_is_scoped_to_benbu(self):
        union_id = "other-campus-teacher"
        old_baolin_db = server_app.BAOLIN_DB_PATH
        server_app.BAOLIN_DB_PATH = str(Path(self.temp_dir.name) / 'baolin-scope.db')
        db = sqlite3.connect(server_app.BAOLIN_DB_PATH)
        db.executescript('''CREATE TABLE user_bindings(
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               dingtalk_unionid TEXT UNIQUE, role TEXT, sub_role TEXT,
               bound_id_card TEXT, bound_grade TEXT, bound_class TEXT,
               bound_name TEXT, dingtalk_userid TEXT, bound_student_userid TEXT
           );
           CREATE TABLE students_baolin(
               dingtalk_userid TEXT PRIMARY KEY, id_card TEXT, name TEXT,
               grade_name TEXT, class_name TEXT
           );''')
        db.execute(
            """INSERT INTO user_bindings(
                   dingtalk_unionid, role, sub_role, bound_grade, bound_class, bound_name
                ) VALUES(?, 'teacher', 'class', '四年级', '2班', '示例教师')""",
            (union_id,),
        )
        db.commit()
        db.close()
        token = server_app._sign_session({
            "unionId": union_id,
            "dingtalkUserId": "teacher-user-dual-001",
            "campus": "baolin",
            "ts": int(time.time()),
        })
        old_disable_demo = server_app.DISABLE_DEMO
        server_app.DISABLE_DEMO = True
        try:
            response = self.client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
            )
        finally:
            server_app.DISABLE_DEMO = old_disable_demo
            server_app.BAOLIN_DB_PATH = old_baolin_db

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["availableRoles"], ["teacher"])

    def test_parent_identity_reconciles_stale_class_with_current_roster(self):
        union_id = "parent-union"
        db = sqlite3.connect(server_app.DB_PATH)
        db.executescript(
            """CREATE TABLE IF NOT EXISTS parent_kids(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   union_id TEXT NOT NULL,
                   kid_id_card TEXT NOT NULL,
                   kid_name TEXT NOT NULL,
                   kid_grade TEXT,
                   kid_class TEXT,
                   campus TEXT,
                   is_active INTEGER DEFAULT 0,
                   bound_at TEXT DEFAULT CURRENT_TIMESTAMP
               );
               CREATE TABLE IF NOT EXISTS students_benbu(
                   dingtalk_userid TEXT PRIMARY KEY,
                   id_card TEXT UNIQUE,
                   name TEXT NOT NULL,
                   grade_name TEXT,
                   class_name TEXT
               );"""
        )
        for column in (
            "dingtalk_userid TEXT",
            "bound_student_userid TEXT",
        ):
            try:
                db.execute(f"ALTER TABLE user_bindings ADD COLUMN {column}")
            except sqlite3.OperationalError:
                pass
        db.execute(
            """INSERT INTO user_bindings(
                   dingtalk_unionid, role, bound_student_userid,
                   bound_id_card, bound_name, bound_grade, bound_class
               ) VALUES(?, 'parent', ?, 'KID-1', '示例学生乙', '二年级', '1班')""",
            (union_id, "student-user-002"),
        )
        db.execute(
            """INSERT INTO parent_kids(
                   union_id, kid_id_card, kid_name, kid_grade, kid_class, campus, is_active
               ) VALUES(?, 'OLD-001', '测试学生', '五年级', '1班', 'benbu', 1)""",
            (union_id,),
        )
        db.execute(
            "INSERT INTO students_benbu VALUES('DT-STUDENT-001', 'NEW-001', '测试学生', '三年级', '5班')"
        )
        db.commit()
        db.close()
        token = server_app._sign_session({"unionId": union_id, "ts": int(time.time())})
        old_disable_demo = server_app.DISABLE_DEMO
        server_app.DISABLE_DEMO = True
        try:
            response = self.client.get(
                "/api/auth/me?campus=benbu",
                headers={"Authorization": f"Bearer {token}"},
            )
        finally:
            server_app.DISABLE_DEMO = old_disable_demo

        self.assertEqual(response.status_code, 200)
        user = response.get_json()
        self.assertEqual(user["boundStudentUserId"], "DT-STUDENT-001")
        self.assertEqual(user["boundIdCard"], "NEW-001")
        self.assertEqual(user["boundGrade"], "三年级")
        self.assertEqual(user["boundClass"], "5班")
        self.assertEqual(user["boundStudent"]["displayName"], "测试学生")
        self.assertEqual(len(user["kids"]), 1)
        self.assertEqual(user["kids"][0]["studentUserId"], "DT-STUDENT-001")
        self.assertEqual(user["kids"][0]["idCard"], "NEW-001")
        self.assertEqual(user["kids"][0]["grade"], "三年级")
        self.assertEqual(user["kids"][0]["class"], "5班")

    def test_parent_switches_between_two_children_by_student_userid(self):
        union_id = "two-kids-parent"
        db = sqlite3.connect(server_app.DB_PATH)
        db.executescript(
            """CREATE TABLE IF NOT EXISTS parent_kids(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   union_id TEXT NOT NULL,
                   kid_dingtalk_userid TEXT,
                   kid_id_card TEXT NOT NULL,
                   kid_name TEXT NOT NULL,
                   kid_grade TEXT,
                   kid_class TEXT,
                   campus TEXT,
                   is_active INTEGER DEFAULT 0,
                   bound_at TEXT DEFAULT CURRENT_TIMESTAMP
               );
               CREATE TABLE IF NOT EXISTS students_benbu(
                   dingtalk_userid TEXT PRIMARY KEY,
                   id_card TEXT UNIQUE,
                   name TEXT NOT NULL,
                   grade_name TEXT,
                   class_name TEXT
               );"""
        )
        db.execute(
            "INSERT INTO user_bindings(dingtalk_unionid, role) VALUES(?, 'parent')",
            (union_id,),
        )
        db.executemany(
            "INSERT INTO students_benbu VALUES(?,?,?,?,?)",
            [
                ("student-user-002", "KID-1", "示例学生乙", "二年级", "1班"),
                ("student-user-003", "KID-2", "示例学生丙", "四年级", "2班"),
            ],
        )
        db.executemany(
            """INSERT INTO parent_kids(
                   union_id, kid_dingtalk_userid, kid_id_card, kid_name,
                   kid_grade, kid_class, campus, is_active
               ) VALUES(?,?,?,?,?,?,?,?)""",
            [
                (union_id, "student-user-002", "KID-1", "示例学生乙", "二年级", "1班", "benbu", 1),
                (union_id, "student-user-003", "KID-2", "示例学生丙", "四年级", "2班", "benbu", 0),
            ],
        )
        db.commit()
        db.close()
        token = server_app._sign_session({"unionId": union_id, "campus": "benbu", "ts": int(time.time())})
        headers = {"Authorization": f"Bearer {token}"}
        old_disable_demo = server_app.DISABLE_DEMO
        server_app.DISABLE_DEMO = True
        try:
            before = self.client.get("/api/auth/me", headers=headers).get_json()
            switched = self.client.post(
                "/api/auth/switch-kid",
                json={"studentUserId": "student-user-003"},
                headers=headers,
            )
            after = self.client.get("/api/auth/me", headers=headers).get_json()
        finally:
            server_app.DISABLE_DEMO = old_disable_demo

        self.assertEqual(before["boundStudent"]["displayName"], "示例学生乙")
        self.assertEqual(len(before["kids"]), 2)
        self.assertEqual(switched.status_code, 200)
        self.assertEqual(switched.get_json()["kid"]["studentUserId"], "student-user-003")
        self.assertEqual(after["boundStudentUserId"], "student-user-003")
        self.assertEqual(after["boundStudent"]["displayName"], "示例学生丙")

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
