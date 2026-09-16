# -*- coding: utf-8 -*-
"""
本部校区独立表建表 + 导入脚本（以最新权威家校/教师通讯录为准）
- students_benbu         : 学生表，主键 dingtalk_userid（钉钉学生 UserID）
- teacher_roster_benbu   : 教师表，主键 dingtalk_userid
- class_teachers_benbu   : 班主任映射（班级 -> 班主任姓名）

家长数据本次不导入（用户指令：家长不要，先放着）。
"""
import os
import re
import sqlite3
import datetime

import xlrd
import openpyxl

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(BASE), "student_data.db")

# 权威文件路径
FAMILY_XLS = os.environ.get('BENBU_FAMILY_XLS', 'private_data/family.xls')
TEACHER_XLSX = os.environ.get('BENBU_TEACHER_XLSX', 'private_data/teachers.xlsx')
CLASS_TEACHER_XLSX = os.environ.get('BENBU_CLASS_TEACHER_XLSX', 'private_data/class-teachers.xlsx')


def parse_grade_class(cls_str):
    """从 '上海市宝山区实验小学-小学-五年级2022级-五年级1班' 解析出 (grade_name, class_name)
    返回形如 ('五年级', '1班')。"""
    if not cls_str:
        return ("", "")
    parts = [p for p in cls_str.split("-") if p]
    last = parts[-1] if parts else cls_str  # '五年级1班'
    m = re.match(r"^(.+?级)\d+班$", last)
    if m:
        grade = m.group(1)  # '五年级'
        cls_num = last[len(grade):]  # '1班'
        return (grade, cls_num)
    # 兜底
    m2 = re.match(r"^(.+?)(\d+班)$", last)
    if m2:
        return (m2.group(1), m2.group(2))
    return (last, "")


def create_tables(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS students_benbu (
            dingtalk_userid TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            school_no       TEXT,
            grade_name      TEXT,
            class_name      TEXT,
            full_class      TEXT,
            student_phone   TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS teacher_roster_benbu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dingtalk_userid TEXT,
            name TEXT,
            mobile TEXT,
            department TEXT,
            position TEXT,
            campus TEXT DEFAULT 'benbu',
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(dingtalk_userid)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS class_teachers_benbu (
            class_name   TEXT,
            grade_name   TEXT,
            teacher_name TEXT,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (grade_name, class_name)
        )
    """)
    conn.commit()


def import_students(conn):
    wb = xlrd.open_workbook(FAMILY_XLS)
    sh = wb.sheet_by_name("学生信息表1")
    cur = conn.cursor()
    cnt = 0
    for r in range(3, sh.nrows):
        uid = str(sh.cell_value(r, 0)).strip()
        name = str(sh.cell_value(r, 1)).strip()
        phone = str(sh.cell_value(r, 2)).strip()
        cls = str(sh.cell_value(r, 3)).strip()
        xh = str(sh.cell_value(r, 4)).strip()
        if not uid:
            continue
        grade, cls_name = parse_grade_class(cls)
        cur.execute(
            "INSERT OR REPLACE INTO students_benbu "
            "(dingtalk_userid, name, school_no, grade_name, class_name, full_class, student_phone) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, name, xh or None, grade or None, cls_name or None, cls or None, phone or None),
        )
        cnt += 1
    conn.commit()
    return cnt


def import_teachers(conn):
    wb = openpyxl.load_workbook(TEACHER_XLSX, read_only=True, data_only=True)
    ws = wb["员工信息表1"]
    cur = conn.cursor()
    cnt = 0
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < 3:  # 跳过 3 行表头
            continue
        uid = str(row[0]).strip() if row[0] is not None else ""
        name = str(row[1]).strip() if row[1] is not None else ""
        mobile = str(row[2]).strip() if row[2] is not None else ""
        dept = str(row[8]).strip() if len(row) > 8 and row[8] is not None else ""  # 办公地点/备注，暂无部门列
        if not uid or not name:
            continue
        cur.execute(
            "INSERT OR REPLACE INTO teacher_roster_benbu "
            "(dingtalk_userid, name, mobile, department, position, campus, is_admin) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, name, mobile or None, dept or None, None, "benbu", 0),
        )
        cnt += 1
    conn.commit()
    return cnt


def import_class_teachers(conn):
    wb = openpyxl.load_workbook(CLASS_TEACHER_XLSX, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    cur = conn.cursor()
    cnt = 0
    grade_map = {"一": "一年级", "二": "二年级", "三": "三年级", "四": "四年级", "五": "五年级", "六": "六年级"}
    # 遍历所有行，找到所有"班级行"（含 '一1' 等），其下一行即班主任行
    for i, row in enumerate(rows):
        vals = [str(v).strip() if v is not None else "" for v in row]
        if not any(re.match(r"^[一二三四五六]+\d+$", v) for v in vals):
            continue
        classes = row
        # 班主任行 = 下一行
        if i + 1 >= len(rows):
            continue
        teacher_row = rows[i + 1]
        teacher_vals = [str(v).strip() if v is not None else "" for v in teacher_row]
        if teacher_vals and teacher_vals[0] != "班主任":
            continue
        for c_idx in range(1, len(classes)):
            cls_raw = classes[c_idx]
            if cls_raw is None:
                continue
            cls_name = str(cls_raw).strip()
            if not re.match(r"^[一二三四五六]+\d+$", cls_name):
                continue
            teacher = teacher_row[c_idx]
            teacher_name = str(teacher).strip() if teacher is not None else ""
            grade_ch = cls_name[0]
            grade_name = grade_map.get(grade_ch, "")
            cls_num = cls_name[1:]
            class_name = f"{cls_num}班"
            cur.execute(
                "INSERT OR REPLACE INTO class_teachers_benbu (class_name, grade_name, teacher_name) VALUES (?,?,?)",
                (class_name, grade_name, teacher_name),
            )
            cnt += 1
    conn.commit()
    return cnt


def main():
    conn = sqlite3.connect(DB_PATH)
    print(f"[1/4] 创建本部门独立表...")
    create_tables(conn)

    print("[2/4] 导入学生（家校通讯录）...")
    n_stu = import_students(conn)
    print(f"      导入学生 {n_stu} 人")

    print("[3/4] 导入教师（通讯录）...")
    n_tch = import_teachers(conn)
    print(f"      导入教师 {n_tch} 人")

    print("[4/4] 导入班主任映射...")
    n_ct = import_class_teachers(conn)
    print(f"      导入班主任映射 {n_ct} 条")

    # 汇总
    cur = conn.cursor()
    print("\n===== 结果汇总 =====")
    for t in ["students_benbu", "teacher_roster_benbu", "class_teachers_benbu"]:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"  {t}: {cur.fetchone()[0]} 行")

    conn.close()
    print("\n完成。")


if __name__ == "__main__":
    main()
