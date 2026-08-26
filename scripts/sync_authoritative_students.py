#!/usr/bin/env python3
"""校验并同步本部权威学生名册 CSV。

CSV 必须由客户提供的家校通讯录导出，包含：
id_card,name,grade_name,class_name。
默认只输出差异；传 --apply 才写入数据库。
"""

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path


EXPECTED_GRADES = {"一年级", "二年级", "三年级", "四年级", "五年级"}


def load_students(path):
    students = {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"id_card", "name", "grade_name", "class_name"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"CSV 缺少字段: {sorted(required)}")
        for line_number, row in enumerate(reader, 2):
            student = {key: (row.get(key) or "").strip() for key in required}
            if not all(student.values()):
                raise ValueError(f"第 {line_number} 行存在空字段")
            if student["grade_name"] not in EXPECTED_GRADES:
                raise ValueError(f"第 {line_number} 行年级无效: {student['grade_name']}")
            if not re.fullmatch(r"\d+班", student["class_name"]):
                raise ValueError(f"第 {line_number} 行班级无效: {student['class_name']}")
            if student["id_card"] in students:
                raise ValueError(f"学生 UserID 重复: {student['id_card']}")
            students[student["id_card"]] = student
    if len(students) < 100:
        raise ValueError(f"学生数量异常，拒绝同步: {len(students)}")
    return students


def current_students(connection):
    rows = connection.execute(
        "SELECT id_card, name, grade_name, class_name FROM students_benbu"
    ).fetchall()
    return {
        row[0]: {
            "id_card": row[0],
            "name": row[1],
            "grade_name": row[2],
            "class_name": row[3],
        }
        for row in rows
    }


def match_students(current, authoritative):
    by_name = {}
    for source in authoritative.values():
        by_name.setdefault(source["name"], []).append(source)
    matches = []
    ambiguous = []
    matched_source_ids = set()
    for internal in current.values():
        candidates = by_name.get(internal["name"], [])
        if len(candidates) > 1:
            candidates = [
                item for item in candidates
                if item["grade_name"] == internal["grade_name"]
                and item["class_name"] == internal["class_name"]
            ]
        if len(candidates) != 1:
            ambiguous.append({"current": internal, "candidateCount": len(candidates)})
            continue
        source = candidates[0]
        if source["id_card"] in matched_source_ids:
            ambiguous.append({"current": internal, "candidateCount": len(candidates)})
            continue
        matched_source_ids.add(source["id_card"])
        matches.append({"internal": internal, "source": source})
    unmatched_source = [
        item for item in authoritative.values()
        if item["id_card"] not in matched_source_ids
    ]
    return matches, ambiguous, unmatched_source


def build_diff(current, authoritative):
    matches, ambiguous, unmatched_source = match_students(current, authoritative)
    changed = []
    for match in matches:
        before = match["internal"]
        source = match["source"]
        after = {
            "id_card": before["id_card"],
            "name": source["name"],
            "grade_name": source["grade_name"],
            "class_name": source["class_name"],
            "source_user_id": source["id_card"],
        }
        if any(before[key] != after[key] for key in ("name", "grade_name", "class_name")):
            changed.append({"before": before, "after": after})
    return {
        "current": len(current),
        "authoritative": len(authoritative),
        "matched": matches,
        "ambiguous": ambiguous,
        "unmatchedSource": unmatched_source,
        "changed": changed,
    }


def apply_students(connection, diff):
    if diff["ambiguous"] or diff["unmatchedSource"]:
        raise ValueError("存在无法唯一匹配的学生，拒绝同步")
    connection.execute("BEGIN IMMEDIATE")
    connection.execute(
        """CREATE TEMP TABLE authoritative_students(
               internal_id TEXT PRIMARY KEY,
               source_user_id TEXT NOT NULL UNIQUE,
               name TEXT NOT NULL,
               grade_name TEXT NOT NULL,
               class_name TEXT NOT NULL
           )"""
    )
    connection.executemany(
        "INSERT INTO authoritative_students VALUES(?, ?, ?, ?, ?)",
        [
            (
                item["internal"]["id_card"],
                item["source"]["id_card"],
                item["source"]["name"],
                item["source"]["grade_name"],
                item["source"]["class_name"],
            )
            for item in diff["matched"]
        ],
    )
    connection.execute(
        """UPDATE students_benbu
           SET name=(SELECT name FROM authoritative_students WHERE internal_id=students_benbu.id_card),
               grade_name=(SELECT grade_name FROM authoritative_students WHERE internal_id=students_benbu.id_card),
               class_name=(SELECT class_name FROM authoritative_students WHERE internal_id=students_benbu.id_card)
           WHERE id_card IN (SELECT internal_id FROM authoritative_students)"""
    )
    connection.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    authoritative = load_students(args.csv_path)
    connection = sqlite3.connect(args.db_path)
    try:
        before = current_students(connection)
        diff = build_diff(before, authoritative)
        summary = {
            "current": diff["current"],
            "authoritative": diff["authoritative"],
            "matched": len(diff["matched"]),
            "ambiguous": len(diff["ambiguous"]),
            "unmatchedSource": len(diff["unmatchedSource"]),
            "changed": len(diff["changed"]),
            "samples": {
                "ambiguous": diff["ambiguous"][:5],
                "unmatchedSource": diff["unmatchedSource"][:5],
                "changed": diff["changed"][:5],
            },
            "applied": args.apply,
        }
        if args.apply:
            apply_students(connection, diff)
            summary["after"] = len(current_students(connection))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
