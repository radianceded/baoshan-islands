#!/usr/bin/env python3
"""Import real 3rd grade (2022级) club data from Excel into the clubs table.
Replaces ALL existing club records with only verified real data."""

import sqlite3
import sys
import os
from datetime import datetime

# ── Parse Excel ──
import openpyxl

XLSX_PATH = os.path.expanduser('/root/.openclaw/media/inbound/25年3年级---492cf9c8-35bc-4c64-a8d1-40e008eb6a04.xlsx')
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'student_data.db')

# Extract all rows
wb = openpyxl.load_workbook(XLSX_PATH)
records = []
for sheet_name in wb.sheetnames:
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        continue
    header = rows[0]
    # Expected: 校区, 年级, 班级, 学生姓名, 拓展课名称, 上课教师, 上课地点
    for row in rows[1:]:
        if not row[0]:
            continue
        records.append({
            'campus': str(row[0]).strip(),
            'grade': str(row[1]).strip() if row[1] else '',
            'class_name': str(row[2]).strip() if row[2] else '',
            'student_name': str(row[3]).strip() if row[3] else '',
            'club_name': str(row[4]).strip() if row[4] else '',
            'teacher': str(row[5]).strip() if row[5] else '',
            'location': str(row[6]).strip() if row[6] else '',
        })

print(f'Parsed {len(records)} records from Excel')

# Filter valid records
valid = [r for r in records if r['student_name'] and r['club_name']]
print(f'Valid records (has name + club): {len(valid)}')

# Show unique clubs
unique_clubs = sorted(set(r['club_name'] for r in valid))
print(f'\nUnique clubs ({len(unique_clubs)}):')
for i, c in enumerate(unique_clubs, 1):
    count = sum(1 for r in valid if r['club_name'] == c)
    print(f'  {i:2}. {c} ({count}人)')

# ── Update database ──
print(f'\nConnecting to {DB_PATH}')
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row

# Show old stats
old_total = db.execute('SELECT COUNT(*) FROM clubs').fetchone()[0]
old_distinct = db.execute('SELECT COUNT(DISTINCT club_name) FROM clubs').fetchone()[0]
print(f'BEFORE: {old_total} records, {old_distinct} distinct clubs')

# Delete all old club data
db.execute('DELETE FROM clubs')
print('Deleted all existing club records')

# Insert new records for 2025学年 (current school year for 3rd grade = 2022级)
now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
inserted = 0
for r in valid:
    # Normalize: 2022级 maps to 三年级 in school_year 2025学年
    db.execute('''
        INSERT INTO clubs (student_name, grade, class_name, club_name, teacher, location, school_year, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        r['student_name'],
        r['grade'],
        r['class_name'],
        r['club_name'],
        r['teacher'],
        r['location'],
        '2025学年',
        now
    ))
    inserted += 1

db.commit()
print(f'Inserted {inserted} new records')

# Verify
new_total = db.execute('SELECT COUNT(*) FROM clubs').fetchone()[0]
new_distinct = db.execute('SELECT COUNT(DISTINCT club_name) FROM clubs').fetchone()[0]
print(f'AFTER: {new_total} records, {new_distinct} distinct clubs')

# Show new club list
print('\nNew club list:')
for r in db.execute('''
    SELECT club_name AS name, teacher, location, COUNT(*) as cnt
    FROM clubs
    GROUP BY club_name, teacher, location
    ORDER BY cnt DESC
''').fetchall():
    print(f'  {r["name"]} | {r["teacher"]} | {r["location"]} | {r["cnt"]}人')

db.close()
print('\n✅ Import complete. Clubs database now contains only real 3rd grade data.')
