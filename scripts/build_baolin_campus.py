#!/usr/bin/env python3
"""Build physically isolated Baolin business/auth databases from read-only rosters."""
from __future__ import annotations

import argparse
import json
import re
import secrets
import sqlite3
import string
from pathlib import Path

from openpyxl import load_workbook
from werkzeug.security import generate_password_hash


CAMPUS_ID = 'baolin'
PASSWORD_ALPHABET = ''.join(
    ch for ch in string.ascii_letters + string.digits if ch not in '0O1Il'
)
GRADE_MAP = {'一': '一年级', '二': '二年级', '三': '三年级', '四': '四年级', '五': '五年级', '六': '六年级'}
CLASS_RE = re.compile(r'-([一二三四五六])年级(\d+)班$')
TEACHER_CLASS_RE = re.compile(r'^([一二三四五六])(\d+)班班主任$')


def random_password(length: int = 12) -> str:
    return ''.join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def text(value) -> str:
    return str(value or '').strip()


def readonly_connection(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def read_students(path: Path) -> list[dict]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb['学生信息表1']
    rows = ws.iter_rows(values_only=True)
    header = tuple(text(value) for value in next(rows))
    expected = ('学生UserID', '学生姓名(必填)', '所在班级(必填)', '学号')
    if header[:4] != expected:
        raise SystemExit(f'Unexpected student columns: {header[:4]}')
    students = []
    for row in rows:
        user_id, name, full_class, school_no = (text(value) for value in row[:4])
        if not user_id and not name:
            continue
        if not user_id or not name or not full_class:
            raise SystemExit(f'Incomplete student row: userId={user_id!r}, name={name!r}')
        match = CLASS_RE.search(full_class)
        if not match:
            raise SystemExit(f'Cannot parse class for {name}: {full_class}')
        students.append({
            'userId': user_id,
            'idCard': user_id,
            'name': name,
            'schoolNo': school_no,
            'grade': GRADE_MAP[match.group(1)],
            'class': f'{match.group(2)}班',
            'fullClass': full_class,
        })
    wb.close()
    user_ids = [student['userId'] for student in students]
    if len(set(user_ids)) != len(user_ids):
        raise SystemExit('Duplicate student UserID in Baolin roster')
    if not students:
        raise SystemExit('Baolin student roster is empty')
    return students


def read_teachers(path: Path) -> tuple[list[dict], list[dict]]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header = tuple(text(value) for value in next(rows))
    if header[:4] != ('员工UserId', '姓名', '手机号码', '职位'):
        raise SystemExit(f'Unexpected teacher columns: {header[:4]}')
    teachers = []
    assignments = []
    for row in rows:
        user_id, name, mobile, position = (text(value) for value in row[:4])
        if not user_id and not name:
            continue
        if not user_id or not name:
            raise SystemExit(f'Incomplete teacher row: userId={user_id!r}, name={name!r}')
        teacher = {'userId': user_id, 'name': name, 'mobile': mobile, 'position': position}
        teachers.append(teacher)
        match = TEACHER_CLASS_RE.match(position)
        if match:
            assignments.append({
                **teacher,
                'grade': GRADE_MAP[match.group(1)],
                'class': f'{match.group(2)}班',
            })
    wb.close()
    user_ids = [teacher['userId'] for teacher in teachers]
    if len(set(user_ids)) != len(user_ids):
        raise SystemExit('Duplicate teacher UserID in Baolin roster')
    class_keys = [(assignment['grade'], assignment['class']) for assignment in assignments]
    if len(set(class_keys)) != len(class_keys):
        raise SystemExit('Duplicate class teacher assignment in Baolin roster')
    return teachers, assignments


def clone_empty_schema(source_path: Path, output_path: Path) -> sqlite3.Connection:
    source = readonly_connection(source_path)
    output = sqlite3.connect(output_path)
    objects = source.execute(
        '''SELECT type, name, sql FROM sqlite_master
           WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'
           ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1
                              WHEN 'view' THEN 2 WHEN 'trigger' THEN 3 ELSE 4 END,
                    name'''
    ).fetchall()
    for item in objects:
        output.execute(item['sql'])
    source.close()
    output.commit()
    return output


def create_business_db(path: Path, schema_source: Path, students: list[dict],
                       teachers: list[dict], assignments: list[dict]) -> None:
    db = clone_empty_schema(schema_source, path)
    db.execute('''CREATE TABLE students_baolin(
        dingtalk_userid TEXT PRIMARY KEY,
        id_card TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        school_no TEXT,
        grade_name TEXT NOT NULL,
        class_name TEXT NOT NULL,
        full_class TEXT,
        student_phone TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        school_name TEXT NOT NULL DEFAULT '宝林校区',
        gender TEXT
    )''')
    db.execute('''CREATE TABLE teacher_roster_baolin(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dingtalk_userid TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        mobile TEXT,
        department TEXT,
        position TEXT,
        campus TEXT NOT NULL CHECK(campus='baolin'),
        is_admin INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('''CREATE TABLE class_teachers_baolin(
        class_name TEXT NOT NULL,
        grade_name TEXT NOT NULL,
        teacher_name TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        dingtalk_userid TEXT NOT NULL,
        PRIMARY KEY (grade_name, class_name)
    )''')
    db.executemany(
        '''INSERT INTO students_baolin(
               dingtalk_userid, id_card, name, school_no, grade_name,
               class_name, full_class, school_name
           ) VALUES(?,?,?,?,?,?,?,'宝林校区')''',
        [(s['userId'], s['idCard'], s['name'], s['schoolNo'], s['grade'],
          s['class'], s['fullClass']) for s in students],
    )
    db.executemany(
        '''INSERT INTO teacher_roster_baolin(
               dingtalk_userid, name, mobile, position, campus, is_admin
           ) VALUES(?,?,?,?,'baolin',0)''',
        [(t['userId'], t['name'], t['mobile'], t['position']) for t in teachers],
    )
    db.executemany(
        '''INSERT INTO class_teachers_baolin(
               class_name, grade_name, teacher_name, dingtalk_userid
           ) VALUES(?,?,?,?)''',
        [(a['class'], a['grade'], a['name'], a['userId']) for a in assignments],
    )
    db.commit()
    db.close()


def create_auth_db(path: Path, students: list[dict], teachers: list[dict],
                   assignments: list[dict], general_names: list[str]) -> dict:
    teachers_by_name = {teacher['name']: teacher for teacher in teachers}
    class_user_ids = {assignment['userId'] for assignment in assignments}
    general_teachers = []
    for name in general_names:
        teacher = teachers_by_name.get(name)
        if not teacher:
            raise SystemExit(f'General teacher missing from teacher roster: {name}')
        if teacher['userId'] in class_user_ids:
            raise SystemExit(f'Role collision: {name} is already a class teacher')
        general_teachers.append(teacher)

    db = sqlite3.connect(path)
    db.execute('''CREATE TABLE auth_accounts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('parent', 'teacher')),
        sub_role TEXT CHECK(sub_role IS NULL OR sub_role IN ('class', 'general')),
        campus_id TEXT NOT NULL CHECK(campus_id='baolin'),
        display_name TEXT NOT NULL,
        bound_student_userid TEXT,
        bound_id_card TEXT,
        bound_grade TEXT,
        bound_class TEXT,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
        auth_version INTEGER NOT NULL DEFAULT 1,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked_until INTEGER,
        last_login_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK(
            (role='parent' AND sub_role IS NULL AND bound_student_userid IS NOT NULL)
            OR (role='teacher' AND sub_role='class' AND bound_grade IS NOT NULL
                AND bound_class IS NOT NULL AND bound_student_userid IS NULL)
            OR (role='teacher' AND sub_role='general' AND bound_student_userid IS NULL
                AND bound_grade IS NULL AND bound_class IS NULL)
        )
    )''')
    db.execute('CREATE INDEX idx_auth_active_role ON auth_accounts(is_active, role, sub_role)')
    credentials = {'campus': CAMPUS_ID, 'students': [], 'classTeachers': [], 'generalTeachers': []}

    def insert_account(*, username, password, role, sub_role, display_name,
                       student_userid=None, id_card=None, grade=None, class_name=None):
        db.execute(
            '''INSERT INTO auth_accounts(
                   username, password_hash, role, sub_role, campus_id, display_name,
                   bound_student_userid, bound_id_card, bound_grade, bound_class
               ) VALUES(?,?,?,?,'baolin',?,?,?,?,?)''',
            (username, generate_password_hash(password, method='pbkdf2:sha256:100000'),
             role, sub_role, display_name, student_userid, id_card, grade, class_name),
        )

    for student in students:
        password = random_password()
        insert_account(
            username=student['userId'], password=password, role='parent', sub_role=None,
            display_name=student['name'], student_userid=student['userId'],
            id_card=student['idCard'], grade=student['grade'], class_name=student['class'],
        )
        credentials['students'].append({
            '校区': '宝林校区', '年级': student['grade'], '班级': student['class'],
            '姓名': student['name'], '账号': student['userId'], '密码': password,
        })

    for assignment in assignments:
        password = random_password()
        insert_account(
            username=assignment['userId'], password=password, role='teacher',
            sub_role='class', display_name=assignment['name'],
            grade=assignment['grade'], class_name=assignment['class'],
        )
        credentials['classTeachers'].append({
            '校区': '宝林校区', '年级': assignment['grade'], '班级': assignment['class'],
            '姓名': assignment['name'], '账号': assignment['userId'], '密码': password,
        })

    for teacher in general_teachers:
        password = random_password()
        insert_account(
            username=teacher['userId'], password=password, role='teacher',
            sub_role='general', display_name=teacher['name'],
        )
        credentials['generalTeachers'].append({
            '校区': '宝林校区', '姓名': teacher['name'],
            '账号': teacher['userId'], '密码': password,
        })

    db.commit()
    db.close()
    return credentials


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--student-roster', type=Path, required=True)
    parser.add_argument('--teacher-roster', type=Path, required=True)
    parser.add_argument('--schema-source-db', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--general-teacher', action='append', default=[])
    args = parser.parse_args()

    business_path = args.output_dir / 'student_data.db'
    auth_path = args.output_dir / 'auth_accounts.db'
    credentials_path = args.output_dir / 'credentials.json'
    for output in (business_path, auth_path, credentials_path):
        if output.exists():
            raise SystemExit(f'Refusing to overwrite existing output: {output}')
    args.output_dir.mkdir(parents=True, exist_ok=True)

    students = read_students(args.student_roster)
    teachers, assignments = read_teachers(args.teacher_roster)
    create_business_db(business_path, args.schema_source_db, students, teachers, assignments)
    credentials = create_auth_db(
        auth_path, students, teachers, assignments, args.general_teacher,
    )
    credentials_path.write_text(json.dumps(credentials, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({
        'campus': CAMPUS_ID,
        'students': len(students),
        'teachers': len(teachers),
        'classTeachers': len(assignments),
        'generalTeachers': len(credentials['generalTeachers']),
        'accounts': len(students) + len(assignments) + len(credentials['generalTeachers']),
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
