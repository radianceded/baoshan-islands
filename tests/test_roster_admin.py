# -*- coding: utf-8 -*-
"""总务老师「学生与选餐账号管理」API：查询/转入/转出/暂停恢复/重置密码"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from server import app as server_app


class _RosterBase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.auth_db_path = str(root / 'auth_accounts.db')
        self.stu_db_path = str(root / 'student_data.db')
        self.old = (server_app.AUTH_DB_PATH, server_app.DB_PATH)
        server_app.AUTH_DB_PATH = self.auth_db_path
        server_app.DB_PATH = self.stu_db_path

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
               display_name, bound_student_userid, bound_grade, bound_class)
               VALUES(?, ?, ?, ?, 'benbu', ?, ?, ?, ?)''',
            [
                ('gt', pwd, 'teacher', 'general', '总务', None, None, None),
                ('ct', pwd, 'teacher', 'class', '班主任', None, '三年级', '1班'),
                ('parent_a', pwd, 'parent', None, '学生甲', 'STU-A', '三年级', '1班'),
            ])
        adb.commit()
        adb.close()

        sdb = sqlite3.connect(self.stu_db_path)
        sdb.execute('''CREATE TABLE students_benbu(
            dingtalk_userid TEXT PRIMARY KEY, id_card TEXT, name TEXT,
            grade_name TEXT, class_name TEXT)''')
        sdb.executemany('INSERT INTO students_benbu VALUES(?,?,?,?,?)', [
            ('STU-A', 'STU-A', '学生甲', '三年级', '1班'),
            ('STU-B', 'STU-B', '学生乙', '三年级', '1班'),   # 无家长账号
            ('STU-C', 'STU-C', '学生丙', '三年级', '2班'),   # 别班，用于班主任越界测试
        ])
        sdb.commit()
        sdb.close()
        server_app.app.config['TESTING'] = True
        self.client = server_app.app.test_client()

    def tearDown(self):
        server_app.AUTH_DB_PATH, server_app.DB_PATH = self.old
        self.temp_dir.cleanup()

    def token(self, username='gt', entry='general_teacher', password='Pass-123'):
        r = self.client.post('/api/login', json={
            'username': username, 'password': password,
            'entry': entry, 'campus': 'benbu'})
        return r.get_json()['sessionToken']

    def h(self, tok):
        return {'Authorization': 'Bearer ' + tok}


class RosterPermissionTests(_RosterBase):
    def test_requires_general_teacher(self):
        self.assertEqual(self.client.get('/api/roster/students').status_code, 403)
        parent_tok = self.token('parent_a', 'parent')
        self.assertEqual(self.client.get('/api/roster/students',
                                         headers=self.h(parent_tok)).status_code, 403)
        ct_tok = self.token('ct', 'class_teacher')
        self.assertEqual(self.client.get('/api/roster/students',
                                         headers=self.h(ct_tok)).status_code, 200)  # 班主任限本班
        gt_tok = self.token()
        self.assertEqual(self.client.get('/api/roster/students',
                                         headers=self.h(gt_tok)).status_code, 200)


class RosterListTests(_RosterBase):
    def test_list_students_with_account_state(self):
        r = self.client.get('/api/roster/students?grade=三年级&className=1班',
                            headers=self.h(self.token()))
        data = r.get_json()['students']
        self.assertEqual(len(data), 2)
        by_name = {s['name']: s for s in data}
        self.assertEqual(by_name['学生甲']['account']['username'], 'parent_a')
        self.assertTrue(by_name['学生甲']['account']['isActive'])
        self.assertIsNone(by_name['学生乙']['account'])


class TransferInTests(_RosterBase):
    def test_transfer_in_creates_student_and_account(self):
        gt = self.token()
        r = self.client.post('/api/roster/transfer-in',
                             json={'name': '新同学', 'grade': '三年级',
                                   'className': '2班', 'username': 'xintongxue'},
                             headers=self.h(gt))
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d['username'], 'xintongxue')
        self.assertTrue(d['tempPassword'])
        # 新家长账号立即可登录且要求首登改密
        login = self.client.post('/api/login', json={
            'username': 'xintongxue', 'password': d['tempPassword'],
            'entry': 'parent', 'campus': 'benbu'}).get_json()
        self.assertTrue(login['success'])
        self.assertTrue(login['user']['mustChangePassword'])
        self.assertEqual(login['user']['bound_grade'], '三年级')

    def test_transfer_in_rejects_duplicate_username(self):
        gt = self.token()
        r = self.client.post('/api/roster/transfer-in',
                             json={'name': '重复号', 'grade': '三年级',
                                   'className': '2班', 'username': 'parent_a'},
                             headers=self.h(gt))
        self.assertEqual(r.status_code, 409)
        self.assertIn('suggest', r.get_json())

    def test_transfer_in_rejects_existing_student_same_class(self):
        gt = self.token()
        r = self.client.post('/api/roster/transfer-in',
                             json={'name': '学生甲', 'grade': '三年级',
                                   'className': '1班', 'username': 'xsj2'},
                             headers=self.h(gt))
        self.assertEqual(r.status_code, 409)


class TransferOutTests(_RosterBase):
    def test_transfer_out_requires_matching_confirm_name(self):
        gt = self.token()
        r = self.client.post('/api/roster/transfer-out',
                             json={'studentUserId': 'STU-A', 'confirmName': '写错了'},
                             headers=self.h(gt))
        self.assertEqual(r.status_code, 400)

    def test_transfer_out_deletes_student_and_account(self):
        gt = self.token()
        r = self.client.post('/api/roster/transfer-out',
                             json={'studentUserId': 'STU-A', 'confirmName': '学生甲'},
                             headers=self.h(gt))
        self.assertEqual(r.status_code, 200)
        sdb = sqlite3.connect(self.stu_db_path)
        self.assertIsNone(sdb.execute(
            "SELECT 1 FROM students_benbu WHERE dingtalk_userid='STU-A'").fetchone())
        adb = sqlite3.connect(self.auth_db_path)
        self.assertIsNone(adb.execute(
            "SELECT 1 FROM auth_accounts WHERE bound_student_userid='STU-A'").fetchone())


class PauseResumeTests(_RosterBase):
    def test_pause_blocks_login_and_resume_restores(self):
        gt = self.token()
        r = self.client.post('/api/roster/pause',
                             json={'studentUserId': 'STU-A', 'active': 0},
                             headers=self.h(gt))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.post('/api/login', json={
            'username': 'parent_a', 'password': 'Pass-123',
            'entry': 'parent', 'campus': 'benbu'}).status_code, 401)
        self.client.post('/api/roster/pause',
                         json={'studentUserId': 'STU-A', 'active': 1},
                         headers=self.h(gt))
        self.assertEqual(self.client.post('/api/login', json={
            'username': 'parent_a', 'password': 'Pass-123',
            'entry': 'parent', 'campus': 'benbu'}).status_code, 200)


class ResetPasswordTests(_RosterBase):
    def test_reset_password_issues_temp_and_forces_change(self):
        gt = self.token()
        r = self.client.post('/api/roster/reset-password',
                             json={'studentUserId': 'STU-A'},
                             headers=self.h(gt))
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d['username'], 'parent_a')
        # 旧密码失效，新临时密码可登录且强制改密
        self.assertEqual(self.client.post('/api/login', json={
            'username': 'parent_a', 'password': 'Pass-123',
            'entry': 'parent', 'campus': 'benbu'}).status_code, 401)
        login = self.client.post('/api/login', json={
            'username': 'parent_a', 'password': d['tempPassword'],
            'entry': 'parent', 'campus': 'benbu'}).get_json()
        self.assertTrue(login['success'])
        self.assertTrue(login['user']['mustChangePassword'])


class RosterLogTests(_RosterBase):
    def test_operations_are_logged(self):
        gt = self.token()
        self.client.post('/api/roster/pause',
                         json={'studentUserId': 'STU-A', 'active': 0},
                         headers=self.h(gt))
        sdb = sqlite3.connect(self.stu_db_path)
        rows = sdb.execute('SELECT op, detail, operator FROM roster_ops_log').fetchall()
        self.assertTrue(rows)
        self.assertEqual(rows[0][0], 'pause')


class RosterUiTests(unittest.TestCase):
    def test_general_view_has_roster_panel(self):
        html = (Path(__file__).resolve().parents[1] / 'nutrition' / 'recommendations.html'
                ).read_text(encoding='utf-8')
        self.assertIn('id="rosterPanel"', html)
        self.assertIn('/api/roster/students', html)
        self.assertIn('/api/roster/transfer-in', html)
        # 确认弹层不使用原生 confirm（钉钉 webview 会吞掉）
        self.assertIn('rosterConfirmVeil', html)
        self.assertIn('rosterTeacherBlock', html)          # 总务：班主任账号重置块
        self.assertIn('/api/roster/reset-teacher-password', html)
        self.assertIn('mountRosterForClassTeacher', html)  # 班主任视图挂载


class ClubCategoryNamingTests(unittest.TestCase):
    """社团分类不得出现学科属性用词（合规要求），subject 键显示为「益智」"""

    def test_subject_category_displays_as_yizhi(self):
        html = (Path(__file__).resolve().parents[1] / 'island-activity.html').read_text(encoding='utf-8')
        self.assertIn("{key:'subject', name:'益智'", html)
        self.assertNotIn("name:'学科'", html)


class ClassTeacherScopeTests(_RosterBase):
    """班主任可管本班学生账号；越界一律 403"""

    def test_class_teacher_list_is_forced_to_own_class(self):
        ct = self.token('ct', 'class_teacher')
        r = self.client.get('/api/roster/students?grade=三年级&className=2班',
                            headers=self.h(ct))
        self.assertEqual(r.status_code, 200)
        names = [s['name'] for s in r.get_json()['students']]
        self.assertIn('学生甲', names)
        self.assertNotIn('学生丙', names)          # 传了 2 班参数也只回本班

    def test_class_teacher_can_manage_own_class_student(self):
        ct = self.token('ct', 'class_teacher')
        r = self.client.post('/api/roster/pause',
                             json={'studentUserId': 'STU-A', 'active': 0},
                             headers=self.h(ct))
        self.assertEqual(r.status_code, 200)
        r2 = self.client.post('/api/roster/reset-password',
                              json={'studentUserId': 'STU-A'},
                              headers=self.h(ct))
        self.assertEqual(r2.status_code, 200)

    def test_class_teacher_cannot_touch_other_class(self):
        ct = self.token('ct', 'class_teacher')
        r = self.client.post('/api/roster/pause',
                             json={'studentUserId': 'STU-C', 'active': 0},
                             headers=self.h(ct))
        self.assertEqual(r.status_code, 403)
        r2 = self.client.post('/api/roster/transfer-in',
                              json={'name': '越界生', 'grade': '三年级',
                                    'className': '2班', 'username': 'yuejie'},
                              headers=self.h(ct))
        self.assertEqual(r2.status_code, 403)

    def test_class_teacher_transfer_in_own_class_ok(self):
        ct = self.token('ct', 'class_teacher')
        r = self.client.post('/api/roster/transfer-in',
                             json={'name': '本班新生', 'grade': '三年级',
                                   'className': '1班', 'username': 'benbanxinsheng'},
                             headers=self.h(ct))
        self.assertEqual(r.status_code, 200)


class ResetTeacherPasswordTests(_RosterBase):
    """总务可重置班主任账号密码；班主任无此权限"""

    def test_general_teacher_lists_and_resets_class_teacher(self):
        gt = self.token()
        r = self.client.get('/api/roster/teachers', headers=self.h(gt))
        self.assertEqual(r.status_code, 200)
        teachers = r.get_json()['teachers']
        ct_row = next(x for x in teachers if x['username'] == 'ct')
        r2 = self.client.post('/api/roster/reset-teacher-password',
                              json={'accountId': ct_row['id']},
                              headers=self.h(gt))
        self.assertEqual(r2.status_code, 200)
        d = r2.get_json()
        self.assertEqual(d['username'], 'ct')
        self.assertTrue(d['tempPassword'])
        # 旧密码失效，新临时密码可登录且不弹首登面板
        self.assertEqual(self.client.post('/api/login', json={
            'username': 'ct', 'password': 'Pass-123',
            'entry': 'class_teacher', 'campus': 'benbu'}).status_code, 401)
        login = self.client.post('/api/login', json={
            'username': 'ct', 'password': d['tempPassword'],
            'entry': 'class_teacher', 'campus': 'benbu'}).get_json()
        self.assertTrue(login['success'])
        self.assertFalse(login['user']['mustChangePassword'])

    def test_class_teacher_cannot_reset_teachers(self):
        ct = self.token('ct', 'class_teacher')
        self.assertEqual(self.client.get('/api/roster/teachers',
                                         headers=self.h(ct)).status_code, 403)
        self.assertEqual(self.client.post('/api/roster/reset-teacher-password',
                                          json={'accountId': 2},
                                          headers=self.h(ct)).status_code, 403)


class LegacyNullUseridRowTests(_RosterBase):
    """早期转入的学生行 dingtalk_userid 为 NULL（如罗泾贾依依）：列表应回退 id_card,
       且能正常转出（曾报 studentUserId required）"""

    def setUp(self):
        super().setUp()
        sdb = sqlite3.connect(self.stu_db_path)
        sdb.execute("INSERT INTO students_benbu(dingtalk_userid, id_card, name, grade_name, class_name) "
                    "VALUES(NULL, 'TRF_legacy', '遗留生', '三年级', '1班')")
        sdb.commit(); sdb.close()

    def test_list_falls_back_to_id_card(self):
        r = self.client.get('/api/roster/students?grade=三年级&className=1班',
                            headers=self.h(self.token()))
        stu = next(s for s in r.get_json()['students'] if s['name'] == '遗留生')
        self.assertEqual(stu['studentUserId'], 'TRF_legacy')

    def test_transfer_out_works_via_id_card(self):
        r = self.client.post('/api/roster/transfer-out',
                             json={'studentUserId': 'TRF_legacy', 'confirmName': '遗留生'},
                             headers=self.h(self.token()))
        self.assertEqual(r.status_code, 200)
        sdb = sqlite3.connect(self.stu_db_path)
        self.assertIsNone(sdb.execute(
            "SELECT 1 FROM students_benbu WHERE id_card='TRF_legacy'").fetchone())


if __name__ == '__main__':
    unittest.main()
