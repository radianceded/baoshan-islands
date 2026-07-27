#!/usr/bin/env python3
"""导入第17/18周真实学生营养午餐选餐数据"""
import sqlite3
from openpyxl import load_workbook
from datetime import date

DB = '/srv/baoshan/宝山实验/student_data.db'
XLSX = '/root/.openclaw/media/inbound/营养午餐_20260618165657---a6d17608-9347-45c9-a1bc-ecf2f2d34f70.xlsx'

# 星期几 → 数据库 weekday 值 (1-5)
WEEKDAY_MAP = {'周一':1,'周二':2,'周三':3,'周四':4,'周五':5}
WEEKDAY_NAMES = ['周一','周二','周三','周四','周五']

def parse():
    wb = load_workbook(XLSX)
    ws = wb['数据']
    
    records = []  # (id_card, name, grade, class, week, parity, weekday, choice)
    
    for row in ws.iter_rows(min_row=2, values_only=True):
        student_name = row[12] or ''
        student_id = row[13] or ''
        grade = row[8] or ''
        class_name = row[9] or ''
        campus = row[7] or ''
        odd_week = str(row[10]).strip() if row[10] else ''
        even_week = str(row[11]).strip() if row[11] else ''
        
        # 奇数周：只有周二有选餐
        odd_choice = row[1]  # 周二（奇数）
        odd_week_no = int(odd_week.replace('周','')) if odd_week.replace('周','').isdigit() else 0
        
        # 偶数周：周一~周五 各有选餐
        even_choices = [row[2], row[3], row[4], row[5], row[6]]  # 周一~周五
        even_week_no = int(even_week.replace('周','')) if even_week.replace('周','').isdigit() else 0
        
        # 只取第17周(奇数)和第18周(偶数)
        if odd_week_no == 17 and odd_choice:
            choice_val = 'A' if 'A' in str(odd_choice) else 'B'
            records.append((
                student_id, student_name, grade, class_name,
                17, 'odd', 2, choice_val, campus  # 周二=2
            ))
        
        if even_week_no == 18:
            for i, choice in enumerate(even_choices):
                wd = i + 1  # 周一=1..周五=5
                if choice:
                    choice_val = 'A' if 'A' in str(choice) else 'B'
                    records.append((
                        student_id, student_name, grade, class_name,
                        18, 'even', wd, choice_val, campus
                    ))
                else:
                    # 未选 → 默认A餐
                    records.append((
                        student_id, student_name, grade, class_name,
                        18, 'even', wd, 'A', campus
                    ))
    
    return records

def main():
    records = parse()
    print(f'Parsed {len(records)} meal choice records')
    
    # Stats
    w17 = [r for r in records if r[4] == 17]
    w18 = [r for r in records if r[4] == 18]
    print(f'  Week 17 (odd): {len(w17)}')
    print(f'  Week 18 (even): {len(w18)}')
    
    unique_ids_w17 = set(r[0] for r in w17)
    unique_ids_w18 = set(r[0] for r in w18)
    print(f'  Unique students: W17={len(unique_ids_w17)}, W18={len(unique_ids_w18)}')
    
    db = sqlite3.connect(DB)
    
    # Clear old week 17/18 data
    db.execute("DELETE FROM meal_choices WHERE week_number IN (17, 18)")
    
    # Insert
    for r in records:
        db.execute(
            "INSERT INTO meal_choices (id_card, name, grade_name, class_name, week_number, parity, weekday, choice, chosen_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))",
            (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], '家长')
        )
    
    db.commit()
    new_count = db.execute("SELECT COUNT(*) FROM meal_choices WHERE week_number IN (17,18)").fetchone()[0]
    print(f'\nInserted: {new_count} rows in meal_choices')
    
    # Update weekly_menus
    db.execute("DELETE FROM weekly_menus WHERE week_number IN (17, 18)")
    db.execute(
        "INSERT INTO weekly_menus (week_number, parity, date_start, date_end, image_path, notes) VALUES (?,?,?,?,?,?)",
        (17, 'odd', '2026-06-09', '2026-06-13', 'assets/menus/week17-menu.png', '第十七周菜单')
    )
    db.execute(
        "INSERT INTO weekly_menus (week_number, parity, date_start, date_end, image_path, notes) VALUES (?,?,?,?,?,?)",
        (18, 'even', '2026-06-16', '2026-06-20', None, '第十八周菜单（待上传）')
    )
    db.commit()
    print('weekly_menus updated')
    db.close()

if __name__ == '__main__':
    main()
