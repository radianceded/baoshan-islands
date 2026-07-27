#!/usr/bin/env python3
"""
迁移已有数据到 unified_events（批量优化版）
"""
import sqlite3, json, os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'student_data.db')

def migrate():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    
    # 预加载 name→id_card 映射（避免逐行查表）
    name_map = {}
    for row in db.execute('SELECT id_card, name, grade_name, class_name FROM students').fetchall():
        key = (row['name'], row['grade_name'] or '', row['class_name'] or '')
        if key not in name_map:
            name_map[key] = row['id_card']
    # 罗泾
    try:
        for row in db.execute('SELECT id_card, name, grade_name, class_name FROM students_luojing').fetchall():
            key = (row['name'], row['grade_name'] or '', row['class_name'] or '')
            if key not in name_map:
                name_map[key] = row['id_card']
    except:
        pass
    print(f'预加载 {len(name_map)} 个学生映射')
    
    # 确保表存在
    db.execute('''CREATE TABLE IF NOT EXISTS unified_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL, student_name TEXT, grade TEXT, class_name TEXT,
        campus TEXT DEFAULT '', island TEXT NOT NULL, branch TEXT NOT NULL,
        event_type TEXT NOT NULL, event_data TEXT, event_summary TEXT,
        event_date TEXT, school_year TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('DELETE FROM unified_events')  # 清空重迁
    db.commit()
    
    batch = []
    total = 0
    BATCH_SIZE = 500
    
    def flush():
        nonlocal total
        if not batch:
            return
        db.executemany(
            'INSERT OR REPLACE INTO unified_events (student_id, student_name, grade, class_name, campus, island, branch, event_type, event_data, event_summary, event_date, school_year) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            batch
        )
        db.commit()
        total += len(batch)
        batch.clear()
    
    def lookup(name, grade, klass):
        sid = name_map.get((name, grade or '', klass or ''))
        if sid: return sid
        sid = name_map.get((name, '', klass or ''))
        return sid or f"??_{name}"
    
    def resolve_campus(school_name):
        if not school_name: return 'benbu'
        sn = str(school_name)
        if '宝林' in sn: return 'baolin'
        if '罗泾' in sn: return 'luojing'
        return 'benbu'
    
    def add(sid, name, grade, klass, campus, island, branch, etype, data, summary, date, syear=None):
        batch.append((
            sid, name or '', grade or '', klass or '', campus, island, branch, etype,
            json.dumps(data, ensure_ascii=False) if data else '{}',
            summary, date or '', syear or ''
        ))
        if len(batch) >= BATCH_SIZE:
            flush()
    
    # ── 1. 体测 ──
    print('[1/9] 体测...')
    for r in db.execute('SELECT * FROM fitness_tests WHERE id_card IS NOT NULL').fetchall():
        d = dict(r)
        add(d['id_card'], d.get('name'), d.get('grade_name'), d.get('class_name'),
            resolve_campus(d.get('school_name')), '体能', '体能管理', 'fitness_test',
            {'height': d.get('height'), 'weight': d.get('weight'), 'bmi': d.get('bmi'),
             'bmi_level': d.get('bmi_level'), 'total_score': d.get('total_score'),
             'total_level': d.get('total_level')},
            f'体测 {d.get("test_year","")}: 总分{d.get("total_score","?")}({d.get("total_level","?")})',
            str(d.get('test_year', '')), str(d.get('test_year', '')))
    flush()
    print(f'  → {total}')
    
    # ── 2. 屈光 ──
    prev = total
    print('[2/9] 屈光...')
    for r in db.execute('SELECT * FROM vision_tests WHERE id_card IS NOT NULL').fetchall():
        d = dict(r)
        add(d['id_card'], d.get('name'), d.get('grade_name'), d.get('class_name'),
            resolve_campus(d.get('school_name')), '体能', '档案管理', 'vision_test',
            {'left_naked': d.get('left_naked_acuity'), 'right_naked': d.get('right_naked_acuity'),
             'left_corrected': d.get('left_corrected_acuity'), 'right_corrected': d.get('right_corrected_acuity')},
            f'屈光 {d.get("test_date","")}: L={d.get("left_naked_acuity","?")} R={d.get("right_naked_acuity","?")}',
            d.get('test_date', ''))
    flush()
    print(f'  → +{total - prev}')
    
    # ── 3. 体检 ──
    prev = total
    print('[3/9] 体检...')
    for r in db.execute('SELECT * FROM physical_exams WHERE id_card IS NOT NULL').fetchall():
        d = dict(r)
        add(d['id_card'], d.get('name'), d.get('grade_name'), d.get('class_name'),
            resolve_campus(d.get('school_name')), '体能', '档案管理', 'physical_exam',
            {'height': d.get('height'), 'weight': d.get('weight'), 'bmi': d.get('bmi'),
             'hospital': d.get('hospital'), 'exam_year': d.get('exam_year')},
            f'体检 {d.get("exam_year","")}: {d.get("height","?")}cm {d.get("weight","?")}kg',
            str(d.get('exam_year', '')), str(d.get('exam_year', '')))
    flush()
    print(f'  → +{total - prev}')
    
    # ── 4. 选餐 ──
    prev = total
    print('[4/9] 选餐...')
    wd_names = ['一','二','三','四','五']
    for r in db.execute('SELECT * FROM meal_choices WHERE id_card IS NOT NULL').fetchall():
        d = dict(r)
        wd = d.get('weekday', 1)
        day_name = wd_names[wd-1] if 1 <= wd <= 5 else str(wd)
        add(d['id_card'], d.get('name'), d.get('grade_name'), d.get('class_name'),
            'benbu', '体能', '饮食管理', 'meal_choice',
            {'week': d.get('week_number'), 'parity': d.get('parity'), 'weekday': wd, 'choice': d.get('choice')},
            f'选餐 W{d.get("week_number","?")}周{day_name}: {d.get("choice","?")}餐',
            datetime.now().strftime('%Y-%m-%d'))
    flush()
    print(f'  → +{total - prev}')
    
    # ── 5. 图书馆（批量聚合，不逐行）──
    prev = total
    print('[5/9] 图书馆(聚合)...')
    for r in db.execute('''
        SELECT borrower_name, borrower_grade, borrower_class,
               COUNT(*) as cnt, COUNT(DISTINCT title) as unique_titles
        FROM library_records WHERE borrower_name IS NOT NULL AND borrower_name != ''
        GROUP BY borrower_name, borrower_grade, borrower_class
    ''').fetchall():
        d = dict(r)
        sid = lookup(d['borrower_name'], d.get('borrower_grade'), d.get('borrower_class'))
        add(sid, d['borrower_name'], d.get('borrower_grade'), d.get('borrower_class'),
            'benbu', '素养', '英语阅读', 'reading_stats',
            {'total_books': d['cnt'], 'unique_titles': d['unique_titles']},
            f'累计借阅 {d["cnt"]} 本 ({d["unique_titles"]} 种)',
            datetime.now().strftime('%Y-%m-%d'))
    flush()
    print(f'  → +{total - prev}')
    
    # ── 6. 美术馆 ──
    prev = total
    print('[6/9] 美术馆...')
    for r in db.execute('SELECT * FROM art_works WHERE student_name IS NOT NULL').fetchall():
        d = dict(r)
        sid = lookup(d['student_name'], d.get('grade'), d.get('class_name'))
        add(sid, d['student_name'], d.get('grade'), d.get('class_name'),
            'benbu', '审美', '数字美术馆', 'art_work',
            {'work_title': d.get('work_title'), 'award_name': d.get('award_name'), 'award_level': d.get('award_level')},
            f'作品: 《{d.get("work_title","?")}》({d.get("award_name","?")})',
            d.get('created_at', ''))
    flush()
    print(f'  → +{total - prev}')
    
    # ── 7. 社团 ──
    prev = total
    print('[7/9] 社团...')
    for r in db.execute('SELECT * FROM clubs WHERE student_name IS NOT NULL').fetchall():
        d = dict(r)
        sid = lookup(d['student_name'], d.get('grade'), d.get('class_name'))
        add(sid, d['student_name'], d.get('grade'), d.get('class_name'),
            'benbu', '兴趣', '社团', 'club_enrollment',
            {'club_name': d.get('club_name'), 'teacher': d.get('teacher'), 'school_year': d.get('school_year')},
            f'社团: {d.get("club_name","?")} ({d.get("school_year","?")})',
            d.get('school_year', ''), d.get('school_year', ''))
    flush()
    print(f'  → +{total - prev}')
    
    # ── 8. 奖状 ──
    prev = total
    print('[8/9] 奖状...')
    for r in db.execute('SELECT * FROM award_certs').fetchall():
        d = dict(r)
        sid = d.get('student_id_card') or lookup(d.get('student_name',''), d.get('grade'), d.get('class_name'))
        add(sid, d.get('student_name'), d.get('grade'), d.get('class_name'),
            d.get('campus') or 'benbu', '成长', '市区奖状', 'award_cert',
            {'competition': d.get('competition'), 'prize': d.get('prize'), 'subject': d.get('subject'),
             'teacher': d.get('teacher'), 'wuyu': d.get('wuyu')},
            f'奖状: {d.get("competition","?")} {d.get("prize","?")}',
            d.get('uploaded_at', ''))
    flush()
    print(f'  → +{total - prev}')
    
    # ── 9. 阅读能力等级（从 island-reading/health 模拟数据事件化）──
    prev = total
    print('[9/9] 英语阅读能力...')
    try:
        for r in db.execute('SELECT * FROM library_records WHERE borrower_name IS NOT NULL AND borrower_name != "" LIMIT 1').fetchall():
            pass  # 只要确认表存在
        # 按学生聚合生成分级事件
        for r in db.execute('''
            SELECT borrower_name, borrower_grade, borrower_class,
                   MAX(price) as max_price, MIN(price) as min_price
            FROM library_records WHERE price > 0 AND borrower_name IS NOT NULL AND borrower_name != ''
            GROUP BY borrower_name, borrower_grade, borrower_class
        ''').fetchall():
            d = dict(r)
            sid = lookup(d['borrower_name'], d.get('borrower_grade'), d.get('borrower_class'))
            # 根据借书定价粗略推断阅读等级
            level_hint = '初阶' if (d['max_price'] or 0) < 30 else ('中阶' if (d['max_price'] or 0) < 60 else '高阶')
            add(sid, d['borrower_name'], d.get('borrower_grade'), d.get('borrower_class'),
                'benbu', '素养', '英语阅读', 'reading_level',
                {'level': level_hint, 'max_price': d.get('max_price'), 'min_price': d.get('min_price')},
                f'阅读水平: {level_hint} (书籍定价范围 ¥{d.get("min_price",0):.0f}-¥{d.get("max_price",0):.0f})',
                datetime.now().strftime('%Y-%m-%d'))
    except Exception as e:
        print(f'  (跳过英语阅读能力: {e})')
    flush()
    print(f'  → +{total - prev}')
    
    db.close()
    print(f'\n✅ 迁移完成！共 {total} 条事件')

if __name__ == '__main__':
    migrate()
