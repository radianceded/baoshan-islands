#!/usr/bin/env python3
"""Build a standalone password-auth database from read-only benbu sources."""
from __future__ import annotations

import argparse
import json
import secrets
import sqlite3
import string
from pathlib import Path

from werkzeug.security import generate_password_hash


PASSWORD_ALPHABET = ''.join(
    ch for ch in string.ascii_letters + string.digits if ch not in '0O1Il'
)


def random_password(length: int = 12) -> str:
    return ''.join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def readonly_connection(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-db', type=Path, required=True)
    parser.add_argument('--teacher-source', type=Path, required=True)
    parser.add_argument('--auth-db', type=Path, required=True)
    parser.add_argument('--credentials-json', type=Path, required=True)
    args = parser.parse_args()

    for output in (args.auth_db, args.credentials_json):
        if output.exists():
            raise SystemExit(f'Refusing to overwrite existing output: {output}')
        output.parent.mkdir(parents=True, exist_ok=True)

    teacher_source = json.loads(args.teacher_source.read_text(encoding='utf-8'))
    teachers_by_name: dict[str, dict] = {}
    for teacher in teacher_source['teachers']:
        name = str(teacher['name']).strip()
        if name in teachers_by_name:
            raise SystemExit(f'Duplicate teacher name in source: {name}')
        teachers_by_name[name] = teacher

    source = readonly_connection(args.source_db)
    students = source.execute(
        '''SELECT dingtalk_userid, id_card, name, grade_name, class_name
           FROM students_benbu
           ORDER BY grade_name, class_name, id_card'''
    ).fetchall()
    source.close()
    if not students:
        raise SystemExit('students_benbu is empty')
    student_userids = [str(row['dingtalk_userid'] or '').strip() for row in students]
    if any(not value for value in student_userids):
        raise SystemExit('A benbu student is missing dingtalk_userid')
    if len(set(student_userids)) != len(student_userids):
        raise SystemExit('Duplicate dingtalk_userid found in students_benbu')

    credentials = {'students': [], 'classTeachers': [], 'generalTeachers': []}
    auth = sqlite3.connect(args.auth_db)
    auth.execute('PRAGMA journal_mode=WAL')
    auth.execute('''CREATE TABLE auth_accounts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('parent', 'teacher')),
        sub_role TEXT CHECK(sub_role IS NULL OR sub_role IN ('class', 'general')),
        campus_id TEXT NOT NULL CHECK(campus_id = 'benbu'),
        display_name TEXT NOT NULL,
        bound_student_userid TEXT,
        bound_id_card TEXT,
        bound_grade TEXT,
        bound_class TEXT,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
        auth_version INTEGER NOT NULL DEFAULT 1,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked_until INTEGER,
        last_login_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK(
            (role='parent' AND sub_role IS NULL AND bound_student_userid IS NOT NULL)
            OR
            (role='teacher' AND sub_role='class' AND bound_grade IS NOT NULL AND bound_class IS NOT NULL AND bound_student_userid IS NULL)
            OR
            (role='teacher' AND sub_role='general' AND bound_student_userid IS NULL AND bound_grade IS NULL AND bound_class IS NULL)
        )
    )''')
    auth.execute('CREATE INDEX idx_auth_active_role ON auth_accounts(is_active, role, sub_role)')

    def insert_account(*, username: str, password: str, role: str, sub_role: str | None,
                       display_name: str, student_userid: str | None = None,
                       id_card: str | None = None, grade: str | None = None,
                       class_name: str | None = None) -> None:
        auth.execute(
            '''INSERT INTO auth_accounts(
                   username, password_hash, role, sub_role, campus_id, display_name,
                   bound_student_userid, bound_id_card, bound_grade, bound_class
               ) VALUES (?, ?, ?, ?, 'benbu', ?, ?, ?, ?, ?)''',
            (username, generate_password_hash(password, method='pbkdf2:sha256:100000'), role, sub_role,
             display_name, student_userid, id_card, grade, class_name),
        )

    for row in students:
        password = random_password()
        username = str(row['dingtalk_userid']).strip()
        insert_account(
            username=username, password=password, role='parent', sub_role=None,
            display_name=row['name'], student_userid=username, id_card=row['id_card'],
            grade=row['grade_name'], class_name=row['class_name'],
        )
        credentials['students'].append({
            'campus': '本部', 'grade': row['grade_name'], 'class': row['class_name'],
            'name': row['name'], 'username': username, 'password': password,
        })

    for assignment in teacher_source['classAssignments']:
        teacher_name = str(assignment['teacher']).strip()
        klass = str(assignment['klass']).strip()
        teacher = teachers_by_name.get(teacher_name)
        if not teacher:
            raise SystemExit(f'Class teacher missing from teacher roster: {teacher_name}')
        username = str(teacher['userId']).strip()
        password = random_password()
        grade = f'{klass[0]}年级'
        class_name = f'{klass[1:]}班'
        insert_account(
            username=username, password=password, role='teacher', sub_role='class',
            display_name=teacher_name, grade=grade, class_name=class_name,
        )
        credentials['classTeachers'].append({
            'campus': '本部', 'grade': grade, 'class': class_name,
            'name': teacher_name, 'username': username, 'password': password,
        })

    for teacher_name in teacher_source['generalTeachers']:
        teacher = teachers_by_name.get(teacher_name)
        if not teacher:
            raise SystemExit(f'General teacher missing from teacher roster: {teacher_name}')
        username = str(teacher['userId']).strip()
        password = random_password()
        insert_account(
            username=username, password=password, role='teacher', sub_role='general',
            display_name=teacher_name,
        )
        credentials['generalTeachers'].append({
            'campus': '本部', 'name': teacher_name,
            'username': username, 'password': password,
        })

    auth.commit()
    expected = len(students) + len(teacher_source['classAssignments']) + len(teacher_source['generalTeachers'])
    actual = auth.execute('SELECT COUNT(*) FROM auth_accounts').fetchone()[0]
    if actual != expected:
        raise SystemExit(f'Account count mismatch: expected {expected}, got {actual}')
    auth.close()
    args.credentials_json.write_text(json.dumps(credentials, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({
        'students': len(credentials['students']),
        'classTeachers': len(credentials['classTeachers']),
        'generalTeachers': len(credentials['generalTeachers']),
        'total': actual,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
