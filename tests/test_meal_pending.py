# -*- coding: utf-8 -*-
"""未订餐提示：总务看各班未订人数汇总，班主任一键钉钉提醒未订餐家长"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from server import app as server_app

SERVICE_DAYS = json.dumps([
    {'plan_date': '2026-09-14', 'weekday': i, 'weekday_label': '周%d' % i,
     'service_status': 'normal', 'service_note': ''} for i in (1, 2, 3, 4, 5)
])


class _PendingBase(unittest.TestCase):
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
            must_change_password INTEGER NOT NULL DEFAULT 0,
            dingtalk_userid TEXT)''')
        pwd = generate_password_hash('Pass-123', method='pbkdf2:sha256:1000')
        adb.executemany(
            '''INSERT INTO auth_accounts(username, password_hash, role, sub_role, campus_id,
               display_name, bound_student_userid, bound_grade, bound_class, dingtalk_userid)
               VALUES(?, ?, ?, ?, 'benbu', ?, ?, ?, ?, ?)''',
            [
                ('gt', pwd, 'teacher', 'general', '总务', None, None, None, None),
                ('ct', pwd, 'teacher', 'class', '班主任', None, '三年级', '1班', None),
                # 学生甲家长：已绑定钉钉；学生乙家长：未绑定；学生丙(三2)无家长账号
                ('pa', pwd, 'parent', None, '学生甲', 'STU-A', '三年级', '1班', 'DT-PA'),
                ('pb', pwd, 'parent', None, '学生乙', 'STU-B', '三年级', '1班', None),
            ])
        adb.commit()
        adb.close()

        sdb = sqlite3.connect(self.stu_db_path)
        sdb.execute('''CREATE TABLE students_benbu(
            dingtalk_userid TEXT PRIMARY KEY, id_card TEXT, name TEXT,
            grade_name TEXT, class_name TEXT)''')
        sdb.executemany('INSERT INTO students_benbu VALUES(?,?,?,?,?)', [
            ('STU-A', 'STU-A', '学生甲', '三年级', '1班'),
            ('STU-B', 'STU-B', '学生乙', '三年级', '1班'),
            ('STU-C', 'STU-C', '学生丙', '三年级', '2班'),
        ])
        sdb.execute('''CREATE TABLE weekly_menus(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_number INTEGER, parity TEXT, date_start TEXT, date_end TEXT,
            image_path TEXT, notes TEXT, uploaded_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            selection_deadline TEXT, import_batch_id INTEGER,
            service_days_json TEXT, default_a_finalized_at TEXT)''')
        sdb.executemany(
            'INSERT INTO weekly_menus(week_number, parity, service_days_json, selection_deadline) '
            'VALUES(?,?,?,?)',
            [(3, 'odd', SERVICE_DAYS, '2026-09-11T13:00'),
             (4, 'even', SERVICE_DAYS, '2026-09-11T13:00')])
        sdb.execute('''CREATE TABLE meal_choices(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_card TEXT NOT NULL, name TEXT, grade_name TEXT, class_name TEXT,
            week_number INTEGER NOT NULL, parity TEXT NOT NULL,
            weekday INTEGER NOT NULL, choice TEXT NOT NULL,
            chosen_by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        # 学生甲：完整选完 10 天；学生乙/丙：一天没选
        rows = []
        for wk, parity in ((3, 'odd'), (4, 'even')):
            for d in (1, 2, 3, 4, 5):
                rows.append(('STU-A', '学生甲', '三年级', '1班', wk, parity, d, 'A'))
        sdb.executemany(
            'INSERT INTO meal_choices(id_card, name, grade_name, class_name, week_number, '
            'parity, weekday, choice) VALUES(?,?,?,?,?,?,?,?)', rows)
        sdb.commit()
        sdb.close()
        server_app.app.config['TESTING'] = True
        self.client = server_app.app.test_client()
        self.sent = []
        self._orig_send = server_app._send_dt_work_notification
        server_app._send_dt_work_notification = (
            lambda uid, title, content, campus: self.sent.append((uid, title)) or True)

    def tearDown(self):
        server_app.AUTH_DB_PATH, server_app.DB_PATH = self.old
        server_app._send_dt_work_notification = self._orig_send
        self.temp_dir.cleanup()

    def token(self, username='gt', entry='general_teacher'):
        r = self.client.post('/api/login', json={
            'username': username, 'password': 'Pass-123',
            'entry': entry, 'campus': 'benbu'})
        return r.get_json()['sessionToken']

    def h(self, tok):
        return {'Authorization': 'Bearer ' + tok}

    OVERVIEW = '/api/meal-stats/pending-overview?week_odd=3&week_even=4'


class PendingOverviewTests(_PendingBase):
    def test_general_teacher_sees_all_classes(self):
        r = self.client.get(self.OVERVIEW, headers=self.h(self.token()))
        self.assertEqual(r.status_code, 200)
        rows = r.get_json()['classes']
        by_class = {(x['grade'], x['className']): x for x in rows}
        c31 = by_class[('三年级', '1班')]
        self.assertEqual(c31['total'], 2)
        self.assertEqual(c31['incomplete'], 1)     # 学生乙
        self.assertEqual(c31['unstarted'], 1)
        c32 = by_class[('三年级', '2班')]
        self.assertEqual(c32['incomplete'], 1)     # 学生丙

    def test_class_teacher_sees_only_own_class(self):
        r = self.client.get(self.OVERVIEW, headers=self.h(self.token('ct', 'class_teacher')))
        rows = r.get_json()['classes']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['className'], '1班')

    def test_parent_forbidden(self):
        r = self.client.get(self.OVERVIEW, headers=self.h(self.token('pa', 'parent')))
        self.assertEqual(r.status_code, 403)


class RemindPendingTests(_PendingBase):
    URL = '/api/meal-stats/remind-pending'

    def test_reminds_bound_parents_and_counts_unbound(self):
        r = self.client.post(self.URL,
                             json={'week_odd': 3, 'week_even': 4,
                                   'grade': '三年级', 'className': '1班'},
                             headers=self.h(self.token()))
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d['reminded'], 0)         # 学生乙家长未绑定钉钉
        self.assertEqual(d['noBinding'], 1)
        # 绑定后：学生乙家长换成绑定的
        adb = sqlite3.connect(self.auth_db_path)
        adb.execute("UPDATE auth_accounts SET dingtalk_userid='DT-PB' WHERE username='pb'")
        adb.commit(); adb.close()
        r2 = self.client.post(self.URL,
                              json={'week_odd': 3, 'week_even': 4,
                                    'grade': '三年级', 'className': '1班'},
                              headers=self.h(self.token()))
        d2 = r2.get_json()
        self.assertEqual(d2['reminded'], 1)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][0], 'DT-PB')

    def test_same_day_dedup(self):
        adb = sqlite3.connect(self.auth_db_path)
        adb.execute("UPDATE auth_accounts SET dingtalk_userid='DT-PB' WHERE username='pb'")
        adb.commit(); adb.close()
        body = {'week_odd': 3, 'week_even': 4, 'grade': '三年级', 'className': '1班'}
        gt = self.token()
        self.client.post(self.URL, json=body, headers=self.h(gt))
        r2 = self.client.post(self.URL, json=body, headers=self.h(gt))
        d2 = r2.get_json()
        self.assertEqual(d2['reminded'], 0)
        self.assertEqual(d2['skippedToday'], 1)
        self.assertEqual(len(self.sent), 1)

    def test_class_teacher_locked_to_own_class(self):
        ct = self.token('ct', 'class_teacher')
        r = self.client.post(self.URL,
                             json={'week_odd': 3, 'week_even': 4,
                                   'grade': '三年级', 'className': '2班'},
                             headers=self.h(ct))
        self.assertEqual(r.status_code, 200)
        # 班主任传别班参数被强制回本班：不会提醒 2 班的学生丙
        d = r.get_json()
        self.assertEqual(d.get('grade'), '三年级')
        self.assertEqual(d.get('className'), '1班')

    def test_parent_forbidden(self):
        r = self.client.post(self.URL, json={'week_odd': 3, 'week_even': 4},
                             headers=self.h(self.token('pa', 'parent')))
        self.assertEqual(r.status_code, 403)


class PendingUiTests(unittest.TestCase):
    def test_frontend_wired(self):
        html = (Path(__file__).resolve().parents[1] / 'nutrition' / 'recommendations.html'
                ).read_text(encoding='utf-8')
        self.assertIn('/api/meal-stats/pending-overview', html)
        self.assertIn('/api/meal-stats/remind-pending', html)
        self.assertIn('pendingOverviewBody', html)


if __name__ == '__main__':
    unittest.main()
