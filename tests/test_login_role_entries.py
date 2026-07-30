import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from server import app as server_app


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


class LoginRoleEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = server_app.DB_PATH
        server_app.DB_PATH = os.path.join(self.temp_dir.name, "accounts.db")
        server_app.app.config["TESTING"] = True

        db = sqlite3.connect(server_app.DB_PATH)
        db.execute(
            """
            CREATE TABLE accounts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                sub_role TEXT,
                bound_id_card TEXT,
                bound_grade TEXT,
                bound_class TEXT,
                kid_name TEXT,
                demo_idx INTEGER,
                display_name TEXT,
                dingtalk_unionid TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.executemany(
            """
            INSERT INTO accounts(
                username, password_hash, role, sub_role, bound_id_card,
                bound_grade, bound_class, kid_name, display_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "general",
                    server_app._hash_pwd("secret"),
                    "teacher",
                    "general",
                    None,
                    None,
                    None,
                    None,
                    "总务老师",
                ),
                (
                    "class",
                    server_app._hash_pwd("secret"),
                    "teacher",
                    "class",
                    None,
                    "三年级",
                    "1班",
                    None,
                    "班主任老师",
                ),
                (
                    "parent",
                    server_app._hash_pwd("secret"),
                    "parent",
                    None,
                    "S001",
                    "三年级",
                    "1班",
                    "学生甲",
                    "学生家长",
                ),
            ],
        )
        db.commit()
        db.close()
        self.client = server_app.app.test_client()

    def tearDown(self):
        server_app.DB_PATH = self.old_db_path
        self.temp_dir.cleanup()

    def login(self, username, entry=None):
        payload = {"username": username, "password": "secret"}
        if entry is not None:
            payload["entry"] = entry
        return self.client.post("/api/login", json=payload)

    def test_each_entry_accepts_its_matching_account(self):
        cases = [
            ("general", "general_teacher", "teacher", "general"),
            ("class", "class_teacher", "teacher", "class"),
            ("parent", "parent", "parent", None),
        ]
        for username, entry, role, sub_role in cases:
            with self.subTest(entry=entry):
                response = self.login(username, entry)
                self.assertEqual(response.status_code, 200)
                user = response.get_json()["user"]
                self.assertEqual(user["role"], role)
                self.assertEqual(user["sub_role"], sub_role)

    def test_entry_rejects_an_account_from_another_identity(self):
        response = self.login("general", "class_teacher")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.get_json()["error"],
            "该账号不属于所选身份入口",
        )

    def test_invalid_entry_is_rejected(self):
        response = self.login("general", "administrator")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "登录身份入口无效")

    def test_legacy_login_without_entry_remains_compatible(self):
        response = self.login("general")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["role"], "teacher")


if __name__ == "__main__":
    unittest.main()
