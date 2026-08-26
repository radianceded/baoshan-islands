#!/usr/bin/env python3
"""从同步前备份恢复家长意向姓名，并按当前本部名册修复绑定。"""

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


def rows(connection, sql, params=()):
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(sql, params)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("db_path", type=Path)
    parser.add_argument("backup_path", type=Path)
    parser.add_argument("--move-choice-owner", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    backup = sqlite3.connect(args.backup_path)
    backup_rows = rows(
        backup,
        """SELECT id, union_id, kid_id_card, kid_name, kid_grade, kid_class,
                  campus, is_active, bound_at FROM parent_kids""",
    )
    backup.close()
    backup_by_key = {(row["id"], row["union_id"]): row for row in backup_rows}

    db = sqlite3.connect(args.db_path)
    try:
        current_rows = rows(
            db,
            """SELECT id, union_id, kid_id_card, kid_name, kid_grade, kid_class,
                      campus, is_active, bound_at FROM parent_kids""",
        )
        restored = []
        effective = []
        for current in current_rows:
            original = backup_by_key.get((current["id"], current["union_id"]))
            effective_row = original or current
            effective.append(effective_row)
            if original and any(
                current[key] != original[key]
                for key in ("kid_id_card", "kid_name", "kid_grade", "kid_class")
            ):
                restored.append({"current": current, "backup": original})

        students_by_name = {}
        for student in rows(
            db, "SELECT id_card, name, grade_name, class_name FROM students_benbu"
        ):
            students_by_name.setdefault(student["name"], []).append(student)

        repairs = []
        unresolved = []
        for kid in effective:
            if kid.get("campus") != "benbu":
                continue
            candidates = students_by_name.get(kid["kid_name"], [])
            if len(candidates) != 1:
                unresolved.append({"kid": kid, "candidateCount": len(candidates)})
                continue
            target = candidates[0]
            if (kid["kid_id_card"], kid["kid_grade"], kid["kid_class"]) != (
                target["id_card"], target["grade_name"], target["class_name"]
            ):
                repairs.append({"kid": kid, "target": target})

        target_counts = Counter(
            (item["kid"]["union_id"], item["target"]["id_card"])
            for item in repairs
        )
        conflicts = [
            item for item in repairs
            if target_counts[(item["kid"]["union_id"], item["target"]["id_card"])] > 1
        ]
        if conflicts:
            raise ValueError(f"同一家长出现重复目标学生，拒绝修复: {len(conflicts)}")

        moved_choices = {}
        if args.apply:
            db.execute("BEGIN IMMEDIATE")
            for item in restored:
                original = item["backup"]
                db.execute(
                    """UPDATE parent_kids
                       SET kid_id_card=?, kid_name=?, kid_grade=?, kid_class=?,
                           campus=?, is_active=?, bound_at=?
                       WHERE id=? AND union_id=?""",
                    (
                        original["kid_id_card"], original["kid_name"],
                        original["kid_grade"], original["kid_class"],
                        original["campus"], original["is_active"], original["bound_at"],
                        original["id"], original["union_id"],
                    ),
                )
            for item in repairs:
                db.execute(
                    "UPDATE parent_kids SET kid_id_card=? WHERE id=?",
                    (f"repair:{item['kid']['id']}", item["kid"]["id"]),
                )
            for item in repairs:
                target = item["target"]
                db.execute(
                    """UPDATE parent_kids
                       SET kid_id_card=?, kid_name=?, kid_grade=?, kid_class=?
                       WHERE id=?""",
                    (
                        target["id_card"], target["name"], target["grade_name"],
                        target["class_name"], item["kid"]["id"],
                    ),
                )
            db.execute(
                """UPDATE user_bindings
                   SET bound_id_card=(SELECT kid_id_card FROM parent_kids
                                      WHERE union_id=user_bindings.dingtalk_unionid
                                        AND is_active=1 LIMIT 1),
                       bound_grade=(SELECT kid_grade FROM parent_kids
                                    WHERE union_id=user_bindings.dingtalk_unionid
                                      AND is_active=1 LIMIT 1),
                       bound_class=(SELECT kid_class FROM parent_kids
                                    WHERE union_id=user_bindings.dingtalk_unionid
                                      AND is_active=1 LIMIT 1)
                   WHERE role='parent'
                     AND EXISTS(SELECT 1 FROM parent_kids
                                WHERE union_id=user_bindings.dingtalk_unionid
                                  AND is_active=1)"""
            )
            for union_id in args.move_choice_owner:
                kid = db.execute(
                    """SELECT kid_id_card, kid_name, kid_grade, kid_class
                       FROM parent_kids WHERE union_id=? AND is_active=1 LIMIT 1""",
                    (union_id,),
                ).fetchone()
                if not kid:
                    raise ValueError(f"选餐迁移账号没有激活孩子: {union_id}")
                cursor = db.execute(
                    """UPDATE meal_choices
                       SET id_card=?, name=?, grade_name=?, class_name=?
                       WHERE chosen_by=?""",
                    (*kid, f"dt:{union_id}"),
                )
                moved_choices[union_id] = cursor.rowcount
            db.commit()

        print(json.dumps({
            "currentRows": len(current_rows),
            "restoredFromBackup": len(restored),
            "repairable": len(repairs),
            "unresolved": len(unresolved),
            "movedChoiceRows": moved_choices,
            "applied": args.apply,
            "repairSamples": repairs[:5],
        }, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
