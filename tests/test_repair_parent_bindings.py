import sqlite3
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "repair_parent_bindings.py"


def create_schema(db_path):
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE parent_kids (
            id INTEGER, union_id TEXT, kid_id_card TEXT, kid_name TEXT,
            kid_grade TEXT, kid_class TEXT, campus TEXT, is_active INTEGER,
            bound_at TEXT, UNIQUE(union_id, kid_id_card)
        );
        CREATE TABLE students_benbu (
            id_card TEXT, name TEXT, grade_name TEXT, class_name TEXT
        );
        CREATE TABLE user_bindings (
            dingtalk_unionid TEXT, role TEXT, bound_id_card TEXT,
            bound_grade TEXT, bound_class TEXT
        );
        CREATE TABLE meal_choices (
            id_card TEXT, name TEXT, grade_name TEXT, class_name TEXT,
            chosen_by TEXT
        );
        """
    )
    return connection


def test_repairs_binding_by_restored_name_and_moves_owned_choices(tmp_path):
    db_path = tmp_path / "current.db"
    backup_path = tmp_path / "backup.db"
    union_id = "zhou-parent"

    backup = create_schema(backup_path)
    backup.execute(
        "INSERT INTO parent_kids VALUES (1, ?, 'old-id', '示例学生丁', '二年级', '5班', 'benbu', 1, 't')",
        (union_id,),
    )
    backup.commit()
    backup.close()

    current = create_schema(db_path)
    current.execute(
        "INSERT INTO students_benbu VALUES ('new-id', '示例学生丁', '三年级', '5班')"
    )
    current.execute(
        "INSERT INTO parent_kids VALUES (1, ?, 'wrong-id', '傅靖桐', '五年级', '3班', 'benbu', 1, 't')",
        (union_id,),
    )
    current.execute(
        "INSERT INTO user_bindings VALUES (?, 'parent', 'wrong-id', '五年级', '3班')",
        (union_id,),
    )
    current.execute(
        "INSERT INTO meal_choices VALUES ('wrong-id', '傅靖桐', '五年级', '3班', ?)",
        (f"dt:{union_id}",),
    )
    current.commit()
    current.close()

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(db_path),
            str(backup_path),
            "--move-choice-owner",
            union_id,
            "--apply",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    repaired = sqlite3.connect(db_path)
    assert repaired.execute(
        "SELECT kid_id_card, kid_name, kid_grade, kid_class FROM parent_kids"
    ).fetchone() == ("new-id", "示例学生丁", "三年级", "5班")
    assert repaired.execute(
        "SELECT bound_id_card, bound_grade, bound_class FROM user_bindings"
    ).fetchone() == ("new-id", "三年级", "5班")
    assert repaired.execute(
        "SELECT id_card, name, grade_name, class_name FROM meal_choices"
    ).fetchone() == ("new-id", "示例学生丁", "三年级", "5班")
    repaired.close()
