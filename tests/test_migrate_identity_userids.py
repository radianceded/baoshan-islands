import json
import sqlite3
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "migrate_identity_userids.py"


def test_migrates_direct_student_guardian_and_dual_role_without_changing_role(tmp_path):
    db_path = tmp_path / "identity.db"
    db = sqlite3.connect(db_path)
    db.executescript(
        """
        CREATE TABLE students_benbu (
            dingtalk_userid TEXT PRIMARY KEY,
            id_card TEXT UNIQUE,
            name TEXT,
            grade_name TEXT,
            class_name TEXT
        );
        CREATE TABLE user_bindings (
            dingtalk_unionid TEXT UNIQUE,
            dingtalk_userid TEXT,
            role TEXT,
            bound_id_card TEXT,
            bound_name TEXT,
            bound_grade TEXT,
            bound_class TEXT
        );
        CREATE TABLE parent_kids (
            id INTEGER PRIMARY KEY,
            union_id TEXT,
            kid_id_card TEXT,
            kid_name TEXT,
            kid_grade TEXT,
            kid_class TEXT,
            campus TEXT,
            is_active INTEGER
        );
        INSERT INTO students_benbu VALUES
          ('STUDENT-1', 'BS-NEW-1', '示例学生丁', '三年级', '5班'),
          ('STUDENT-2', 'BS-NEW-2', '学生乙', '四年级', '2班');
        INSERT INTO user_bindings VALUES
          ('student-union', 'STUDENT-2', 'parent', NULL, '学生乙', NULL, NULL),
          ('teacher-union', 'TEACHER-1', 'teacher', NULL, '班主任', '三年级', '5班');
        INSERT INTO parent_kids VALUES
          (1, 'teacher-union', 'OLD-1', '示例学生丁', '二年级', '5班', 'benbu', 1);
        """
    )
    db.commit()
    db.close()

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), str(db_path), "--apply"],
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(completed.stdout)
    assert summary["resolvedParentKids"] == 1
    assert summary["directStudentAccounts"] == 1

    migrated = sqlite3.connect(db_path)
    assert migrated.execute(
        """SELECT bound_student_userid, bound_id_card
           FROM user_bindings WHERE dingtalk_unionid='student-union'"""
    ).fetchone() == ("STUDENT-2", "BS-NEW-2")
    assert migrated.execute(
        """SELECT role, bound_student_userid, bound_id_card
           FROM user_bindings WHERE dingtalk_unionid='teacher-union'"""
    ).fetchone() == ("teacher", "STUDENT-1", "BS-NEW-1")
    assert migrated.execute(
        """SELECT kid_dingtalk_userid, kid_id_card, kid_grade, kid_class
           FROM parent_kids WHERE id=1"""
    ).fetchone() == ("STUDENT-1", "BS-NEW-1", "三年级", "5班")
    migrated.close()
