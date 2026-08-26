"""Export database data as JavaScript file for HTML consumption"""
import json
import sqlite3
import re

DB_PATH = "d:/EnsureAI/联通/宝山实验/student_data.db"
OUTPUT_PATH = "d:/EnsureAI/联通/宝山实验/data.js"


def clean_student_name(name):
    """Remove leading numbers from student names like '01陈俊熹' -> '陈俊熹'"""
    return re.sub(r'^\d+', '', name).strip()


def export():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ── Students with latest fitness data ──
    cursor.execute('''SELECT s.id_card, s.name, s.gender, s.grade_name, s.class_name,
        f.test_year, f.total_score, f.total_level, f.bmi_level, f.height, f.weight, f.bmi,
        f.vital_capacity, f.vital_level, f.run_50m, f.run_50m_level,
        f.sit_reach, f.sit_reach_level, f.jump_stand, f.jump_stand_level,
        f.jump_rope, f.jump_rope_level, f.sit_up, f.sit_up_level
        FROM students s
        LEFT JOIN fitness_tests f ON s.id_card = f.id_card
        AND f.test_year = (SELECT MAX(test_year) FROM fitness_tests WHERE id_card = s.id_card)
        ORDER BY s.class_name, s.name''')
    cols = [d[0] for d in cursor.description]
    students = [dict(zip(cols, r)) for r in cursor.fetchall()]
    # Clean gender: 1=男, 2=女
    for s in students:
        s['gender'] = '男' if s['gender'] == '1' else '女' if s['gender'] == '2' else s['gender']
        if not s['grade_name']:
            s['grade_name'] = '一年级'  # default for missing

    # ── Fitness history (all years) ──
    cursor.execute('''SELECT id_card, test_year, height, weight, bmi, bmi_level,
        vital_capacity, vital_level, run_50m, run_50m_level, sit_reach, sit_reach_level,
        jump_stand, jump_stand_level, jump_rope, jump_rope_level, sit_up, sit_up_level,
        total_score, total_level FROM fitness_tests ORDER BY id_card, test_year''')
    cols = [d[0] for d in cursor.description]
    fitness_history = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # ── Awards ──
    cursor.execute('''SELECT name, class_name, competition, prize, subject, teacher, remark, source_sheet
        FROM awards ORDER BY subject, competition, name''')
    cols = [d[0] for d in cursor.description]
    awards = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # Build awards by student name for cross-reference
    awards_by_student = {}
    for a in awards:
        name = a['name']
        if name not in awards_by_student:
            awards_by_student[name] = []
        awards_by_student[name].append(a)

    # ── Clubs ──
    cursor.execute('''SELECT student_name, grade, class_name, club_name, teacher, location, school_year
        FROM clubs ORDER BY school_year, student_name''')
    cols = [d[0] for d in cursor.description]
    clubs_raw = [dict(zip(cols, r)) for r in cursor.fetchall()]
    # Clean names
    for c in clubs_raw:
        c['student_name'] = clean_student_name(c['student_name'])

    # Build clubs by student
    clubs_by_student = {}
    for c in clubs_raw:
        name = c['student_name']
        if name not in clubs_by_student:
            clubs_by_student[name] = []
        clubs_by_student[name].append(c)

    # ── AB Menus organized by week ──
    cursor.execute('''SELECT week_number, menu_date, meal_set, category, dish_name, ingredient,
        calories, protein, fat, vitamin_c, soup_name, soup_ingredient,
        fruit_name, fruit_amount FROM ab_menus
        ORDER BY week_number, menu_date, meal_set, id''')
    cols = [d[0] for d in cursor.description]
    menu_rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # Organize menus by week -> day -> set -> dishes list
    menus_by_week = {}
    for m in menu_rows:
        w = m['week_number']
        d = m['menu_date']
        s = m['meal_set']
        if w not in menus_by_week:
            menus_by_week[w] = {}
        if d not in menus_by_week[w]:
            menus_by_week[w][d] = {'A': [], 'B': []}
        cat = m['category'] or ''
        dish = m['dish_name'] or ''
        if dish and '份量' not in cat and '食材' not in cat:
            menus_by_week[w][d][s].append({
                'category': cat,
                'dish': dish,
                'calories': m['calories'],
                'soup': m['soup_name'],
                'fruit': m['fruit_name']
            })

    # ── Build final JS output ──
    js_data = {
        'students': students,
        'fitness_history': fitness_history,
        'awards': awards,
        'awards_by_student': awards_by_student,
        'clubs_by_student': clubs_by_student,
        'menus_by_week': menus_by_week,
        'stats': {
            'total_students': len(students),
            'total_awards': len(awards),
            'total_clubs': len(clubs_raw),
            'total_weeks': len(menus_by_week),
            'award_subjects': {},
            'award_by_class': {},
        }
    }

    # Compute stats
    for a in awards:
        subj = a['subject']
        js_data['stats']['award_subjects'][subj] = js_data['stats']['award_subjects'].get(subj, 0) + 1
        cls = a['class_name']
        if cls:
            js_data['stats']['award_by_class'][cls] = js_data['stats']['award_by_class'].get(cls, 0) + 1

    # Write as JS
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write('// Auto-generated from student_data.db - DO NOT EDIT\n')
        f.write(f'const REAL_DATA = {json.dumps(js_data, ensure_ascii=False, indent=None)};\n')

    conn.close()
    print(f"data.js exported: {OUTPUT_PATH}")
    print(f"  Students: {len(students)}, Awards: {len(awards)}, Clubs: {len(clubs_raw)}, Menu weeks: {len(menus_by_week)}")


if __name__ == "__main__":
    export()
