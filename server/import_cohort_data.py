#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性把"学生数字画像/"下三-1 cohort 全部相关数据灌进 student_data.db

涉及表:
  students         — 主档（按 (name, grade, class) 找不到时合成 id_card 插入）
  vision_tests     — 屈光 (2023 / 2024.06 / 2024.11 / 2025.4 / 2025.9)
  physical_exams   — 体检 (2023)         新增表
  fitness_tests    — 体测 (2023/2024/2025)
  clubs            — 25年3年级 社团
  awards           — 2025 学年 综合学科赛事

所有数据按 (id_card 优先 → name+grade+class 兜底) 与 award_certs 链路对齐。
"""
import os, sys, re, sqlite3
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, 'student_data.db')
ROOT = os.path.join(BASE, '学生数字画像')

import openpyxl
try:
    import xlrd
except ImportError:
    xlrd = None

# ─────────── 通用工具 ───────────
CN2NUM = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
GRADE_CODE = {'11':'一年级','12':'二年级','13':'三年级','14':'四年级','15':'五年级','16':'六年级'}

def norm_grade(v):
    if v is None: return ''
    s = str(v).strip().replace('小学','')
    if s in GRADE_CODE: return GRADE_CODE[s]
    if not s: return ''
    if s.endswith('年级'): return s
    if s in CN2NUM: return s + '年级'
    if s.isdigit():
        return GRADE_CODE.get(s) or s + '年级'
    return s

def norm_class(v):
    if v is None: return ''
    s = str(v).strip()
    if s.endswith('.0'): s = s[:-2]
    m = re.search(r'(\d+)\s*班', s)
    if m: return f'{int(m.group(1))}班'
    m = re.search(r'([一二三四五六七八九十])\s*班', s)
    if m: return f'{CN2NUM[m.group(1)]}班'
    if s.isdigit(): return f'{int(s)}班'
    return s

def clean_id_card(v):
    if v is None: return None
    s = str(v).strip().lstrip("'").lstrip('=')
    return s or None

def to_iso_date(v):
    if v is None or v == '': return None
    if isinstance(v, datetime):
        return v.strftime('%Y-%m-%d')
    if isinstance(v, (int, float)):
        # Excel serial date — origin 1899-12-30
        try:
            d = datetime(1899, 12, 30) + timedelta(days=float(v))
            return d.strftime('%Y-%m-%d')
        except Exception:
            return None
    s = str(v).strip()
    if not s: return None
    return s

def f(v):
    """to float or None"""
    if v is None or v == '': return None
    if isinstance(v, (int, float)): return float(v)
    try: return float(str(v).strip())
    except Exception: return None

def t(v):
    if v is None: return None
    s = str(v).strip()
    return s or None

# ─────────── 打开 Excel 抽象 ───────────
def load_sheets(path):
    """yield (sheet_name, list_of_rows_as_lists)"""
    if path.endswith('.xls'):
        if not xlrd:
            raise RuntimeError('xlrd missing')
        wb = xlrd.open_workbook(path)
        for sn in wb.sheet_names():
            ws = wb.sheet_by_name(sn)
            rows = [[ws.cell_value(i,j) for j in range(ws.ncols)] for i in range(ws.nrows)]
            yield sn, rows
    else:
        wb = openpyxl.load_workbook(path, data_only=True)
        for sn in wb.sheetnames:
            ws = wb[sn]
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            yield sn, rows

# ─────────── DB 设置 ───────────
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
cur = db.cursor()

# 确保 vision_tests 表带所有列（沿用上次扩展）
vision_cols = {r[1] for r in cur.execute('PRAGMA table_info(vision_tests)').fetchall()}
for col, typ in [
    ('name','TEXT'),('school_name','TEXT'),('grade_name','TEXT'),('class_name','TEXT'),
    ('gender','TEXT'),('birth_date','TEXT'),('glasses_type','TEXT'),('glasses_other','TEXT'),
    ('right_naked_acuity','REAL'),('left_naked_acuity','REAL'),
    ('right_corrected_acuity','REAL'),('left_corrected_acuity','REAL'),
    ('right_cyl','REAL'),('left_cyl','REAL'),
    ('right_axis','REAL'),('left_axis','REAL'),
    ('right_kh','REAL'),('left_kh','REAL'),('right_kv','REAL'),('left_kv','REAL'),
    ('right_al','REAL'),('left_al','REAL'),('doctor_advice','TEXT'),
]:
    if col not in vision_cols:
        cur.execute(f'ALTER TABLE vision_tests ADD COLUMN {col} {typ}')

# 体检
cur.execute('''CREATE TABLE IF NOT EXISTS physical_exams(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_card TEXT, name TEXT, grade_name TEXT, class_name TEXT,
    school_name TEXT, hospital TEXT, exam_year INTEGER, exam_date TEXT,
    height REAL, weight REAL, bmi REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(id_card, exam_year)
)''')

# fitness_tests 已存在
# clubs/awards 已存在

# ─────────── 学生表查找 / 合成 ───────────
synth_seq = {}
def upsert_student(name, grade, klass, id_card=None, gender=None, birth_date=None, school='宝山实验小学'):
    if not name: return None
    name = str(name).strip()
    grade = norm_grade(grade); klass = norm_class(klass)
    # 1) 真实 id_card 直接 hit
    if id_card:
        idc = clean_id_card(id_card)
        if idc:
            r = cur.execute('SELECT id_card FROM students WHERE id_card=?', (idc,)).fetchone()
            if r:
                # 补全可能缺的 grade/class/gender/birth_date
                cur.execute('''UPDATE students SET
                    name=COALESCE(NULLIF(?,''), name),
                    grade_name=COALESCE(NULLIF(?,''), grade_name),
                    class_name=COALESCE(NULLIF(?,''), class_name),
                    gender=COALESCE(NULLIF(?,''), gender),
                    birth_date=COALESCE(NULLIF(?,''), birth_date)
                    WHERE id_card=?''',
                    (name, grade, klass, t(gender) or '', t(birth_date) or '', idc))
                return idc
            # 新插入
            cur.execute('''INSERT INTO students (id_card, name, gender, birth_date, grade_name, class_name, school_name, created_at)
                           VALUES (?,?,?,?,?,?,?,datetime('now'))''',
                        (idc, name, t(gender), t(birth_date), grade, klass, school))
            return idc
    # 2) 按 (name, grade, class) 查
    r = cur.execute('SELECT id_card FROM students WHERE name=? AND grade_name=? AND class_name=?',
                    (name, grade, klass)).fetchone()
    if r: return r['id_card']
    # 3) 兜底：按 (name, class) 查（grade 可能跨学年不同）
    r = cur.execute("SELECT id_card FROM students WHERE name=? AND class_name=? AND grade_name LIKE '%年级'",
                    (name, klass)).fetchone()
    if r: return r['id_card']
    # 4) 合成
    key = klass or 'unk'
    synth_seq[key] = synth_seq.get(key, 0) + 1
    prefix = re.sub(r'年级$', '', grade) or '?'
    idc = f'SYN_{prefix}{klass.replace("班","")}_{synth_seq[key]:03d}_{name}'
    cur.execute('''INSERT INTO students (id_card, name, gender, birth_date, grade_name, class_name, school_name, created_at)
                   VALUES (?,?,?,?,?,?,?,datetime('now'))''',
                (idc, name, t(gender), t(birth_date), grade, klass, school))
    return idc

# ─────────── 各导入函数 ───────────
def header_index(headers):
    return {h:i for i,h in enumerate(headers) if h is not None}

def col(row, idx, key):
    i = idx.get(key)
    if i is None or i >= len(row): return None
    return row[i]

# ─── 屈光 ───
VISION_FILES = [
    ('学生数字画像/ai推送运动和早晚餐建议/2023一1班屈光数据.xlsx', None),
    ('学生数字画像/ai推送运动和早晚餐建议/2024.06一1班屈光数据.xlsx', None),
    ('学生数字画像/ai推送运动和早晚餐建议/2024.11二一班屈光数据.xls', None),
    ('学生数字画像/ai推送运动和早晚餐建议/2025.4二1屈光数据.xlsx', None),
]

def import_vision(path):
    n = 0
    full = os.path.join(BASE, path)
    for sn, rows in load_sheets(full):
        if not rows: continue
        headers = rows[0]
        idx = header_index(headers)
        for row in rows[1:]:
            name = t(col(row, idx, '姓名'))
            if not name: continue
            id_card_raw = col(row, idx, '证件号码') or col(row, idx, '学籍号')
            grade = norm_grade(col(row, idx, '年级'))
            klass = norm_class(col(row, idx, '班级'))
            gender = col(row, idx, '性别')
            birth = to_iso_date(col(row, idx, '出生日期'))
            school = t(col(row, idx, '学校')) or '宝山实验小学'

            idc = upsert_student(name, grade, klass, id_card=id_card_raw,
                                 gender=gender, birth_date=birth, school=school)
            if not idc: continue
            test_date = to_iso_date(col(row, idx, '建档日期')) or to_iso_date(col(row, idx, '检查日期'))
            if not test_date: continue
            # 去重（同 id_card + 同 test_date）
            cur.execute('DELETE FROM vision_tests WHERE id_card=? AND test_date=?', (idc, test_date))
            cur.execute('''INSERT INTO vision_tests (
                id_card, test_date, test_grade, created_at,
                name, school_name, grade_name, class_name, gender, birth_date,
                glasses_type, glasses_other,
                right_naked_acuity, left_naked_acuity,
                right_corrected_acuity, left_corrected_acuity,
                right_sph, left_sph, right_cyl, left_cyl,
                right_axis, left_axis,
                right_kh, left_kh, right_kv, left_kv,
                right_al, left_al, doctor_advice
            ) VALUES (?,?,?,datetime('now'), ?,?,?,?,?,?, ?,?, ?,?, ?,?, ?,?, ?,?, ?,?, ?,?, ?,?, ?,?, ?)''', (
                idc, test_date, grade,
                name, school, grade, klass, t(gender), birth,
                t(col(row, idx, '初筛戴镜方式')), t(col(row, idx, '初筛其他戴镜方式')),
                f(col(row, idx, '初筛右眼裸眼视力')), f(col(row, idx, '初筛左眼裸眼视力')),
                f(col(row, idx, '初筛右眼戴镜视力')), f(col(row, idx, '初筛左眼戴镜视力')),
                f(col(row, idx, '初筛右眼球镜')), f(col(row, idx, '初筛左眼球镜')),
                f(col(row, idx, '初筛右眼柱镜')), f(col(row, idx, '初筛左眼柱镜')),
                f(col(row, idx, '右眼轴位散光方向')), f(col(row, idx, '左眼轴位散光方向')),
                f(col(row, idx, '初筛右眼角膜曲率H')), f(col(row, idx, '初筛左眼角膜曲率H')),
                f(col(row, idx, '初筛右眼角膜曲率V')), f(col(row, idx, '初筛左眼角膜曲率V')),
                f(col(row, idx, '初筛右眼眼轴长度')), f(col(row, idx, '初筛左眼眼轴长度')),
                t(col(row, idx, '医生建议')),
            ))
            n += 1
    return n

# ─── 体检 (2023) ───
def import_physical(path, exam_year):
    full = os.path.join(BASE, path)
    n = 0
    for sn, rows in load_sheets(full):
        if not rows: continue
        headers = rows[0]; idx = header_index(headers)
        for row in rows[1:]:
            name = t(col(row, idx, '姓名'))
            if not name: continue
            grade = norm_grade(col(row, idx, '年级'))
            klass = norm_class(col(row, idx, '班级'))
            school = t(col(row, idx, '学校')) or '宝山实验小学'
            idc = upsert_student(name, grade, klass, school=school)
            if not idc: continue
            height = f(col(row, idx, '身高(cm)') or col(row, idx, '身高'))
            weight = f(col(row, idx, '体重(Kg)') or col(row, idx, '体重'))
            bmi = f(col(row, idx, '体重指数') or col(row, idx, 'BMI'))
            hospital = t(col(row, idx, '体检医院'))
            cur.execute('DELETE FROM physical_exams WHERE id_card=? AND exam_year=?', (idc, exam_year))
            cur.execute('''INSERT INTO physical_exams (id_card, name, grade_name, class_name, school_name,
                            hospital, exam_year, exam_date, height, weight, bmi, created_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))''',
                        (idc, name, grade, klass, school, hospital, exam_year, f'{exam_year}-01-01',
                         height, weight, bmi))
            n += 1
    return n

# ─── 体测 ───
def import_fitness(path, test_year):
    full = os.path.join(BASE, path)
    n = 0
    for sn, rows in load_sheets(full):
        if not rows: continue
        headers = rows[0]; idx = header_index(headers)
        for row in rows[1:]:
            name = t(col(row, idx, '姓名'))
            if not name: continue
            id_card_raw = col(row, idx, '学籍号')
            grade = norm_grade(col(row, idx, '年级名称') or col(row, idx, '年级编号'))
            klass = norm_class(col(row, idx, '班级名称') or col(row, idx, '班级编号'))
            birth = to_iso_date(col(row, idx, '出生日期'))
            gender = col(row, idx, '性别')
            idc = upsert_student(name, grade, klass, id_card=id_card_raw, gender=gender, birth_date=birth)
            if not idc: continue
            cur.execute('DELETE FROM fitness_tests WHERE id_card=? AND test_year=?', (idc, test_year))
            cur.execute('''INSERT INTO fitness_tests (id_card, test_year, height, weight, bmi, bmi_level,
                            vital_capacity, vital_level, run_50m, run_50m_level,
                            sit_reach, sit_reach_level, jump_stand, jump_stand_level,
                            jump_rope, jump_rope_level, sit_up, sit_up_level,
                            total_score, total_level, created_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))''', (
                idc, test_year,
                f(col(row, idx, '身高')), f(col(row, idx, '体重')), f(col(row, idx, 'BMI')),
                t(col(row, idx, 'BMI等级')),
                f(col(row, idx, '肺活量')), t(col(row, idx, '肺活量等级')),
                f(col(row, idx, '50米跑')), t(col(row, idx, '50米跑等级')),
                f(col(row, idx, '坐位体前屈')), t(col(row, idx, '坐位体前屈等级')),
                f(col(row, idx, '立定跳远')), t(col(row, idx, '立定跳远等级')),
                f(col(row, idx, '一分钟跳绳')), t(col(row, idx, '一分钟跳绳等级')),
                f(col(row, idx, '一分钟仰卧起坐')), t(col(row, idx, '一分钟仰卧起坐等级')),
                f(col(row, idx, '总分')), t(col(row, idx, '总分等级')),
            ))
            n += 1
    return n

# ─── 社团 ───
def import_clubs(path, school_year):
    full = os.path.join(BASE, path)
    # 该文件按 班 分 sheet
    cur.execute("DELETE FROM clubs WHERE school_year=?", (school_year,))
    n = 0
    for sn, rows in load_sheets(full):
        if not rows: continue
        headers = rows[0]; idx = header_index(headers)
        for row in rows[1:]:
            name = t(col(row, idx, '学生姓名'))
            if not name: continue
            grade_raw = t(col(row, idx, '年级')) or ''     # 2022级
            # 2022 级 → 现在三年级
            grade = '三年级' if '2022' in grade_raw else norm_grade(grade_raw)
            klass = norm_class(col(row, idx, '班级'))
            club_name = t(col(row, idx, '拓展课名称'))
            teacher = t(col(row, idx, '上课教师'))
            location = t(col(row, idx, '上课地点'))
            # 关联 id_card（按 name+grade+class）
            idc = upsert_student(name, grade, klass)
            cur.execute('''INSERT INTO clubs (student_name, grade, class_name, club_name, teacher, location, school_year, created_at)
                           VALUES (?,?,?,?,?,?,?,datetime('now'))''',
                        (name, grade, klass, club_name, teacher, location, school_year))
            n += 1
    return n

# ─── 综合学科赛事 awards ───
def import_subject_awards(path, source_year):
    full = os.path.join(BASE, path)
    cur.execute("DELETE FROM awards WHERE source_sheet LIKE ?", (f'{source_year}_%',))
    n = 0
    for sn, rows in load_sheets(full):
        # 该文件第 0 行通常是标题（如"体育条线赛事"），第 1 行才是表头
        # 找包含 '姓名' 的那一行
        header_row = -1
        for i, r in enumerate(rows[:5]):
            if r and '姓名' in [str(x) for x in r if x is not None]:
                header_row = i; break
        if header_row < 0: continue
        headers = rows[header_row]
        idx = header_index(headers)
        for row in rows[header_row+1:]:
            name = t(col(row, idx, '姓名'))
            if not name: continue
            klass = norm_class(col(row, idx, '班级'))
            comp = t(col(row, idx, '赛事活动'))
            prize = t(col(row, idx, '状态/获奖情况'))
            teacher = t(col(row, idx, '班主任'))
            remark = t(col(row, idx, '备注'))
            cur.execute('''INSERT INTO awards (name, class_name, competition, prize, subject, teacher, remark, source_sheet, created_at)
                           VALUES (?,?,?,?,?,?,?,?,datetime('now'))''',
                        (name, klass, comp, prize, sn, teacher, remark, f'{source_year}_{sn}'))
            n += 1
    return n


# ─────────── 执行 ───────────
report = {}

for p, _ in VISION_FILES:
    label = os.path.basename(p)
    try:
        report[f'屈光·{label}'] = import_vision(p)
    except Exception as e:
        report[f'屈光·{label}'] = f'ERR: {e}'

report['体检·2023一1班'] = import_physical('学生数字画像/ai推送运动和早晚餐建议/2023一1班体检.xlsx', 2023)

for yr in (2023, 2024, 2025):
    p = f'学生数字画像/ai推送运动和早晚餐建议/2023-2025体质测试/{yr}体测等第成绩导出.xlsx'
    report[f'体测·{yr}'] = import_fitness(p, yr)

report['社团·25年3年级'] = import_clubs('学生数字画像/学生数字画像/学生参加社团/25年3年级.xlsx', '2025-3年级')
report['赛事·2025学年S1'] = import_subject_awards('学生数字画像/学生数字画像/学生获奖/2025学年第一学期综合学科条线赛事(1).xlsx', '2025S1')

db.commit()

print('═══ 导入完成 ═══')
for k, v in report.items():
    print(f'  {k}: {v} 行')

print('\n═══ 总表行数 ═══')
for t_ in ['students','vision_tests','physical_exams','fitness_tests','clubs','awards','award_certs']:
    print(f'  {t_}: {cur.execute(f"SELECT COUNT(*) FROM {t_}").fetchone()[0]}')

print('\n═══ 三-1 cohort 单生样本（陈思麟）═══')
idc = 'G<student-id>'
for tbl, sql in [
    ('students', 'SELECT name, grade_name, class_name, gender, birth_date FROM students WHERE id_card=?'),
    ('vision_tests', 'SELECT test_date, grade_name, glasses_type, right_naked_acuity, left_naked_acuity, right_sph, left_sph FROM vision_tests WHERE id_card=? ORDER BY test_date'),
    ('physical_exams', 'SELECT exam_year, height, weight, bmi FROM physical_exams WHERE id_card=?'),
    ('fitness_tests', 'SELECT test_year, height, weight, total_score, total_level FROM fitness_tests WHERE id_card=? ORDER BY test_year'),
    ('clubs', "SELECT club_name, teacher, location, school_year FROM clubs WHERE student_name='陈思麟'"),
    ('award_certs', "SELECT competition, prize, image_path FROM award_certs WHERE student_id_card=?"),
]:
    rows = cur.execute(sql, (idc,) if '?' in sql and "student_name" not in sql else (idc,) if '?' in sql else ()).fetchall()
    print(f'-- {tbl}: {len(rows)} 行')
    for r in rows[:5]:
        print('   ', dict(r))
