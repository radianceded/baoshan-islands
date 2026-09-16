# -*- coding: utf-8 -*-
"""首登强改密：mustChangePassword 标志 + 「暂不修改」跳过（skip-password-change）"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from server import app as server_app


class _AuthDbBase(unittest.TestCase):
    with_flag_column = True

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.auth_db_path = str(root / 'auth_accounts.db')
        self.old_auth_db = server_app.AUTH_DB_PATH
        self.old_student_db = server_app.DB_PATH
        server_app.AUTH_DB_PATH = self.auth_db_path
        server_app.DB_PATH = str(root / 'student_data.db')
        flag_col = ',\n            must_change_password INTEGER NOT NULL DEFAULT 0' \
            if self.with_flag_column else ''
        db = sqlite3.connect(self.auth_db_path)
        db.execute(f'''CREATE TABLE auth_accounts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            sub_role TEXT,
            campus_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            bound_student_userid TEXT,
            bound_id_card TEXT,
            bound_grade TEXT,
            bound_class TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            auth_version INTEGER NOT NULL DEFAULT 1,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until INTEGER,
            last_login_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP{flag_col}
        )''')
        db.execute(
            '''INSERT INTO auth_accounts(username, password_hash, role, sub_role, campus_id, display_name)
               VALUES('zhangting', ?, 'teacher', 'general', 'benbu', '张婷')''',
            (generate_password_hash('Init-123', method='pbkdf2:sha256:1000'),))
        if self.with_flag_column:
            db.execute('UPDATE auth_accounts SET must_change_password=1')
        db.commit()
        db.close()
        sqlite3.connect(server_app.DB_PATH).close()
        server_app.app.config['TESTING'] = True
        self.client = server_app.app.test_client()

    def tearDown(self):
        server_app.AUTH_DB_PATH = self.old_auth_db
        server_app.DB_PATH = self.old_student_db
        self.temp_dir.cleanup()

    def login(self, password='Init-123'):
        return self.client.post('/api/login', json={
            'username': 'zhangting', 'password': password,
            'entry': 'general_teacher', 'campus': 'benbu'})

    def flag_now(self):
        db = sqlite3.connect(self.auth_db_path)
        val = db.execute('SELECT must_change_password FROM auth_accounts').fetchone()[0]
        db.close()
        return val


class SkipPasswordChangeTests(_AuthDbBase):
    def test_login_reports_must_change(self):
        d = self.login().get_json()
        self.assertTrue(d['success'])
        self.assertTrue(d['user']['mustChangePassword'])

    def test_skip_clears_flag_and_keeps_password(self):
        token = self.login().get_json()['sessionToken']
        r = self.client.post('/api/auth/skip-password-change',
                             headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()['success'])
        self.assertEqual(self.flag_now(), 0)
        # 原密码继续可用，且不再提示改密
        d = self.login().get_json()
        self.assertTrue(d['success'])
        self.assertFalse(d['user']['mustChangePassword'])

    def test_skip_requires_valid_token(self):
        self.assertEqual(
            self.client.post('/api/auth/skip-password-change').status_code, 401)
        self.assertEqual(
            self.client.post('/api/auth/skip-password-change',
                             headers={'Authorization': 'Bearer bad.token'}).status_code, 401)

    def test_change_password_still_clears_flag(self):
        token = self.login().get_json()['sessionToken']
        r = self.client.post('/api/auth/change-password',
                             json={'oldPassword': 'Init-123', 'newPassword': 'sunny2026a'},
                             headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(r.status_code, 200)
        d = self.login('sunny2026a').get_json()
        self.assertTrue(d['success'])
        self.assertFalse(d['user']['mustChangePassword'])


class SkipWithoutFlagColumnTests(_AuthDbBase):
    """旧库没有 must_change_password 列时，skip 静默成功不报错"""
    with_flag_column = False

    def test_skip_is_safe_without_column(self):
        token = self.login().get_json()['sessionToken']
        r = self.client.post('/api/auth/skip-password-change',
                             headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(r.status_code, 200)


class FirstLoginSkipUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).resolve().parents[1] / 'login.html').read_text(encoding='utf-8')

    def test_skip_link_present_in_first_login_panel(self):
        self.assertIn('id="skipFirstLogin"', self.html)
        self.assertIn('/api/auth/skip-password-change', self.html)
        self.assertIn('skip-row', self.html)

    def test_first_login_panel_no_longer_offers_username_change(self):
        """两起家长误改账号名事故后，首登面板收回改名功能（改名走总务）"""
        self.assertNotIn('id="newUsername"', self.html)
        self.assertNotIn('change-username', self.html)


class LogoutUiTests(unittest.TestCase):
    """退出按钮不再依赖原生 confirm（钉钉 webview 会吞掉弹窗导致点击无反应）"""
    ROOT = Path(__file__).resolve().parents[1]

    def test_user_auth_has_logout_with_dingtalk_bypass(self):
        js = (self.ROOT / 'assets' / 'user-auth.js').read_text(encoding='utf-8')
        self.assertIn('logout()', js)
        self.assertIn('/DingTalk/i.test(navigator.userAgent)', js)

    def test_island_pages_use_unified_logout_entry(self):
        pages = ['island-homepage.html', 'island-health.html', 'island-archive.html',
                 'island-award.html', 'island-activity.html', 'island-reading.html']
        for page in pages:
            html = (self.ROOT / page).read_text(encoding='utf-8')
            self.assertIn('UserAuth.logout', html, page)
            # 行内 confirm 已移除（homepage 的 doLogout 内部委托给 logout）
            self.assertNotIn("if(confirm('退出登录?')", html, page)


class ParentMealWeekUiTests(unittest.TestCase):
    """家长选餐周对不再硬编码第 1/2 周，按菜单截止时间动态选择当前一期"""

    def test_week_pair_is_dynamic(self):
        html = (Path(__file__).resolve().parents[1] / 'island-health.html').read_text(encoding='utf-8')
        self.assertNotIn('const wkOdd = 1;', html)
        self.assertNotIn('const wkEven = 2;', html)
        self.assertIn('pickActiveMealWeek', html)
        self.assertIn("pickActiveMealWeek(data.menus, 'odd', 1)", html)
        self.assertIn("pickActiveMealWeek(data.menus, 'even', 2)", html)


class ClubActivityParentViewTests(unittest.TestCase):
    """家长端社团详情弹窗不显示「本学期重要活动」"""

    def test_important_events_hidden_for_parent(self):
        html = (Path(__file__).resolve().parents[1] / 'island-activity.html').read_text(encoding='utf-8')
        self.assertIn('本学期重要活动', html)                       # 老师端仍保留
        idx = html.find('本学期重要活动')
        guard = html.rfind("UserAuth.isParent && UserAuth.isParent() ? ''", 0, idx)
        self.assertNotEqual(guard, -1, '重要活动区块前缺少家长隐藏条件')
        self.assertLess(idx - guard, 400, '家长隐藏条件应紧邻重要活动区块')


if __name__ == '__main__':
    unittest.main()


class RecoverByInitialPasswordTests(_AuthDbBase):
    """忘记密码：凭发放单上的初始密码自助重置（initial_password_hash 永不被自改覆盖）"""

    def recover(self, initial='Init-123', new='newpass9x', username='zhangting'):
        return self.client.post('/api/auth/recover-by-initial', json={
            'username': username, 'initialPassword': initial,
            'newPassword': new, 'campus': 'benbu'})

    def test_full_recover_flow(self):
        # 旧库无 initial 列 → 端点自动迁移并回填当前密码为初始密码
        r = self.recover()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()['success'])
        d = self.login('newpass9x').get_json()
        self.assertTrue(d['success'])
        self.assertFalse(d['user']['mustChangePassword'])

    def test_initial_survives_self_service_changes(self):
        self.recover(new='firstnew9')
        # 家长又用改密接口改了一次
        token = self.login('firstnew9').get_json()['sessionToken']
        self.client.post('/api/auth/change-password',
                         json={'oldPassword': 'firstnew9', 'newPassword': 'secondnew9'},
                         headers={'Authorization': f'Bearer {token}'})
        # 再忘 → 仍可用最初的发放密码找回
        r = self.recover(new='thirdnew9')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.login('thirdnew9').get_json()['success'])

    def test_wrong_initial_password_rejected(self):
        self.assertEqual(self.recover(initial='wrong-000').status_code, 401)

    def test_weak_new_password_rejected(self):
        self.assertEqual(self.recover(new='123').status_code, 400)

    def test_unknown_username_rejected(self):
        self.assertEqual(self.recover(username='nobody').status_code, 401)


class RecoverUiTests(unittest.TestCase):
    def test_login_page_has_recover_view(self):
        html = (Path(__file__).resolve().parents[1] / 'login.html').read_text(encoding='utf-8')
        self.assertIn('id="recoverView"', html)
        self.assertIn('/api/auth/recover-by-initial', html)
        self.assertIn('忘记密码', html)
