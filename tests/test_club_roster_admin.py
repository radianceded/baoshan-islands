# -*- coding: utf-8 -*-
"""社团名单调整（发布确认前）：总务可移出待确认学生、补录学生、按姓名搜学生"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from server import app as server_app

SEMESTER = server_app.CLUB_SEMESTER


class _ClubRosterBase(unittest.TestCase):
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
               display_name, bound_grade, bound_class)
               VALUES(?, ?, ?, ?, 'benbu', ?, ?, ?)''',
            [
                ('gt', pwd, 'teacher', 'general', '总务', None, None),
                ('ct', pwd, 'teacher', 'class', '班主任', '三年级', '1班'),
            ])
        adb.commit()
        adb.close()

        sdb = sqlite3.connect(self.stu_db_path)
        sdb.execute('''CREATE TABLE students_benbu(
            dingtalk_userid TEXT PRIMARY KEY, id_card TEXT, name TEXT,
            grade_name TEXT, class_name TEXT)''')
        sdb.executemany('INSERT INTO students_benbu VALUES(?,?,?,?,?)', [
            ('STU-A', 'STU-A', '甲小明', '三年级', '1班'),
            ('STU-B', 'STU-B', '乙小红', '三年级', '2班'),
            ('STU-C', 'STU-C', '丙小刚', '三年级', '3班'),
            ('STU-D', 'STU-D', '丁小美', '三年级', '4班'),
        ])
        sdb.execute('''CREATE TABLE club_course_catalog(
            id TEXT PRIMARY KEY, semester TEXT, campus TEXT, name TEXT, teacher TEXT,
            weekday TEXT, location TEXT, capacity INTEGER, note TEXT,
            is_active INTEGER DEFAULT 1, sort_order INTEGER,
            created_at TEXT, updated_at TEXT, selection_mode TEXT DEFAULT 'signup',
            eligible_grades TEXT, source_number TEXT, grade_quotas TEXT)''')
        sdb.execute(
            "INSERT INTO club_course_catalog(id, semester, campus, name, teacher, capacity, "
            "eligible_grades) VALUES('art-1', ?, '东校区', '创意美术', '张老师', 3, '三年级')",
            (SEMESTER,))
        sdb.execute('''CREATE TABLE club_signups(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL, course_id TEXT NOT NULL, semester TEXT NOT NULL,
            registered_by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'pending',
            confirmed_by TEXT, confirmed_at TEXT, grade TEXT)''')
        sdb.execute(
            "INSERT INTO club_signups(student_id, course_id, semester, status, grade) "
            "VALUES('STU-A', 'art-1', ?, 'pending', '三年级')", (SEMESTER,))
        sdb.execute(
            "INSERT INTO club_signups(student_id, course_id, semester, status, grade) "
            "VALUES('STU-D', 'art-1', ?, 'confirmed', '三年级')", (SEMESTER,))
        sdb.execute('''CREATE TABLE club_admission_windows(
            semester TEXT, grade TEXT, preview_at TEXT, open_at TEXT, close_at TEXT,
            published_at TEXT, updated_by TEXT, updated_at TEXT,
            PRIMARY KEY(semester, grade))''')
        sdb.execute(
            "INSERT INTO club_admission_windows(semester, grade, preview_at, open_at, close_at) "
            "VALUES(?, '三年级', '2020-01-01T00:00', '2020-01-01T00:00', '2099-01-01T00:00')",
            (SEMESTER,))
        sdb.commit()
        sdb.close()
        server_app.app.config['TESTING'] = True
        self.client = server_app.app.test_client()

    def tearDown(self):
        server_app.AUTH_DB_PATH, server_app.DB_PATH = self.old
        self.temp_dir.cleanup()

    def token(self, username='gt', entry='general_teacher'):
        r = self.client.post('/api/login', json={
            'username': username, 'password': 'Pass-123',
            'entry': entry, 'campus': 'benbu'})
        return r.get_json()['sessionToken']

    def h(self, tok):
        return {'Authorization': 'Bearer ' + tok}

    def status_of(self, student_id):
        db = sqlite3.connect(self.stu_db_path)
        row = db.execute("SELECT status FROM club_signups WHERE student_id=? AND course_id='art-1'",
                         (student_id,)).fetchone()
        return row[0] if row else None


class RemoveSignupTests(_ClubRosterBase):
    def test_general_teacher_removes_pending(self):
        r = self.client.post('/api/clubs/art-1/roster/remove', json={'studentId': 'STU-A'},
                             headers=self.h(self.token()))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.status_of('STU-A'), 'cancelled')

    def test_cannot_remove_confirmed(self):
        r = self.client.post('/api/clubs/art-1/roster/remove', json={'studentId': 'STU-D'},
                             headers=self.h(self.token()))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.status_of('STU-D'), 'confirmed')

    def test_class_teacher_forbidden(self):
        r = self.client.post('/api/clubs/art-1/roster/remove', json={'studentId': 'STU-A'},
                             headers=self.h(self.token('ct', 'class_teacher')))
        self.assertEqual(r.status_code, 403)


class AddSignupTests(_ClubRosterBase):
    def test_add_student_as_pending(self):
        r = self.client.post('/api/clubs/art-1/roster/add', json={'studentId': 'STU-B'},
                             headers=self.h(self.token()))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.status_of('STU-B'), 'pending')

    def test_add_rejects_duplicate(self):
        r = self.client.post('/api/clubs/art-1/roster/add', json={'studentId': 'STU-A'},
                             headers=self.h(self.token()))
        self.assertEqual(r.status_code, 409)

    def test_add_respects_capacity(self):
        gt = self.token()
        # capacity=3：加入 STU-B 后满（STU-A pending + STU-D confirmed + STU-B）
        self.client.post('/api/clubs/art-1/roster/add', json={'studentId': 'STU-B'},
                         headers=self.h(gt))
        r = self.client.post('/api/clubs/art-1/roster/add', json={'studentId': 'STU-C'},
                             headers=self.h(gt))
        self.assertEqual(r.status_code, 409)
        self.assertIn('名额', r.get_json()['error'])

    def test_add_respects_per_student_limit(self):
        gt = self.token()
        # 先移出 STU-A 腾出名额
        self.client.post('/api/clubs/art-1/roster/remove', json={'studentId': 'STU-A'},
                         headers=self.h(gt))
        # STU-D 已确认在本社团 → 但换一个学生测限报：给 STU-B 在另一社团报名
        db = sqlite3.connect(self.stu_db_path)
        db.execute("INSERT INTO club_course_catalog(id, semester, campus, name, capacity) "
                   "VALUES('art-2', ?, '东校区', '合唱', 10)", (SEMESTER,))
        db.execute("INSERT INTO club_signups(student_id, course_id, semester, status, grade) "
                   "VALUES('STU-B', 'art-2', ?, 'pending', '三年级')", (SEMESTER,))
        db.commit(); db.close()
        r = self.client.post('/api/clubs/art-1/roster/add', json={'studentId': 'STU-B'},
                             headers=self.h(gt))
        self.assertEqual(r.status_code, 409)
        self.assertIn('已报', r.get_json()['error'])

    def test_add_unknown_student_404(self):
        r = self.client.post('/api/clubs/art-1/roster/add', json={'studentId': 'NOPE'},
                             headers=self.h(self.token()))
        self.assertEqual(r.status_code, 404)


class StudentSearchTests(_ClubRosterBase):
    def test_search_by_name(self):
        r = self.client.get('/api/clubs/roster/student-search?q=乙小',
                            headers=self.h(self.token()))
        self.assertEqual(r.status_code, 200)
        hits = r.get_json()['students']
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['studentId'], 'STU-B')

    def test_search_forbidden_for_class_teacher(self):
        r = self.client.get('/api/clubs/roster/student-search?q=乙',
                            headers=self.h(self.token('ct', 'class_teacher')))
        self.assertEqual(r.status_code, 403)


class ClubRosterUiTests(unittest.TestCase):
    def test_frontend_wired(self):
        html = (Path(__file__).resolve().parents[1] / 'island-activity.html'
                ).read_text(encoding='utf-8')
        self.assertIn('/roster/remove', html)
        self.assertIn('/roster/add', html)
        self.assertIn('clubRosterSearch', html)


class TeacherRosterViewTests(_ClubRosterBase):
    """老师端社团名单不显示已取消的报名（避免误点「移出」报已取消）"""

    def test_cancelled_hidden_from_teacher_roster(self):
        gt = self.token()
        self.client.post('/api/clubs/art-1/roster/remove', json={'studentId': 'STU-A'},
                         headers=self.h(gt))
        r = self.client.get('/api/clubs/art-1/signups', headers=self.h(gt))
        self.assertEqual(r.status_code, 200)
        ids = [s['studentId'] for s in r.get_json()['students']]
        self.assertNotIn('STU-A', ids)
        self.assertIn('STU-D', ids)     # 已确认的仍显示


class ParentViewAfterRemovalTests(_ClubRosterBase):
    """被移出的学生，家长端不再显示该社团的报名记录（可重新选课）"""

    def setUp(self):
        super().setUp()
        adb = sqlite3.connect(self.auth_db_path)
        pwd_row = adb.execute("SELECT password_hash FROM auth_accounts WHERE username='gt'").fetchone()
        adb.execute(
            """INSERT INTO auth_accounts(username, password_hash, role, sub_role, campus_id,
               display_name, bound_id_card, bound_grade, bound_class)
               VALUES('pa', ?, 'parent', NULL, 'benbu', '甲小明家长', 'STU-A', '三年级', '1班')""",
            (pwd_row[0],))
        adb.commit(); adb.close()

    def test_cancelled_signup_hidden_from_parent(self):
        gt = self.token()
        self.client.post('/api/clubs/art-1/roster/remove', json={'studentId': 'STU-A'},
                         headers=self.h(gt))
        pa = self.token('pa', 'parent')
        r = self.client.get('/api/clubs/signups', headers=self.h(pa))
        self.assertEqual(r.status_code, 200)
        course_ids = [s['courseId'] for s in r.get_json().get('signups', [])
                      if isinstance(s, dict) and 'courseId' in s] or \
                     [s.get('course_id') for s in r.get_json().get('signups', [])]
        self.assertNotIn('art-1', course_ids)


class RemovedStudentCanReapplyTests(_ClubRosterBase):
    """被移出的学生，家长可立即改报其他社团（cancelled 不占限报名额）"""

    def setUp(self):
        super().setUp()
        adb = sqlite3.connect(self.auth_db_path)
        pwd_row = adb.execute("SELECT password_hash FROM auth_accounts WHERE username='gt'").fetchone()
        adb.execute(
            """INSERT INTO auth_accounts(username, password_hash, role, sub_role, campus_id,
               display_name, bound_id_card, bound_grade, bound_class)
               VALUES('pa', ?, 'parent', NULL, 'benbu', '甲小明家长', 'STU-A', '三年级', '1班')""",
            (pwd_row[0],))
        adb.commit(); adb.close()
        db = sqlite3.connect(self.stu_db_path)
        db.execute("INSERT INTO club_course_catalog(id, semester, campus, name, capacity, eligible_grades, selection_mode) "
                   "VALUES('art-2', ?, '东校区', '合唱', 10, '三年级', 'selectable')", (SEMESTER,))
        db.commit(); db.close()

    def test_reapply_after_removal(self):
        gt = self.token()
        self.client.post('/api/clubs/art-1/roster/remove', json={'studentId': 'STU-A'},
                         headers=self.h(gt))
        pa = self.token('pa', 'parent')
        r = self.client.post('/api/clubs/signups', json={'course_id': 'art-2'},
                             headers=self.h(pa))
        self.assertIn(r.status_code, (200, 201), r.get_data(as_text=True))
        self.assertTrue(r.get_json().get('success'))


if __name__ == '__main__':
    unittest.main()
