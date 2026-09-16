#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宝小学生画像 · 钉钉账号 ↔ 学生 / 班级 绑定管理工具

用法：
    # 列出当前所有绑定
    python3 server/manage_bindings.py list

    # 添加一条家长绑定（钉钉 unionId → 学生学籍号）
    python3 server/manage_bindings.py add-parent <unionId> <id_card> [显示姓名]

    # 添加一条班主任绑定（钉钉 unionId → 年级班级）
    python3 server/manage_bindings.py add-teacher-class <unionId> <年级> <班级> [显示姓名]

    # 添加一条总务老师绑定（钉钉 unionId → 总务身份）
    python3 server/manage_bindings.py add-teacher-general <unionId> [显示姓名]

    # 删除某个 unionId 的绑定
    python3 server/manage_bindings.py del <unionId>

    # 从 CSV 批量导入（家长版）
    #   CSV 列：unionId,id_card,bound_name
    python3 server/manage_bindings.py import-parents <csv 路径>

    # 从 CSV 批量导入（班主任版）
    #   CSV 列：unionId,grade,class,bound_name
    python3 server/manage_bindings.py import-class-teachers <csv 路径>

    # 清空所有绑定（谨慎！）
    python3 server/manage_bindings.py clear --yes
"""
import os, sys, csv, sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'student_data.db')

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE IF NOT EXISTS user_bindings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dingtalk_unionid TEXT UNIQUE,
        role TEXT NOT NULL DEFAULT 'teacher',
        sub_role TEXT,
        bound_id_card TEXT,
        bound_grade TEXT,
        bound_class TEXT,
        bound_name TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    # 兼容旧库
    cols = {r[1] for r in conn.execute('PRAGMA table_info(user_bindings)').fetchall()}
    for col, typ in [('sub_role','TEXT'),('bound_grade','TEXT'),('bound_class','TEXT')]:
        if col not in cols:
            conn.execute(f'ALTER TABLE user_bindings ADD COLUMN {col} {typ}')
    conn.commit()
    return conn

def cmd_list(_):
    conn = db()
    rows = conn.execute('SELECT * FROM user_bindings ORDER BY role, sub_role, bound_grade, bound_class, bound_name').fetchall()
    if not rows:
        print('（空）')
        return
    print(f'共 {len(rows)} 条：\n')
    print(f"{'#':>3} {'role':<8} {'sub':<8} {'unionId':<32} {'绑定':<20} {'姓名':<10}")
    print('-'*90)
    for r in rows:
        bound = r['bound_id_card'] or (f"{r['bound_grade'] or ''}{r['bound_class'] or ''}")
        print(f"{r['id']:>3} {r['role']:<8} {r['sub_role'] or '-':<8} {(r['dingtalk_unionid'] or '')[:30]:<32} {bound:<20} {r['bound_name'] or '':<10}")

def _upsert(conn, *, union_id, role, sub_role=None, bound_id_card=None, bound_grade=None, bound_class=None, bound_name=''):
    conn.execute('''INSERT INTO user_bindings(dingtalk_unionid, role, sub_role, bound_id_card, bound_grade, bound_class, bound_name)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(dingtalk_unionid) DO UPDATE SET
            role=excluded.role,
            sub_role=excluded.sub_role,
            bound_id_card=excluded.bound_id_card,
            bound_grade=excluded.bound_grade,
            bound_class=excluded.bound_class,
            bound_name=excluded.bound_name
    ''', (union_id, role, sub_role, bound_id_card, bound_grade, bound_class, bound_name))
    conn.commit()

def cmd_add_parent(args):
    if len(args) < 2:
        print('用法: add-parent <unionId> <id_card> [显示姓名]'); return
    union_id, id_card = args[0], args[1]
    name = args[2] if len(args) > 2 else ''
    conn = db()
    # 校验 id_card 在 students 表里
    s = conn.execute('SELECT name FROM students WHERE id_card=?', (id_card,)).fetchone()
    if not s:
        print(f'⚠️ 学籍号 {id_card} 不在 students 表里，仍然写入但请确认无误')
    elif not name:
        name = s['name']
    _upsert(conn, union_id=union_id, role='parent', bound_id_card=id_card, bound_name=name)
    print(f'✅ 已绑定家长 {union_id} → {id_card} ({name})')

def cmd_add_teacher_class(args):
    if len(args) < 3:
        print('用法: add-teacher-class <unionId> <年级> <班级> [显示姓名]'); return
    union_id, grade, klass = args[0], args[1], args[2]
    name = args[3] if len(args) > 3 else ''
    conn = db()
    cnt = conn.execute('SELECT COUNT(*) FROM students WHERE grade_name=? AND class_name=?', (grade, klass)).fetchone()[0]
    print(f'  · {grade} {klass} 有 {cnt} 名学生在档' + ('（注意 0 人）' if cnt == 0 else ''))
    _upsert(conn, union_id=union_id, role='teacher', sub_role='class',
            bound_grade=grade, bound_class=klass, bound_name=name)
    print(f'✅ 已绑定班主任 {union_id} → {grade} {klass} ({name})')

def cmd_add_teacher_general(args):
    if not args:
        print('用法: add-teacher-general <unionId> [显示姓名]'); return
    union_id = args[0]
    name = args[1] if len(args) > 1 else ''
    conn = db()
    _upsert(conn, union_id=union_id, role='teacher', sub_role='general', bound_name=name)
    print(f'✅ 已绑定总务老师 {union_id} ({name})')

def cmd_del(args):
    if not args:
        print('用法: del <unionId>'); return
    union_id = args[0]
    conn = db()
    cur = conn.execute('DELETE FROM user_bindings WHERE dingtalk_unionid=?', (union_id,))
    conn.commit()
    print(f'已删除 {cur.rowcount} 条记录')

def cmd_import_parents(args):
    if not args:
        print('用法: import-parents <csv 路径>'); return
    path = args[0]
    if not os.path.exists(path):
        print(f'文件不存在: {path}'); return
    conn = db()
    ok = miss = err = 0
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            union_id = (row.get('unionId') or row.get('union_id') or '').strip()
            id_card = (row.get('id_card') or row.get('学籍号') or '').strip()
            name = (row.get('bound_name') or row.get('姓名') or '').strip()
            if not union_id or not id_card:
                err += 1; continue
            s = conn.execute('SELECT name FROM students WHERE id_card=?', (id_card,)).fetchone()
            if not s:
                miss += 1
            if not name and s:
                name = s['name']
            _upsert(conn, union_id=union_id, role='parent', bound_id_card=id_card, bound_name=name)
            ok += 1
    print(f'✅ 导入完成：成功 {ok} 条；学籍号库里查无 {miss} 条；缺字段跳过 {err} 条')

def cmd_import_class_teachers(args):
    if not args:
        print('用法: import-class-teachers <csv 路径>'); return
    path = args[0]
    if not os.path.exists(path):
        print(f'文件不存在: {path}'); return
    conn = db()
    ok = err = 0
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            union_id = (row.get('unionId') or row.get('union_id') or '').strip()
            grade = (row.get('grade') or row.get('年级') or '').strip()
            klass = (row.get('class') or row.get('班级') or '').strip()
            name = (row.get('bound_name') or row.get('姓名') or '').strip()
            if not union_id or not grade or not klass:
                err += 1; continue
            _upsert(conn, union_id=union_id, role='teacher', sub_role='class',
                    bound_grade=grade, bound_class=klass, bound_name=name)
            ok += 1
    print(f'✅ 导入完成：成功 {ok} 条；缺字段跳过 {err} 条')

def cmd_clear(args):
    if '--yes' not in args:
        print('要清空所有绑定，请加 --yes 确认'); return
    conn = db()
    cur = conn.execute('DELETE FROM user_bindings')
    conn.commit()
    print(f'已清空 {cur.rowcount} 条记录')

COMMANDS = {
    'list': cmd_list,
    'add-parent': cmd_add_parent,
    'add-teacher-class': cmd_add_teacher_class,
    'add-teacher-general': cmd_add_teacher_general,
    'del': cmd_del,
    'import-parents': cmd_import_parents,
    'import-class-teachers': cmd_import_class_teachers,
    'clear': cmd_clear,
}

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(0)
    COMMANDS[sys.argv[1]](sys.argv[2:])
