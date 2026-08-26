"""宝山实验学生数据导出脚本 - 导出为前端可用的JSON"""
import sqlite3
import json
from datetime import datetime

DB_PATH = "g:/EnsureAI/联通/宝山实验/student_data.db"
OUTPUT_PATH = "g:/EnsureAI/联通/宝山实验/data.json"

def export_for_frontend():
    """导出数据为前端可用的JSON格式"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 导出学生列表 - 转换为前端需要的格式
    cursor.execute('''SELECT s.id_card, s.name, s.gender, s.grade_name, s.class_name,
        f.test_year, f.total_score, f.total_level, f.bmi_level, f.height, f.weight,
        f.vital_capacity, f.run_50m, f.sit_reach, f.jump_stand, f.jump_rope,
        f.sit_up, f.bmi, f.vital_level, f.run_50m_level, f.sit_reach_level,
        f.jump_stand_level, f.jump_rope_level
        FROM students s
        LEFT JOIN fitness_tests f ON s.id_card = f.id_card 
        AND f.test_year = (SELECT MAX(test_year) FROM fitness_tests WHERE id_card = s.id_card)
        LIMIT 500''')
    cols = [d[0] for d in cursor.description]
    students_raw = [dict(zip(cols, r)) for r in cursor.fetchall()]
    
    # 转换为前端STUDENTS格式
    students = []
    fitness_by_student = {}
    for s in students_raw:
        student_id = f"stu_{s['id_card'][-6:]}"
        
        # 年级推断
        grade = '小学'
        if '初三' in str(s.get('grade_name', '')) or '九年级' in str(s.get('grade_name', '')):
            grade = '初中'
        
        # 生成颜色
        colors = ['#C8720A', '#1E5C3A', '#0D7377', '#7C3AED', '#DC2626', '#16A34A', '#D97706']
        color_idx = hash(s['name']) % len(colors)
        
        student = {
            'id': student_id,
            'no': s['id_card'],
            'name': s['name'],
            'displayName': s['name'][0] + '*' * (len(s['name']) - 1) if len(s['name']) > 1 else s['name'],
            'grade': grade,
            'school': '宝山实验学校',
            'class': s['class_name'] or '三年级1班',
            'age': 9,  # 三年级默认9岁
            'sex': s['gender'] or '未知',
            'color': colors[color_idx],
            'avatar': s['name'][0] if s['name'] else '学',
            'allergy': [],
            'diet_note': '',
            'special': '',
            'fitness': {
                'items': [
                    {'e': '🏃', 'n': '50米跑', 's': map_level(s.get('run_50m_level', 'fair'))},
                    {'e': '🤸', 'n': '坐位体前屈', 's': map_level(s.get('sit_reach_level', 'fair'))},
                    {'e': '💪', 'n': '跳绳/仰卧起坐', 's': map_level(s.get('jump_rope_level', 'fair') or s.get('sit_up_level', 'fair'))},
                    {'e': '🫁', 'n': '肺活量', 's': map_level(s.get('vital_level', 'fair'))},
                    {'e': '⏱', 'n': '耐力跑', 's': 'good'},
                    {'e': '🦵', 'n': '立定跳远', 's': map_level(s.get('jump_stand_level', 'fair'))}
                ]
            },
            'interests': ['阅读', '运动', '音乐'],
            'books': [],
            'tags': ['健康在档'],
            'awards': []
        }
        students.append(student)
        
        # 存储体测数据用于前端查询
        fitness_by_student[s['name']] = {
            'height': s.get('height'),
            'weight': s.get('weight'),
            'bmi': s.get('bmi'),
            'bmi_level': s.get('bmi_level'),
            'vital_capacity': s.get('vital_capacity'),
            'run_50m': s.get('run_50m'),
            'sit_reach': s.get('sit_reach'),
            'jump_stand': s.get('jump_stand'),
            'jump_rope': s.get('jump_rope'),
            'sit_up': s.get('sit_up'),
            'total_score': s.get('total_score'),
            'total_level': s.get('total_level'),
            'test_year': s.get('test_year')
        }
    
    # 导出获奖数据 - 按学生分组
    cursor.execute('''SELECT name, class_name, competition, prize, subject, teacher, remark
        FROM awards ORDER BY name, subject''')
    awards_by_student = {}
    for row in cursor.fetchall():
        name, cls, comp, prize, subj, teacher, remark = row
        if name not in awards_by_student:
            awards_by_student[name] = []
        awards_by_student[name].append({
            'name': comp,
            'level': '区级' if '区' in str(comp) else '校级',
            'prize': prize,
            'subject': subj,
            'date': '2024-2025',
            'org': '宝山实验学校'
        })
    
    # 将获奖数据合并到学生对象
    for student in students:
        if student['name'] in awards_by_student:
            student['awards'] = awards_by_student[student['name']]
            student['tags'].append(f'获奖 {len(student["awards"])} 项')
    
    # 导出社团数据 - 按学生分组
    cursor.execute('''SELECT student_name, grade, class_name, club_name, teacher, location, school_year
        FROM clubs ORDER BY student_name''')
    clubs_by_student = {}
    for row in cursor.fetchall():
        name, grade, cls, club, teacher, loc, year = row
        if name not in clubs_by_student:
            clubs_by_student[name] = []
        clubs_by_student[name].append({
            'name': club,
            'teacher': teacher,
            'location': loc,
            'year': year
        })
    
    # 导出AB菜单数据
    cursor.execute('''SELECT week_number, menu_date, meal_set, category, dish_name, ingredient,
        calories, protein, fat, vitamin_c, soup_name, fruit_name, dessert_name, milk_name
        FROM ab_menus ORDER BY week_number, menu_date, meal_set''')
    
    menu_by_week = {}
    for row in cursor.fetchall():
        week, day, meal_set, cat, dish, ing, cal, pro, fat, vit, soup, fruit, dessert, milk = row
        if week not in menu_by_week:
            menu_by_week[week] = {}
        if day not in menu_by_week[week]:
            menu_by_week[week][day] = {'A': {'dishes': {}, 'nutrition': {}}, 
                                      'B': {'dishes': {}, 'nutrition': {}}}
        
        if dish:
            menu_by_week[week][day][meal_set]['dishes'][cat] = dish
            if cal:
                menu_by_week[week][day][meal_set]['nutrition'] = {
                    'calories': cal, 'protein': pro, 'fat': fat, 'vitamin_c': vit
                }
    
    # 导出体质测试历史
    cursor.execute('''SELECT s.name, f.test_year, f.height, f.weight, f.bmi, f.total_level,
        f.vital_capacity, f.run_50m, f.sit_reach, f.jump_stand
        FROM fitness_tests f JOIN students s ON f.id_card = s.id_card
        ORDER BY s.name, f.test_year''')
    
    fitness_history = []
    for row in cursor.fetchall():
        fitness_history.append({
            'name': row[0], 'year': row[1], 'height': row[2], 'weight': row[3],
            'bmi': row[4], 'level': row[5], 'vital': row[6], 'run50m': row[7],
            'sitReach': row[8], 'jump': row[9]
        })
    
    data = {
        'students': students,
        'awards_by_student': awards_by_student,
        'clubs_by_student': clubs_by_student,
        'menu_by_week': menu_by_week,
        'fitness_history': fitness_history,
        'export_time': datetime.now().isoformat(),
        'total_students': len(students),
        'total_awards': sum(len(a) for a in awards_by_student.values()),
        'total_clubs': sum(len(c) for c in clubs_by_student.values()),
        'total_weeks': len(menu_by_week)
    }
    
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"JSON导出成功: {OUTPUT_PATH}")
    print(f"  学生数: {len(students)}")
    print(f"  获奖记录: {data['total_awards']}")
    print(f"  社团记录: {data['total_clubs']}")
    print(f"  菜单周数: {len(menu_by_week)}")
    
    # 打印前3个学生样本
    print("\n样本学生数据:")
    for s in students[:3]:
        print(f"  {s['name']} ({s['no'][-6:]}) - 获奖{len(s['awards'])}项")
    
    conn.close()

def map_level(level):
    """将数据库等级映射为前端等级"""
    level_map = {
        '优秀': 'great',
        '良好': 'good', 
        '及格': 'fair',
        '不合格': 'watch',
        'A': 'great',
        'B': 'good',
        'C': 'fair',
        'D': 'watch'
    }
    return level_map.get(str(level), 'fair') if level else 'fair'

if __name__ == "__main__":
    export_for_frontend()
