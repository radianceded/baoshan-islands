import sqlite3, json
conn = sqlite3.connect('student_data.db')
cursor = conn.cursor()

cursor.execute('''
SELECT s.id_card, s.name, s.gender, s.grade_name, s.class_name,
    f.test_year, f.total_score, f.total_level, f.bmi, f.bmi_level,
    f.vital_capacity, f.vital_level, f.run_50m, f.run_50m_level,
    f.sit_reach, f.sit_reach_level, f.jump_stand, f.jump_stand_level,
    f.jump_rope, f.jump_rope_level, f.sit_up, f.sit_up_level
FROM students s
LEFT JOIN fitness_tests f ON s.id_card = f.id_card 
    AND f.test_year = (SELECT MAX(test_year) FROM fitness_tests WHERE id_card = s.id_card)
ORDER BY s.name
''')

cols = [d[0] for d in cursor.description]
students = []
for row in cursor.fetchall():
    s = dict(zip(cols, row))
    items = []
    if s.get('run_50m'):
        status = 'good' if s.get('run_50m_level') in ['优秀','良好'] else 'fair' if s.get('run_50m_level')=='及格' else 'watch'
        items.append({'e':'🏃','n':'50米跑','s':status})
    if s.get('sit_reach'):
        status = 'great' if s.get('sit_reach_level')=='优秀' else 'good' if s.get('sit_reach_level')=='良好' else 'fair' if s.get('sit_reach_level')=='及格' else 'watch'
        items.append({'e':'🤸','n':'坐位体前屈','s':status})
    if s.get('jump_stand'):
        status = 'great' if s.get('jump_stand_level')=='优秀' else 'good' if s.get('jump_stand_level')=='良好' else 'fair' if s.get('jump_stand_level')=='及格' else 'watch'
        items.append({'e':'🦵','n':'立定跳远','s':status})
    if s.get('vital_capacity'):
        status = 'great' if s.get('vital_level')=='优秀' else 'good' if s.get('vital_level')=='良好' else 'fair' if s.get('vital_level')=='及格' else 'watch'
        items.append({'e':'🫁','n':'肺活量','s':status})
    if s.get('jump_rope'):
        status = 'great' if s.get('jump_rope_level')=='优秀' else 'good' if s.get('jump_rope_level')=='良好' else 'fair' if s.get('jump_rope_level')=='及格' else 'watch'
        items.append({'e':'⏱','n':'跳绳','s':status})
    if s.get('sit_up'):
        status = 'great' if s.get('sit_up_level')=='优秀' else 'good' if s.get('sit_up_level')=='良好' else 'fair' if s.get('sit_up_level')=='及格' else 'watch'
        items.append({'e':'💪','n':'仰卧起坐','s':status})
    
    gender = '男' if s.get('gender')=='1' else '女'
    grade = s.get('grade_name','')
    age_map = {'一年级':7,'二年级':8,'三年级':9,'四年级':10,'五年级':11,'六年级':12,'七年级':13,'八年级':14,'九年级':15}
    age = age_map.get(grade, 10)
    
    color = '#C8720A' if gender=='女' else '#1E5C3A'
    students.append({
        'id': s['id_card'][:8] if s.get('id_card') else 'unknown',
        'no': s['id_card'][-6:] if s.get('id_card') else '',
        'name': s['name'],
        'grade': grade,
        'school': '宝山实验小学',
        'class': grade + ' ' + (s.get('class_name','')),
        'age': age,
        'sex': gender,
        'color': color,
        'avatar': s['name'][0] if s.get('name') else '?',
        'allergy': [],
        'diet_note': '',
        'special': s.get('bmi_level','') if s.get('bmi_level') in ['超重','肥胖'] else '',
        'fitness': {'items': items},
        'interests': ['阅读','运动'],
        'books': [],
        'tags': ['健康在档']
    })

with open('students_export.json', 'w', encoding='utf-8') as f:
    json.dump(students, f, ensure_ascii=False, indent=2)

print(f"导出完成: {len(students)} 名学生")
print(students[0] if students else "无数据")