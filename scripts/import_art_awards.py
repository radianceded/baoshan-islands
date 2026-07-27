#!/usr/bin/env python3
"""导入3份艺术奖项 docx 到 awards 表"""
import sqlite3, re
from docx import Document
from collections import defaultdict

DB = '/srv/baoshan/宝山实验/student_data.db'

FILES = [
    ('艺术单项', '/root/.openclaw/media/inbound/艺术单项获奖名单---483f15db-d0bb-4784-b5ca-ef8d45730936.docx'),
    ('艺术获奖', '/root/.openclaw/media/inbound/艺术获奖---ae4cf11e-45f7-46a6-9e5f-7d6997cbbb82.docx'),
]

def load_student_class_map(db):
    """从 students 表构建 姓名→班级 的映射"""
    cur = db.execute("SELECT DISTINCT name, class_name FROM students WHERE class_name != ''")
    name_to_classes = defaultdict(set)
    for name, cls in cur:
        if name:
            name_to_classes[name].add(cls)
    # 对每个名字取最常见班级
    return {n: list(clses)[0] for n, clses in name_to_classes.items()}

def is_baoshan_exp(school):
    """判断是否上海宝山区实验小学"""
    if not school: return False
    s = school.replace('上海市','').replace('上海','').strip()
    return s in ('宝山区实验小学', '宝山区实验小学 ', '')

def parse_file1(doc, class_map):
    """解析艺术单项获奖名单 (File 1)"""
    awards = []
    table = doc.tables[0]
    for row in table.rows:
        cells = [c.text.strip() for c in row.cells]
        cat_main = cells[0]    # 类别如 钢琴/舞蹈/西乐/民乐/声乐
        cat_sub  = cells[1]    # 子类如 管乐/键盘/组合
        group    = cells[2]    # 组别
        school   = cells[3]    # 学校
        name     = cells[4]    # 学生姓名
        prize    = cells[5]    # 奖次

        if not name: continue
        # 只导入宝山实验小学的
        if not is_baoshan_exp(school):
            continue

        sub_str = f' {cat_sub}' if cat_sub and cat_sub != '_' else ''
        competition = f'宝山区艺术单项比赛·{cat_main}{sub_str} ({group})'
        cls = class_map.get(name, '')

        awards.append({
            'name': name,
            'class_name': cls,
            'competition': competition,
            'prize': prize,
            'subject': '艺术',
            'teacher': '',
            'remark': f'宝山区艺术单项比赛',
            'source_sheet': '艺术单项获奖名单',
        })
    return awards

def parse_file2(doc, class_map):
    """解析艺术获奖 (File 2/3)"""
    awards = []
    table = doc.tables[0]
    has_header = table.rows[0].cells[0].text.strip() == '编号'
    start = 1 if has_header else 0

    for row in table.rows[start:]:
        cells = [c.text.strip().replace('\n', ' ').replace('\r', '') for c in row.cells]
        if not cells[1]:  # 空行跳过
            continue
        # 列: [编号, 学生姓名, 获奖名称, 等第, 发证单位, 发证时间, 指导教师]
        name = cells[1]
        competition = cells[2]
        prize = cells[3]
        issuer = cells[4]
        teacher = cells[6] if len(cells) > 6 else ''

        cls = class_map.get(name, '')
        awards.append({
            'name': name,
            'class_name': cls,
            'competition': competition,
            'prize': prize,
            'subject': '艺术',
            'teacher': teacher,
            'remark': issuer,
            'source_sheet': '艺术获奖名单',
        })
    return awards

def main():
    db = sqlite3.connect(DB)
    class_map = load_student_class_map(db)

    all_awards = []
    for label, path in FILES:
        doc = Document(path)
        if label == '艺术单项':
            records = parse_file1(doc, class_map)
        else:
            records = parse_file2(doc, class_map)
        print(f'{label}: {len(records)} records')
        for r in records:
            print(f"  {r['name']} | {r['class_name'] or '?'} | {r['competition'][:40]} | {r['prize']}")
        all_awards.extend(records)

    # 导入前先清旧的艺术比赛数据（source_sheet 匹配）
    old = db.execute(
        "SELECT COUNT(*) FROM awards WHERE source_sheet IN ('艺术单项获奖名单','艺术获奖名单')"
    ).fetchone()[0]
    if old > 0:
        db.execute("DELETE FROM awards WHERE source_sheet IN ('艺术单项获奖名单','艺术获奖名单')")
        print(f'  Removed {old} old art awards')

    # 插入
    for a in all_awards:
        db.execute(
            "INSERT INTO awards (name, class_name, competition, prize, subject, teacher, remark, source_sheet, created_at) VALUES (?,?,?,?,?,?,?,?,datetime('now'))",
            (a['name'], a['class_name'], a['competition'], a['prize'], a['subject'], a['teacher'], a['remark'], a['source_sheet'])
        )

    db.commit()
    new_total = db.execute("SELECT COUNT(*) FROM awards").fetchone()[0]
    print(f'\nDone: {len(all_awards)} art awards imported')
    print(f'Awards table total: {new_total}')
    db.close()

if __name__ == '__main__':
    main()
