# -*- coding: utf-8 -*-
"""账密 ↔ 钉钉 id 绑定免登：登录后绑定钉钉 userId，之后任何设备在钉钉内打开自动登录"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from server import app as server_app


class _BindBase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.auth_db_path = str(root / 'auth_accounts.db')
        self.old = (server_app.AUTH_DB_PATH, server_app.DB_PATH)
        server_app.AUTH_DB_PATH = self.auth_db_path
        server_app.DB_PATH = str(root / 'student_data.db')
        adb = sqlite3.connect(self.auth_db_path)
        adb.execute('''CREATE TABLE auth_accounts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            role TEXT NOT NULL, sub_role TEXT, campus_id TEXT NOT NULL,
            display_name TEXT NOT NULL, bound_student_userid TEXT,
            bound_id_card TEXT, bound_grade TEXT, bound_class TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            auth_version INTEGER NOT NULL DEFAULT 1,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until INTEGER, last_login_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            must_change_password INTEGER NOT NULL DEFAULT 0)''')
        pwd = generate_password_hash('Pass-123', method='pbkdf2:sha256:1000')
        adb.executemany(
            '''INSERT INTO auth_accounts(username, password_hash, role, sub_role, campus_id,
               display_name, bound_student_userid, bound_grade, bound_class, last_login_at)
               VALUES(?, ?, 'parent', NULL, 'benbu', ?, ?, '三年级', '1班', ?)''',
            [
                ('p_one', pwd, '孩子甲', 'STU-A', '2026-09-01 08:00:00'),
                ('p_two', pwd, '孩子乙', 'STU-B', '2026-09-05 08:00:00'),
            ])
        adb.commit()
        adb.close()
        sdb = sqlite3.connect(server_app.DB_PATH)
        sdb.execute('''CREATE TABLE students_benbu(
            dingtalk_userid TEXT PRIMARY KEY, id_card TEXT, name TEXT,
            grade_name TEXT, class_name TEXT)''')
        sdb.executemany('INSERT INTO students_benbu VALUES(?,?,?,?,?)', [
            ('STU-A', 'STU-A', '孩子甲', '三年级', '1班'),
            ('STU-B', 'STU-B', '孩子乙', '三年级', '1班'),
        ])
        sdb.commit()
        sdb.close()
        server_app.app.config['TESTING'] = True
        self.client = server_app.app.test_client()
        # mock 钉钉兑码：authCode 'code-ok' → userId 'DTUSER1'
        self._orig_exchange = server_app._exchange_auth_code_via_accesstoken
        server_app._exchange_auth_code_via_accesstoken = (
            lambda k, s, code: {'userId': 'DTUSER1', 'unionId': 'U1', 'nick': '测试家长',
                                'avatarUrl': ''} if code == 'code-ok' else None)
        # 让校区钉钉配置存在（bind-config enabled）
        self._orig_get_dt = server_app._get_campus_dt
        server_app._get_campus_dt = lambda c: {
            'appKey': 'k', 'appSecret': 's', 'corpId': 'ding-test', 'school_name': '测试'}

    def tearDown(self):
        server_app.AUTH_DB_PATH, server_app.DB_PATH = self.old
        server_app._exchange_auth_code_via_accesstoken = self._orig_exchange
        server_app._get_campus_dt = self._orig_get_dt
        self.temp_dir.cleanup()

    def login_token(self, username='p_one'):
        r = self.client.post('/api/login', json={
            'username': username, 'password': 'Pass-123',
            'entry': 'parent', 'campus': 'benbu'})
        return r.get_json()['sessionToken']

    def bind(self, token, code='code-ok'):
        return self.client.post('/api/auth/dingtalk-bind', json={'authCode': code},
                                headers={'Authorization': 'Bearer ' + token})

    def dt_login(self, code='code-ok'):
        return self.client.post('/api/auth/dingtalk-token-login',
                                json={'authCode': code, 'campus': 'benbu'})


class BindConfigTests(_BindBase):
    def test_config_enabled_with_credentials(self):
        r = self.client.get('/api/auth/dingtalk-bind-config?campus=benbu')
        d = r.get_json()
        self.assertTrue(d['enabled'])
        self.assertEqual(d['corpId'], 'ding-test')

    def test_config_disabled_without_credentials(self):
        server_app._get_campus_dt = lambda c: {'appKey': '', 'appSecret': '', 'corpId': '',
                                               'school_name': ''}
        d = self.client.get('/api/auth/dingtalk-bind-config?campus=benbu').get_json()
        self.assertFalse(d['enabled'])


class BindTests(_BindBase):
    def test_bind_writes_dingtalk_userid(self):
        r = self.bind(self.login_token())
        self.assertEqual(r.status_code, 200)
        adb = sqlite3.connect(self.auth_db_path)
        val = adb.execute("SELECT dingtalk_userid FROM auth_accounts WHERE username='p_one'"
                          ).fetchone()[0]
        self.assertEqual(val, 'DTUSER1')

    def test_bind_requires_login(self):
        self.assertEqual(
            self.client.post('/api/auth/dingtalk-bind',
                             json={'authCode': 'code-ok'}).status_code, 401)

    def test_bind_exchange_failure_is_502(self):
        r = self.bind(self.login_token(), code='bad-code')
        self.assertEqual(r.status_code, 502)


class DingTalkTokenLoginTests(_BindBase):
    def test_unbound_user_gets_404(self):
        self.assertEqual(self.dt_login().status_code, 404)

    def test_bound_user_auto_logs_in(self):
        self.bind(self.login_token())
        r = self.dt_login()
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d['success'])
        self.assertTrue(d['sessionToken'])
        self.assertEqual(d['user']['displayName'], '孩子甲')
        # 发的 token 能通过身份接口
        me = self.client.get('/api/auth/me',
                             headers={'Authorization': 'Bearer ' + d['sessionToken']}).get_json()
        self.assertEqual(me.get('role'), 'parent')

    def test_multiple_bound_accounts_pick_latest_login(self):
        self.bind(self.login_token('p_one'))
        self.bind(self.login_token('p_two'))    # 同一个钉钉家长绑了两个孩子账号
        adb = sqlite3.connect(self.auth_db_path)
        adb.execute("UPDATE auth_accounts SET last_login_at='2026-09-01 08:00:00' WHERE username='p_one'")
        adb.execute("UPDATE auth_accounts SET last_login_at='2026-09-06 09:00:00' WHERE username='p_two'")
        adb.commit(); adb.close()
        d = self.dt_login().get_json()
        # p_two 的 last_login_at 最新（刚绑定时登录过），应选中它
        self.assertEqual(d['user']['displayName'], '孩子乙')

    def test_paused_account_not_auto_logged(self):
        self.bind(self.login_token())
        adb = sqlite3.connect(self.auth_db_path)
        adb.execute("UPDATE auth_accounts SET is_active=0 WHERE username='p_one'")
        adb.commit()
        adb.close()
        self.assertEqual(self.dt_login().status_code, 404)

    def test_bad_authcode_is_502(self):
        self.assertEqual(self.dt_login('bad-code').status_code, 502)


class LoginPageDingTalkUiTests(unittest.TestCase):
    def test_login_page_wires_dingtalk_auto_login(self):
        html = (Path(__file__).resolve().parents[1] / 'login.html').read_text(encoding='utf-8')
        self.assertIn('/api/auth/dingtalk-bind-config', html)
        self.assertIn('/api/auth/dingtalk-token-login', html)
        self.assertIn('/api/auth/dingtalk-bind', html)
        self.assertIn('dingtalk.open.js', html)

    def test_explicit_logout_skips_one_dingtalk_auto_login(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / 'login.html').read_text(encoding='utf-8')
        auth_js = (root / 'assets' / 'user-auth.js').read_text(encoding='utf-8')
        homepage = (root / 'island-homepage.html').read_text(encoding='utf-8')
        self.assertIn("get('manual') === '1'", html)
        self.assertIn('if(!restored && !MANUAL_LOGIN)', html)
        self.assertIn("+ '&manual=1'", auth_js)
        self.assertIn("+ '&manual=1'", homepage)


class SiblingAccountSwitchTests(_BindBase):
    """多孩家庭：同一钉钉绑定的多个账号之间一键切换（账密体系版切换孩子）"""

    def _bind_both(self):
        self.bind(self.login_token('p_one'))
        self.bind(self.login_token('p_two'))

    def test_my_accounts_lists_siblings(self):
        self._bind_both()
        tok = self.login_token('p_one')
        r = self.client.get('/api/auth/my-accounts',
                            headers={'Authorization': 'Bearer ' + tok})
        self.assertEqual(r.status_code, 200)
        accounts = r.get_json()['accounts']
        self.assertEqual(len(accounts), 2)
        current = [a for a in accounts if a['current']]
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]['displayName'], '孩子甲')

    def test_switch_to_sibling_issues_new_session(self):
        self._bind_both()
        tok = self.login_token('p_one')
        accounts = self.client.get('/api/auth/my-accounts',
                                   headers={'Authorization': 'Bearer ' + tok}).get_json()['accounts']
        target = next(a for a in accounts if not a['current'])
        r = self.client.post('/api/auth/switch-account',
                             json={'accountId': target['accountId']},
                             headers={'Authorization': 'Bearer ' + tok})
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d['success'])
        self.assertEqual(d['user']['displayName'], '孩子乙')
        me = self.client.get('/api/auth/me',
                             headers={'Authorization': 'Bearer ' + d['sessionToken']}).get_json()
        self.assertEqual(me.get('boundIdCard') or me.get('boundStudent', {}).get('idCard'), 'STU-B')

    def test_switch_requires_same_dingtalk_binding(self):
        # 只绑 p_one；p_two 未绑钉钉 → 不可切换
        self.bind(self.login_token('p_one'))
        tok = self.login_token('p_one')
        r = self.client.post('/api/auth/switch-account', json={'accountId': 2},
                            headers={'Authorization': 'Bearer ' + tok})
        self.assertEqual(r.status_code, 403)

    def test_unbound_account_sees_only_self(self):
        tok = self.login_token('p_one')     # 未绑定钉钉
        accounts = self.client.get('/api/auth/my-accounts',
                                   headers={'Authorization': 'Bearer ' + tok}).get_json()['accounts']
        self.assertEqual(len(accounts), 1)
        self.assertTrue(accounts[0]['current'])

    def test_switch_rejects_inactive_target(self):
        self._bind_both()
        import sqlite3 as s3
        adb = s3.connect(self.auth_db_path)
        adb.execute("UPDATE auth_accounts SET is_active=0 WHERE username='p_two'")
        adb.commit(); adb.close()
        tok = self.login_token('p_one')
        r = self.client.post('/api/auth/switch-account', json={'accountId': 2},
                            headers={'Authorization': 'Bearer ' + tok})
        self.assertIn(r.status_code, (403, 404))


class KidSwitcherUiTests(unittest.TestCase):
    def test_user_auth_wires_account_switch(self):
        js = (Path(__file__).resolve().parents[1] / 'assets' / 'user-auth.js').read_text(encoding='utf-8')
        self.assertIn('/api/auth/my-accounts', js)
        self.assertIn('/api/auth/switch-account', js)


if __name__ == '__main__':
    unittest.main()
