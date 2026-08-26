#!/usr/bin/env python3
"""把登录身份链从兼容 BS 编号迁移到客户通讯录学生 UserID。"""

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


CAMPUS_TABLES = {
    "benbu": "students_benbu",
    "luojing": "students_luojing",
}


def table_exists(db, table):
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def columns(db, table):
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def add_columns(db):
    user_columns = columns(db, "user_bindings")
    if "bound_student_userid" not in user_columns:
        db.execute("ALTER TABLE user_bindings ADD COLUMN bound_student_userid TEXT")
    if "dingtalk_userid" not in user_columns:
        db.execute("ALTER TABLE user_bindings ADD COLUMN dingtalk_userid TEXT")

    kid_columns = columns(db, "parent_kids")
    if "kid_dingtalk_userid" not in kid_columns:
        db.execute("ALTER TABLE parent_kids ADD COLUMN kid_dingtalk_userid TEXT")


def student_indexes(db):
    indexes = {}
    for campus, table in CAMPUS_TABLES.items():
        if not table_exists(db, table) or "dingtalk_userid" not in columns(db, table):
            continue
        rows = db.execute(
            f"""SELECT dingtalk_userid, id_card, name, grade_name, class_name
                FROM {table}"""
        ).fetchall()
        by_userid = {row[0]: row for row in rows if row[0]}
        by_name = {}
        for row in rows:
            by_name.setdefault(row[2], []).append(row)
        indexes[campus] = {"by_userid": by_userid, "by_name": by_name}
    return indexes


def resolve_student(kid, indexes):
    campus = (kid[6] or "benbu").strip()
    index = indexes.get(campus)
    if not index:
        return None
    if kid[1] and kid[1] in index["by_userid"]:
        return index["by_userid"][kid[1]]
    candidates = index["by_name"].get(kid[3], [])
    exact = [row for row in candidates if row[1] == kid[2]]
    if len(exact) == 1:
        return exact[0]
    return candidates[0] if len(candidates) == 1 else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = sqlite3.connect(args.db_path)
    try:
        if not table_exists(db, "user_bindings") or not table_exists(db, "parent_kids"):
            raise ValueError("缺少 user_bindings 或 parent_kids 表")
        db.execute("BEGIN IMMEDIATE")
        add_columns(db)
        indexes = student_indexes(db)

        kids = db.execute(
            """SELECT id, kid_dingtalk_userid, kid_id_card, kid_name,
                      kid_grade, kid_class, campus, union_id, is_active
               FROM parent_kids"""
        ).fetchall()
        resolved = []
        unresolved = []
        for kid in kids:
            student = resolve_student(kid, indexes)
            if not student:
                unresolved.append({
                    "id": kid[0], "unionId": kid[7], "name": kid[3],
                    "campus": kid[6], "active": bool(kid[8]),
                })
                continue
            resolved.append((kid, student))
            db.execute(
                """UPDATE parent_kids
                   SET kid_dingtalk_userid=?, kid_id_card=?, kid_name=?,
                       kid_grade=?, kid_class=? WHERE id=?""",
                (student[0], student[1], student[2], student[3], student[4], kid[0]),
            )

        direct_accounts = 0
        for campus_index in indexes.values():
            for student_userid, student in campus_index["by_userid"].items():
                cursor = db.execute(
                    """UPDATE user_bindings
                       SET bound_student_userid=?, bound_id_card=?, bound_name=?,
                           bound_grade=?, bound_class=?
                       WHERE role='parent' AND dingtalk_userid=?""",
                    (
                        student_userid, student[1], student[2], student[3], student[4],
                        student_userid,
                    ),
                )
                direct_accounts += cursor.rowcount

        guardian_accounts = db.execute(
            """UPDATE user_bindings
               SET bound_student_userid=(
                       SELECT kid_dingtalk_userid FROM parent_kids
                       WHERE union_id=user_bindings.dingtalk_unionid AND is_active=1 LIMIT 1
                   ),
                   bound_id_card=(
                       SELECT kid_id_card FROM parent_kids
                       WHERE union_id=user_bindings.dingtalk_unionid AND is_active=1 LIMIT 1
                   ),
                   bound_grade=(
                       SELECT kid_grade FROM parent_kids
                       WHERE union_id=user_bindings.dingtalk_unionid AND is_active=1 LIMIT 1
                   ),
                   bound_class=(
                       SELECT kid_class FROM parent_kids
                       WHERE union_id=user_bindings.dingtalk_unionid AND is_active=1 LIMIT 1
                   )
               WHERE EXISTS(
                   SELECT 1 FROM parent_kids
                   WHERE union_id=user_bindings.dingtalk_unionid
                     AND is_active=1 AND kid_dingtalk_userid IS NOT NULL
               )"""
        ).rowcount

        db.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_pk_union_student_userid
               ON parent_kids(union_id, kid_dingtalk_userid)
               WHERE kid_dingtalk_userid IS NOT NULL"""
        )
        if args.apply:
            db.commit()
        else:
            db.rollback()

        binding_unions = {
            row[0] for row in db.execute("SELECT dingtalk_unionid FROM user_bindings")
        }
        unresolved_by_campus = Counter((item["campus"] or "benbu") for item in unresolved)
        print(json.dumps({
            "parentKids": len(kids),
            "resolvedParentKids": len(resolved),
            "unresolvedParentKids": len(unresolved),
            "unresolvedActive": sum(1 for item in unresolved if item["active"]),
            "unresolvedWithLoginAccount": sum(
                1 for item in unresolved if item["unionId"] in binding_unions
            ),
            "unresolvedByCampus": dict(unresolved_by_campus),
            "directStudentAccounts": direct_accounts,
            "accountsLinkedFromGuardianRelation": guardian_accounts,
            "applied": args.apply,
            "unresolvedSamples": unresolved[:10],
        }, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
