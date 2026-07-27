#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宝山学习群岛 · 账号管理 CLI

用法：
    # 初始化 demo 账户（首次部署运行）
    python3 server/manage_accounts.py seed-demo

    # 列出所有账号
    python3 server/manage_accounts.py list

    # 添加一条
    python3 server/manage_accounts.py add <username> <password> <role> [选项]
        --sub general|class
        --grade 五年级 --class 1班     （班主任专用）
        --kid 陈思麟                    （家长专用）
        --idCard G310...               （家长专用，链接到 students.id_card）
        --idx 0|1|2|3                  （家长 demo idx，用于 5 个岛的 mock 数据）
        --displayName "五(1)班 王老师"

    # 改密码
    python3 server/manage_accounts.py passwd <username> <new_password>

    # 删除
    python3 server/manage_accounts.py del <username>

    # CSV 批量（生产用）
    #   列：username,password,role,sub_role,bound_id_card,bound_grade,bound_class,kid_name,demo_idx,display_name
    python3 server/manage_accounts.py import accounts.csv
"""
import os, sys, csv, sqlite3, hashlib, argparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, 'student_data.db')

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute('''CREATE TABLE IF NOT EXISTS accounts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        sub_role TEXT,
        bound_id_card TEXT,
        bound_grade TEXT,
        bound_class TEXT,
        kid_name TEXT,
        demo_idx INTEGER,
        display_name TEXT,
        dingtalk_unionid TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.commit()
    return c

def hash_pwd(p):
    return hashlib.sha256(('bs_salt_2026:' + (p or '')).encode()).hexdigest()

def upsert(c, **kw):
    c.execute('''INSERT INTO accounts
        (username, password_hash, role, sub_role, bound_id_card, bound_grade, bound_class, kid_name, demo_idx, display_name)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(username) DO UPDATE SET
            password_hash=excluded.password_hash,
            role=excluded.role,
            sub_role=excluded.sub_role,
            bound_id_card=excluded.bound_id_card,
            bound_grade=excluded.bound_grade,
            bound_class=excluded.bound_class,
            kid_name=excluded.kid_name,
            demo_idx=excluded.demo_idx,
            display_name=excluded.display_name
    ''', (
        kw['username'],
        hash_pwd(kw['password']),
        kw['role'],
        kw.get('sub_role'),
        kw.get('bound_id_card'),
        kw.get('bound_grade'),
        kw.get('bound_class'),
        kw.get('kid_name'),
        kw.get('demo_idx'),
        kw.get('display_name'),
    ))
    c.commit()

DEMO = []

def cmd_seed(args):
    c = conn()
    for a in DEMO:
        upsert(c, **a)
    print(f'✅ 已 upsert {len(DEMO)} 个 demo 账户（统一密码：123456）')
    cmd_list(args)

def cmd_list(args):
    c = conn()
    rows = c.execute('SELECT * FROM accounts ORDER BY role DESC, sub_role, username').fetchall()
    if not rows:
        print('（空）'); return
    print(f'共 {len(rows)} 个账户：')
    print(f"{'用户名':<22} {'role':<8} {'sub':<8} {'绑定':<22} {'显示名':<14}")
    print('-'*80)
    for r in rows:
        bound = r['kid_name'] or r['bound_id_card'] or f"{r['bound_grade'] or ''}{r['bound_class'] or ''}"
        print(f"{r['username']:<22} {r['role']:<8} {(r['sub_role'] or '-'):<8} {(bound or '-'):<22} {r['display_name'] or '':<14}")

def cmd_add(args):
    if len(args) < 3:
        print('用法: add <username> <password> <role:teacher|parent> [选项]'); return
    p = argparse.ArgumentParser()
    p.add_argument('--sub')
    p.add_argument('--grade')
    p.add_argument('--class', dest='klass')
    p.add_argument('--kid')
    p.add_argument('--idCard')
    p.add_argument('--idx', type=int)
    p.add_argument('--displayName')
    a, _ = p.parse_known_args(args[3:])
    upsert(conn(),
        username=args[0], password=args[1], role=args[2],
        sub_role=a.sub, bound_grade=a.grade, bound_class=a.klass,
        kid_name=a.kid, bound_id_card=a.idCard, demo_idx=a.idx,
        display_name=a.displayName or args[0])
    print(f'✅ 已添加 {args[0]}')

def cmd_passwd(args):
    if len(args) < 2: print('用法: passwd <username> <new_password>'); return
    c = conn()
    cur = c.execute('UPDATE accounts SET password_hash=? WHERE username=?', (hash_pwd(args[1]), args[0]))
    c.commit()
    print(f'已改密码 ({cur.rowcount} 行)')

def cmd_del(args):
    if not args: print('用法: del <username>'); return
    c = conn()
    cur = c.execute('DELETE FROM accounts WHERE username=?', (args[0],))
    c.commit()
    print(f'已删除 {cur.rowcount} 行')

def cmd_import(args):
    if not args: print('用法: import <csv>'); return
    path = args[0]
    if not os.path.exists(path): print(f'文件不存在: {path}'); return
    c = conn()
    ok = err = 0
    with open(path, encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            if not row.get('username') or not row.get('password') or not row.get('role'):
                err += 1; continue
            upsert(c,
                username=row['username'], password=row['password'], role=row['role'],
                sub_role=row.get('sub_role') or None,
                bound_id_card=row.get('bound_id_card') or None,
                bound_grade=row.get('bound_grade') or None,
                bound_class=row.get('bound_class') or None,
                kid_name=row.get('kid_name') or None,
                demo_idx=int(row['demo_idx']) if row.get('demo_idx') else None,
                display_name=row.get('display_name') or row['username'])
            ok += 1
    print(f'✅ 导入 {ok} 条，跳过 {err}')

CMDS = {
    'seed-demo': cmd_seed,
    'list': cmd_list,
    'add': cmd_add,
    'passwd': cmd_passwd,
    'del': cmd_del,
    'import': cmd_import,
}

if __name__ == '__main__':
    args = sys.argv[1:]
    if not args or args[0] not in CMDS:
        print(__doc__); sys.exit(0)
    CMDS[args[0]](args[1:])
