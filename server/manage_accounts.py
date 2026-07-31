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
import os, sys, csv, json, sqlite3, hashlib, argparse
from datetime import datetime, timedelta

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

DEMO = [
    {
        'username': 'demo_general',
        'password': '123456',
        'role': 'teacher',
        'sub_role': 'general',
        'display_name': '示例总务老师',
    },
    {
        'username': 'demo_class',
        'password': '123456',
        'role': 'teacher',
        'sub_role': 'class',
        'bound_grade': '三年级',
        'bound_class': '1班',
        'display_name': '示例班主任老师',
    },
    {
        'username': 'demo_parent',
        'password': '123456',
        'role': 'parent',
        'bound_id_card': 'BS_99999',
        'bound_grade': '三年级',
        'bound_class': '1班',
        'kid_name': '示例学生',
        'demo_idx': 0,
        'display_name': '示例学生家长',
    },
]

DEMO_CHILD = {
    'child_code': 'BS_99999',
    'display_name': '示例学生',
    'grade_name': '三年级',
    'class_name': '1班',
    'school_name': '本部校区',
}

DEMO_MEAL_CHOICES = [
    (17, 'odd', 1, 'A'),
    (17, 'odd', 2, 'B'),
    (17, 'odd', 3, 'A'),
    (17, 'odd', 4, 'A'),
    (17, 'odd', 5, 'B'),
    (18, 'even', 1, 'B'),
    (18, 'even', 2, 'B'),
    (18, 'even', 3, 'A'),
    (18, 'even', 4, 'B'),
    (18, 'even', 5, 'A'),
]

DEMO_RECOMMENDATIONS = [
    ('2026-07-27', 0.82, 0.71, 'A', 'A餐营养结构更均衡，适合作为当天首选。'),
    ('2026-07-28', 0.69, 0.84, 'B', 'B餐蛋白质与蔬菜搭配更适合孩子当前需求。'),
    ('2026-07-29', 0.80, 0.72, 'A', 'A餐综合匹配度更高，建议优先选择。'),
    ('2026-07-30', 0.73, 0.86, 'B', 'B餐与孩子当前营养需求更匹配。'),
    ('2026-07-31', 0.83, 0.75, 'A', 'A餐能量与蛋白质搭配更均衡。'),
    ('2026-08-03', 0.76, 0.85, 'B', 'B餐蔬菜和优质蛋白组合更合适。'),
    ('2026-08-04', 0.84, 0.74, 'A', 'A餐综合营养匹配度更高。'),
    ('2026-08-05', 0.71, 0.83, 'B', 'B餐更符合当天的营养补充需要。'),
    ('2026-08-06', 0.86, 0.72, 'A', 'A餐营养结构更适合孩子。'),
    ('2026-08-07', 0.74, 0.82, 'B', 'B餐综合评分更高，建议优先选择。'),
]

DEMO_MEAL_PLANS = [
    ('2026-07-27', 'A', '香菇鸡肉饭', ['香菇鸡肉', '西兰花', '米饭'], 526, 24.6),
    ('2026-07-27', 'B', '番茄牛肉面', ['番茄牛肉', '青菜', '面条'], 548, 22.8),
    ('2026-07-28', 'A', '清蒸鱼套餐', ['清蒸鱼', '炒时蔬', '米饭'], 512, 25.1),
    ('2026-07-28', 'B', '土豆炖牛肉', ['土豆牛肉', '胡萝卜', '米饭'], 559, 26.3),
    ('2026-07-29', 'A', '虾仁豆腐饭', ['虾仁豆腐', '菜心', '米饭'], 503, 23.9),
    ('2026-07-29', 'B', '菌菇鸡丝面', ['菌菇鸡丝', '小青菜', '面条'], 535, 21.7),
    ('2026-07-30', 'A', '彩椒肉片饭', ['彩椒肉片', '冬瓜', '米饭'], 541, 22.6),
    ('2026-07-30', 'B', '鳕鱼蔬菜饭', ['香煎鳕鱼', '杂蔬', '米饭'], 518, 25.8),
    ('2026-07-31', 'A', '萝卜炖排骨', ['萝卜排骨', '菠菜', '米饭'], 552, 24.2),
    ('2026-07-31', 'B', '鸡蛋肉末饭', ['鸡蛋肉末', '西葫芦', '米饭'], 529, 22.4),
    ('2026-08-03', 'A', '黑椒鸡丁饭', ['黑椒鸡丁', '花菜', '米饭'], 544, 23.5),
    ('2026-08-03', 'B', '茄汁鱼排饭', ['茄汁鱼排', '生菜', '米饭'], 521, 25.4),
    ('2026-08-04', 'A', '冬瓜肉丸饭', ['冬瓜肉丸', '油麦菜', '米饭'], 517, 22.9),
    ('2026-08-04', 'B', '香菇牛肉面', ['香菇牛肉', '青菜', '面条'], 553, 24.8),
    ('2026-08-05', 'A', '红烧鸡腿饭', ['红烧鸡腿', '卷心菜', '米饭'], 562, 25.7),
    ('2026-08-05', 'B', '虾仁蔬菜面', ['虾仁', '时令蔬菜', '面条'], 506, 23.6),
    ('2026-08-06', 'A', '肉末蒸蛋饭', ['肉末蒸蛋', '西兰花', '米饭'], 523, 24.1),
    ('2026-08-06', 'B', '咖喱牛肉饭', ['咖喱牛肉', '胡萝卜', '米饭'], 568, 25.2),
    ('2026-08-07', 'A', '清炒虾仁饭', ['清炒虾仁', '菜心', '米饭'], 509, 24.7),
    ('2026-08-07', 'B', '香菇鸡肉面', ['香菇鸡肉', '小青菜', '面条'], 532, 23.8),
]

def seed_demo_child_data(c, nutrition_db_path=None):
    """为 demo_parent 写入可重复执行的孩子推荐和选餐历史。"""
    c.execute('''CREATE TABLE IF NOT EXISTS students(
        id_card TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        gender TEXT,
        birth_date TEXT,
        grade_name TEXT,
        class_name TEXT,
        school_name TEXT DEFAULT '宝山实验小学',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_students_name ON students(name)')
    c.execute(
        '''INSERT INTO students
           (id_card, name, gender, birth_date, grade_name, class_name,
            school_name)
           VALUES (?, ?, NULL, NULL, ?, ?, ?)
           ON CONFLICT(id_card) DO UPDATE SET
             name=excluded.name,
             grade_name=excluded.grade_name,
             class_name=excluded.class_name,
             school_name=excluded.school_name''',
        (
            DEMO_CHILD['child_code'],
            DEMO_CHILD['display_name'],
            DEMO_CHILD['grade_name'],
            DEMO_CHILD['class_name'],
            DEMO_CHILD['school_name'],
        ),
    )
    c.execute('''CREATE TABLE IF NOT EXISTS weekly_menus(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_number INTEGER NOT NULL,
        parity TEXT NOT NULL CHECK(parity IN ('odd','even')),
        date_start TEXT,
        date_end TEXT,
        selection_deadline TEXT,
        image_path TEXT,
        notes TEXT,
        uploaded_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(week_number, parity)
    )''')
    menu_cols = {row[1] for row in c.execute('PRAGMA table_info(weekly_menus)').fetchall()}
    if 'selection_deadline' not in menu_cols:
        c.execute('ALTER TABLE weekly_menus ADD COLUMN selection_deadline TEXT')
    demo_deadline = (
        datetime.now() + timedelta(days=7)
    ).replace(hour=20, minute=0, second=0, microsecond=0).isoformat(timespec='minutes')
    for week, parity, date_start, date_end in (
        (17, 'odd', '2026-07-27', '2026-07-31'),
        (18, 'even', '2026-08-03', '2026-08-07'),
    ):
        c.execute(
            '''INSERT INTO weekly_menus
               (week_number, parity, date_start, date_end, selection_deadline,
                notes, uploaded_by)
               VALUES (?, ?, ?, ?, ?, '本地演示周次', 'demo:seed')
               ON CONFLICT(week_number, parity) DO UPDATE SET
                 date_start=CASE
                   WHEN weekly_menus.date_start IS NULL OR weekly_menus.date_start=''
                   THEN excluded.date_start ELSE weekly_menus.date_start END,
                 date_end=CASE
                   WHEN weekly_menus.date_end IS NULL OR weekly_menus.date_end=''
                   THEN excluded.date_end ELSE weekly_menus.date_end END,
                 selection_deadline=excluded.selection_deadline''',
            (week, parity, date_start, date_end, demo_deadline),
        )
    c.execute('''CREATE TABLE IF NOT EXISTS meal_choices(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_card TEXT NOT NULL,
        name TEXT,
        grade_name TEXT,
        class_name TEXT,
        week_number INTEGER NOT NULL,
        parity TEXT NOT NULL CHECK(parity IN ('odd','even')),
        weekday INTEGER NOT NULL CHECK(weekday BETWEEN 1 AND 5),
        choice TEXT NOT NULL CHECK(choice IN ('A','B')),
        chosen_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(id_card, week_number, parity, weekday) ON CONFLICT REPLACE
    )''')
    c.executemany(
        '''INSERT INTO meal_choices
           (id_card, name, grade_name, class_name, week_number, parity,
            weekday, choice, chosen_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id_card, week_number, parity, weekday) DO UPDATE SET
             name=excluded.name,
             grade_name=excluded.grade_name,
             class_name=excluded.class_name,
             choice=excluded.choice,
             chosen_by=excluded.chosen_by''',
        [
            (
                DEMO_CHILD['child_code'],
                DEMO_CHILD['display_name'],
                DEMO_CHILD['grade_name'],
                DEMO_CHILD['class_name'],
                week,
                parity,
                weekday,
                choice,
                'demo:seed',
            )
            for week, parity, weekday, choice in DEMO_MEAL_CHOICES
        ],
    )
    c.commit()

    nutrition_db_path = nutrition_db_path or os.environ.get(
        'NUTRITION_DB_PATH',
        DB,
    )
    nutrition_conn = sqlite3.connect(nutrition_db_path)
    nutrition_conn.execute('PRAGMA foreign_keys=ON')
    nutrition_conn.executescript('''
        CREATE TABLE IF NOT EXISTS nutrition_children (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_code TEXT UNIQUE NOT NULL,
            display_name TEXT,
            real_name_encrypted TEXT,
            age INTEGER,
            gender TEXT,
            height_cm REAL,
            weight_kg REAL,
            bmi REAL,
            allergies TEXT DEFAULT '[]',
            dietary_restrictions TEXT DEFAULT '[]',
            special_needs TEXT DEFAULT '[]',
            doctor_notes TEXT,
            data_status TEXT DEFAULT 'incomplete',
            data_updated_at TIMESTAMP,
            campus TEXT DEFAULT '本部',
            is_deleted INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS nutrition_meal_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_date DATE NOT NULL,
            plan_type TEXT CHECK(plan_type IN ('A','B')) NOT NULL,
            plan_name TEXT,
            ingredients TEXT DEFAULT '[]',
            calories_kcal REAL,
            protein_g REAL,
            fat_g REAL,
            carbs_g REAL,
            sugar_g REAL,
            sodium_mg REAL,
            fiber_g REAL,
            allergens TEXT DEFAULT '[]',
            suitable_tags TEXT DEFAULT '[]',
            unsuitable_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(plan_date, plan_type)
        );
        CREATE TABLE IF NOT EXISTS nutrition_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL REFERENCES nutrition_children(id),
            plan_date DATE NOT NULL,
            rule_version TEXT NOT NULL,
            score_a REAL,
            score_b REAL,
            recommended_plan TEXT,
            reason TEXT,
            exclusion_reason TEXT,
            risk_notes TEXT,
            confirmed INTEGER DEFAULT 0,
            confirmed_by TEXT,
            confirmed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(child_id, plan_date)
        );
    ''')
    nutrition_conn.execute(
        '''INSERT INTO nutrition_children
           (child_code, display_name, age, height_cm, weight_kg, bmi,
            allergies, dietary_restrictions, special_needs, doctor_notes,
            data_status, data_updated_at, campus, is_deleted)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, 0)
           ON CONFLICT(child_code) DO UPDATE SET
             display_name=excluded.display_name,
             age=excluded.age,
             height_cm=excluded.height_cm,
             weight_kg=excluded.weight_kg,
             bmi=excluded.bmi,
             allergies=excluded.allergies,
             dietary_restrictions=excluded.dietary_restrictions,
             special_needs=excluded.special_needs,
             doctor_notes=excluded.doctor_notes,
             data_status=excluded.data_status,
             data_updated_at=CURRENT_TIMESTAMP,
             campus=excluded.campus,
             is_deleted=0''',
        (
            DEMO_CHILD['child_code'],
            DEMO_CHILD['display_name'],
            9,
            135,
            30,
            16.46,
            '["牛奶"]',
            '[]',
            '[]',
            '演示数据，仅用于本地功能验证。',
            'complete',
            '本部',
        ),
    )
    child_id = nutrition_conn.execute(
        'SELECT id FROM nutrition_children WHERE child_code=?',
        (DEMO_CHILD['child_code'],),
    ).fetchone()[0]
    nutrition_conn.executemany(
        '''INSERT INTO nutrition_meal_plans
           (plan_date, plan_type, plan_name, ingredients, calories_kcal,
            protein_g, allergens, suitable_tags)
           VALUES (?, ?, ?, ?, ?, ?, '[]', '["演示餐食"]')
           ON CONFLICT(plan_date, plan_type) DO UPDATE SET
             plan_name=excluded.plan_name,
             ingredients=excluded.ingredients,
             calories_kcal=excluded.calories_kcal,
             protein_g=excluded.protein_g,
             allergens=excluded.allergens,
             suitable_tags=excluded.suitable_tags''',
        [
            (
                plan_date,
                plan_type,
                plan_name,
                json.dumps(ingredients, ensure_ascii=False),
                calories,
                protein,
            )
            for plan_date, plan_type, plan_name, ingredients, calories, protein
            in DEMO_MEAL_PLANS
        ],
    )
    nutrition_conn.executemany(
        '''INSERT INTO nutrition_recommendations
           (child_id, plan_date, rule_version, score_a, score_b,
            recommended_plan, reason, exclusion_reason, risk_notes, confirmed)
           VALUES (?, ?, 'demo-v1', ?, ?, ?, ?, '', '演示推荐，请勿用于真实配餐决策。', 0)
           ON CONFLICT(child_id, plan_date) DO UPDATE SET
             rule_version=excluded.rule_version,
             score_a=excluded.score_a,
             score_b=excluded.score_b,
             recommended_plan=excluded.recommended_plan,
             reason=excluded.reason,
             exclusion_reason=excluded.exclusion_reason,
             risk_notes=excluded.risk_notes,
             confirmed=0''',
        [
            (child_id, plan_date, score_a, score_b, plan, reason)
            for plan_date, score_a, score_b, plan, reason in DEMO_RECOMMENDATIONS
        ],
    )
    nutrition_conn.commit()
    nutrition_conn.close()
    return {
        'child_code': DEMO_CHILD['child_code'],
        'meal_choices': len(DEMO_MEAL_CHOICES),
        'meal_plans': len(DEMO_MEAL_PLANS),
        'recommendations': len(DEMO_RECOMMENDATIONS),
    }

def cmd_seed(args):
    c = conn()
    for a in DEMO:
        upsert(c, **a)
    seeded = seed_demo_child_data(c)
    c.close()
    print(f'已 upsert {len(DEMO)} 个 demo 账户（统一密码：123456）')
    print(
        f"已为 {seeded['child_code']} 写入 "
        f"{seeded['meal_choices']} 条选餐记录、"
        f"{seeded['meal_plans']} 份餐食数据和 "
        f"{seeded['recommendations']} 条营养推荐"
    )
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
