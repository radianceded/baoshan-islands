"""宝山实验学生数据数据库构建脚本"""
import pandas as pd
import sqlite3
import os
import re
from datetime import datetime

DB_PATH = "d:/EnsureAI/联通/宝山实验/student_data.db"

def create_database():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 学生主表
    cursor.execute('''CREATE TABLE students (
        id_card TEXT PRIMARY KEY, name TEXT NOT NULL, gender TEXT,
        birth_date TEXT, grade_name TEXT, class_name TEXT,
        school_name TEXT DEFAULT '宝山实验小学', created_at TEXT)''')
    
    # 体质测试表
    cursor.execute('''CREATE TABLE fitness_tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_card TEXT,
        test_year INTEGER, height REAL, weight REAL, bmi REAL,
        bmi_level TEXT, vital_capacity INTEGER, vital_level TEXT,
        run_50m REAL, run_50m_level TEXT, sit_reach REAL, sit_reach_level TEXT,
        jump_stand REAL, jump_stand_level TEXT, jump_rope INTEGER, jump_rope_level TEXT,
        sit_up INTEGER, sit_up_level TEXT, total_score REAL, total_level TEXT,
        created_at TEXT, FOREIGN KEY (id_card) REFERENCES students(id_card))''')
    
    # 屈光数据表
    cursor.execute('''CREATE TABLE vision_tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_card TEXT,
        test_date TEXT, left_sph REAL, right_sph REAL,
        test_grade TEXT, created_at TEXT,
        FOREIGN KEY (id_card) REFERENCES students(id_card))''')
    
    # AB餐菜单表 (包含营养素数据)
    cursor.execute('''CREATE TABLE ab_menus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_number INTEGER,
        menu_date TEXT,
        meal_set TEXT,
        -- 菜品分类
        category TEXT,
        dish_name TEXT,
        ingredient TEXT,
        -- 营养素数据
        calories REAL,
        protein REAL,
        fat REAL,
        vitamin_c REAL,
        -- 汤/水果/点心
        soup_name TEXT,
        soup_ingredient TEXT,
        fruit_name TEXT,
        fruit_amount TEXT,
        dessert_name TEXT,
        dessert_amount TEXT,
        milk_name TEXT,
        milk_amount TEXT,
        created_at TEXT)''')
    
    # 过敏信息表 (预留)
    cursor.execute('''CREATE TABLE allergies (
        id INTEGER PRIMARY KEY AUTOINCREMENT, id_card TEXT,
        allergen TEXT, source TEXT DEFAULT '家长填报', created_at TEXT,
        FOREIGN KEY (id_card) REFERENCES students(id_card))''')
    
    # 获奖记录表
    cursor.execute('''CREATE TABLE awards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, class_name TEXT, competition TEXT,
        prize TEXT, subject TEXT, teacher TEXT, remark TEXT,
        source_sheet TEXT, created_at TEXT)''')

    # 社团/拓展课表
    cursor.execute('''CREATE TABLE clubs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_name TEXT NOT NULL, grade TEXT, class_name TEXT,
        club_name TEXT, teacher TEXT, location TEXT,
        school_year TEXT, created_at TEXT)''')

    # 创建索引
    cursor.execute('CREATE INDEX idx_students_name ON students(name)')
    cursor.execute('CREATE INDEX idx_fitness_idcard ON fitness_tests(id_card, test_year)')
    cursor.execute('CREATE INDEX idx_vision_idcard ON vision_tests(id_card)')
    cursor.execute('CREATE INDEX idx_ab_menus_week ON ab_menus(week_number, menu_date, meal_set)')
    cursor.execute('CREATE INDEX idx_awards_name ON awards(name)')
    cursor.execute('CREATE INDEX idx_clubs_student ON clubs(student_name)')

    conn.commit()
    print(f"数据库创建成功: {DB_PATH}")
    return conn

def import_fitness_data(conn):
    base = "d:/EnsureAI/联通/宝山实验/学生数字画像/ai推送运动和早晚餐建议/2023-2025体质测试"
    files = [("2023体测等第成绩导出.xlsx", 2023), ("2024体测等第成绩导出.xlsx", 2024), ("2025体测等第成绩导出.xlsx", 2025)]
    cursor = conn.cursor()
    total = 0
    
    for fname, year in files:
        fpath = os.path.join(base, fname)
        if not os.path.exists(fpath):
            continue
        df = pd.read_excel(fpath)
        for _, row in df.iterrows():
            id_card = str(row.get('学籍号', '')).strip()
            name = str(row.get('姓名', '')).strip()
            if not id_card or id_card == 'nan':
                continue
            cursor.execute('''INSERT OR REPLACE INTO students 
                (id_card, name, gender, birth_date, grade_name, class_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                (id_card, name, str(row.get('性别', '')), str(row.get('出生日期', '')),
                 str(row.get('年级名称', '')), str(row.get('班级名称', '')), datetime.now().isoformat()))
            cursor.execute('''INSERT INTO fitness_tests 
                (id_card, test_year, height, weight, bmi, bmi_level, vital_capacity, vital_level,
                 run_50m, run_50m_level, sit_reach, sit_reach_level, jump_stand, jump_stand_level,
                 jump_rope, jump_rope_level, sit_up, sit_up_level, total_score, total_level, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                (id_card, year, row.get('身高'), row.get('体重'), row.get('BMI'), row.get('BMI等级'),
                 row.get('肺活量'), row.get('肺活量等级'), row.get('50米跑'), row.get('50米跑等级'),
                 row.get('坐位体前屈'), row.get('坐位体前屈等级'), row.get('立定跳远'), row.get('立定跳远等级'),
                 row.get('一分钟跳绳'), row.get('一分钟跳绳等级'), row.get('一分钟仰卧起坐'), 
                 row.get('一分钟仰卧起坐等级'), row.get('总分'), row.get('总分等级'), datetime.now().isoformat()))
            total += 1
    conn.commit()
    print(f"体质测试数据导入完成: {total} 条")

def import_vision_data(conn):
    base = "d:/EnsureAI/联通/宝山实验/学生数字画像/ai推送运动和早晚餐建议"
    files = [("2023一1班屈光数据.xlsx", "2023级"), ("2024.06一1班屈光数据.xlsx", "2024级"),
             ("2025.4二1屈光数据.xlsx", "2025级"), ("2025.9三1屈光数据.xlsx", "2025级")]
    cursor = conn.cursor()
    total = 0
    for fname, grade in files:
        fpath = os.path.join(base, fname)
        if not os.path.exists(fpath):
            continue
        try:
            df = pd.read_excel(fpath)
            for _, row in df.iterrows():
                id_card = str(row.get('学籍号', '')).strip()
                if not id_card or id_card == 'nan':
                    continue
                cursor.execute('''INSERT INTO vision_tests (id_card, test_date, left_sph, right_sph, test_grade, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                    (id_card, str(row.get('检查日期', '')), row.get('左眼球镜'), row.get('右眼球镜'),
                     grade, datetime.now().isoformat()))
                total += 1
        except: pass
    conn.commit()
    print(f"屈光数据导入完成: {total} 条")

def get_student_by_name(conn, name):
    cursor = conn.cursor()
    cursor.execute('''SELECT s.*, f.test_year, f.total_score, f.total_level, f.bmi_level,
        f.vital_level, f.run_50m_level, f.jump_stand_level
        FROM students s
        LEFT JOIN fitness_tests f ON s.id_card = f.id_card 
        AND f.test_year = (SELECT MAX(test_year) FROM fitness_tests WHERE id_card = s.id_card)
        WHERE s.name LIKE ?''', (f'%{name}%',))
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]

def get_all_students(conn, limit=100):
    cursor = conn.cursor()
    cursor.execute(f'''SELECT s.id_card, s.name, s.gender, s.grade_name, s.class_name,
        f.test_year, f.total_score, f.total_level, f.bmi_level FROM students s
        LEFT JOIN fitness_tests f ON s.id_card = f.id_card 
        AND f.test_year = (SELECT MAX(test_year) FROM fitness_tests WHERE id_card = s.id_card)
        LIMIT {limit}''')
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]

def import_menu_data(conn):
    """导入每周AB餐菜单数据（含营养素）"""
    base_dir = "d:/EnsureAI/联通/宝山实验/2025学年第一学期学生菜单"
    cursor = conn.cursor()
    total = 0
    
    files = [f for f in os.listdir(base_dir) if f.endswith('.xlsx')]
    for fname in files:
        # 从文件名提取周数
        week_match = re.search(r'第(\d+)[~-]?(\d+)?周', fname)
        if not week_match:
            week_match = re.search(r'第(\d+)周', fname)
        if not week_match:
            continue
        
        week_num = int(week_match.group(1))
        fpath = os.path.join(base_dir, fname)
        
        try:
            # 尝试读取Sheet1，如果没有营养素数据再尝试其他sheet
            df = pd.read_excel(fpath, sheet_name=0, header=None)
            if df.shape[0] < 20:
                continue
            
            # 解析营养素数据 (Row 19-22: 热量/蛋白质/脂肪/维生素C)
            nutrition = {'A': {}, 'B': {}}
            
            # 检查是否有营养素数据行
            has_nutrition = False
            if df.shape[0] > 22:
                # 查找"膳食宏营养素"或"膳食宏量营养素"行
                for row_idx in range(15, min(25, df.shape[0])):
                    row = df.iloc[row_idx]
                    if pd.notna(row[0]) and '膳食' in str(row[0]) and '营养' in str(row[0]):
                        has_nutrition = True
                        # 解析营养素 - 列对应周一到周五的AB套餐
                        # 列结构: 0=项目, 1=营养素名, 2=周一A, 3=周一B, 4=周二A, 5=周二B, ...
                        for col_idx in range(2, min(12, df.shape[1])):
                            day_idx = (col_idx - 2) // 2  # 0=周一, 1=周二, ...
                            set_type = 'A' if (col_idx - 2) % 2 == 0 else 'B'
                            days = ['周一', '周二', '周三', '周四', '周五']
                            if day_idx < 5:
                                day = days[day_idx]
                                if day not in nutrition[set_type]:
                                    nutrition[set_type][day] = {}
                                
                                val = row[col_idx]
                                if pd.notna(val):
                                    # 处理数值
                                    try:
                                        # 提取数字
                                        val_str = str(val).replace('kcal', '').replace('mg', '').strip()
                                        val = float(val_str) if val_str else None
                                    except:
                                        val = None
                                    
                                    nutrient_name = str(row[1]).strip() if pd.notna(row[1]) else ''
                                    if '热量' in nutrient_name:
                                        nutrition[set_type][day]['calories'] = val
                                    elif '蛋白质' in nutrient_name:
                                        nutrition[set_type][day]['protein'] = val
                                    elif '脂肪' in nutrient_name:
                                        nutrition[set_type][day]['fat'] = val
                                    elif '维生素' in nutrient_name or 'vc' in nutrient_name.lower():
                                        nutrition[set_type][day]['vitamin_c'] = val
                        break
            
            # 每天的列: 周一(2,3), 周二(4,5), 周三(6,7), 周四(8,9), 周五(10,11)
            # 注意：有些文件可能只有12列，需要检查
            max_col = df.shape[1]
            day_cols = [(2, 3, '周一'), (4, 5, '周二'), (6, 7, '周三'), (8, 9, '周四'), (10, 11, '周五')]
            day_cols = [(a, b, d) for a, b, d in day_cols if a < max_col and b < max_col]
            
            for a_col, b_col, day in day_cols:
                if a_col >= len(df) or b_col >= len(df):
                    continue
                
                # 获取该日该套餐的营养素
                def get_nutrition(set_type, day):
                    if day in nutrition.get(set_type, {}):
                        n = nutrition[set_type][day]
                        return {
                            'calories': n.get('calories'),
                            'protein': n.get('protein'),
                            'fat': n.get('fat'),
                            'vitamin_c': n.get('vitamin_c')
                        }
                    return {'calories': None, 'protein': None, 'fat': None, 'vitamin_c': None}
                
                # 解析菜品
                soup_name, soup_ing = None, None
                fruit_name, fruit_amt = None, None
                dessert_name, dessert_amt = None, None
                milk_name, milk_amt = None, None
                
                for row_idx in range(5, min(25, len(df))):
                    row = df.iloc[row_idx]
                    category = str(row[1]).strip() if pd.notna(row[1]) else ''
                    if not category or category == 'nan':
                        continue
                    
                    a_dish = str(row[a_col]).strip() if a_col < len(row) and pd.notna(row[a_col]) else ''
                    b_dish = str(row[b_col]).strip() if b_col < len(row) and pd.notna(row[b_col]) else ''
                    
                    # 分类处理
                    cat_key = category.replace(' ', '')
                    
                    # 解析汤
                    if '例汤' in cat_key:
                        soup_name = a_dish if a_dish and a_dish != 'nan' else None
                        soup_ing = str(row[a_col+1]).strip() if a_col+1 < len(row) and pd.notna(row[a_col+1]) else None
                        # B套餐汤
                        b_soup = str(row[b_col]).strip() if pd.notna(row[b_col]) else ''
                        b_soup_ing = str(row[b_col+1]).strip() if b_col+1 < len(row) and pd.notna(row[b_col+1]) else ''
                        if b_soup and b_soup != 'nan':
                            # 插入B套餐菜品和汤
                            n = get_nutrition('B', day)
                            cursor.execute('''INSERT INTO ab_menus 
                                (week_number, menu_date, meal_set, category, dish_name, ingredient,
                                 calories, protein, fat, vitamin_c, soup_name, soup_ingredient,
                                 fruit_name, fruit_amount, dessert_name, dessert_amount, milk_name, milk_amount, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                (week_num, day, 'B', category, b_soup, b_soup_ing,
                                 n['calories'], n['protein'], n['fat'], n['vitamin_c'],
                                 None, None, None, None, None, None, None, None, datetime.now().isoformat()))
                            total += 1
                        continue
                    
                    # 解析水果
                    if '水果' in cat_key:
                        fruit_name = a_dish if a_dish and a_dish != 'nan' else None
                        fruit_amt = str(row[a_col+1]).strip() if a_col+1 < len(row) and pd.notna(row[a_col+1]) else None
                        continue
                    
                    # 解析点心/小西点
                    if '点心' in cat_key or '小西点' in cat_key:
                        dessert_name = a_dish if a_dish and a_dish != 'nan' else None
                        dessert_amt = str(row[a_col+1]).strip() if a_col+1 < len(row) and pd.notna(row[a_col+1]) else None
                        continue
                    
                    # 解析奶制品
                    if '奶制品' in cat_key or '奶' in cat_key:
                        milk_name = a_dish if a_dish and a_dish != 'nan' else None
                        milk_amt = str(row[a_col+1]).strip() if a_col+1 < len(row) and pd.notna(row[a_col+1]) else None
                        continue
                    
                    # 主食和菜品
                    # A套餐
                    if a_dish and a_dish != 'nan':
                        # 获取食材份量
                        ing_row_idx = row_idx + 1
                        ingredient = None
                        if ing_row_idx < len(df):
                            ing_row = df.iloc[ing_row_idx]
                            if a_col < len(ing_row) and pd.notna(ing_row[a_col]) and '主食材' in str(ing_row[1]):
                                ingredient = str(ing_row[a_col]).strip()
                        
                        n = get_nutrition('A', day)
                        cursor.execute('''INSERT INTO ab_menus 
                            (week_number, menu_date, meal_set, category, dish_name, ingredient,
                             calories, protein, fat, vitamin_c, soup_name, soup_ingredient,
                             fruit_name, fruit_amount, dessert_name, dessert_amount, milk_name, milk_amount, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                            (week_num, day, 'A', category, a_dish, ingredient,
                             n['calories'], n['protein'], n['fat'], n['vitamin_c'],
                             soup_name, soup_ing, fruit_name, fruit_amt, dessert_name, dessert_amt, milk_name, milk_amt, datetime.now().isoformat()))
                        total += 1
                    
                    # B套餐
                    if b_dish and b_dish != 'nan':
                        ing_row_idx = row_idx + 1
                        ingredient = None
                        if ing_row_idx < len(df):
                            ing_row = df.iloc[ing_row_idx]
                            if b_col < len(ing_row) and pd.notna(ing_row[b_col]) and '主食材' in str(ing_row[1]):
                                ingredient = str(ing_row[b_col]).strip()
                        
                        n = get_nutrition('B', day)
                        cursor.execute('''INSERT INTO ab_menus 
                            (week_number, menu_date, meal_set, category, dish_name, ingredient,
                             calories, protein, fat, vitamin_c, soup_name, soup_ingredient,
                             fruit_name, fruit_amount, dessert_name, dessert_amount, milk_name, milk_amount, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                            (week_num, day, 'B', category, b_dish, ingredient,
                             n['calories'], n['protein'], n['fat'], n['vitamin_c'],
                             soup_name, soup_ing, fruit_name, fruit_amt, dessert_name, dessert_amt, milk_name, milk_amt, datetime.now().isoformat()))
                        total += 1
                        
        except Exception as e:
            print(f"处理菜单文件 {fname} 出错: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    conn.commit()
    print(f"菜单数据导入完成: {total} 条")

def import_awards_data(conn):
    """导入获奖数据 - 从综合学科条线赛事Excel"""
    fpath = "d:/EnsureAI/联通/宝山实验/学生数字画像/学生数字画像/学生获奖/2025学年第一学期综合学科条线赛事(1).xlsx"
    if not os.path.exists(fpath):
        print(f"获奖文件不存在: {fpath}")
        return
    cursor = conn.cursor()
    total = 0
    subject_map = {'体育':'体育', '科技':'科技', '音乐':'音乐', '美术':'美术'}

    for sheet_name in ['体育', '科技', '音乐', '美术']:
        try:
            df = pd.read_excel(fpath, sheet_name=sheet_name, header=None)
        except Exception as e:
            print(f"读取sheet {sheet_name} 失败: {e}")
            continue

        current_competition = None
        current_seq = None
        current_remark = None
        current_teacher = None

        for idx in range(1, len(df)):  # skip header row
            row = df.iloc[idx]
            seq = row.iloc[0]
            competition = row.iloc[1] if pd.notna(row.iloc[1]) else None
            class_name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ''
            name = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ''
            prize = str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else ''
            teacher_col = str(row.iloc[5]).strip() if len(row) > 5 and pd.notna(row.iloc[5]) else ''
            resp_teacher = str(row.iloc[6]).strip() if len(row) > 6 and pd.notna(row.iloc[6]) else ''
            remark = str(row.iloc[7]).strip() if len(row) > 7 and pd.notna(row.iloc[7]) else ''

            # Update current competition when sequence number changes
            if pd.notna(seq) and competition:
                current_competition = competition
                current_remark = remark if remark else None
                current_teacher = resp_teacher if resp_teacher else teacher_col

            if not name or name == 'nan' or name == '姓名':
                continue

            # Clean class name
            class_name = class_name.replace('（', '(').replace('）', ')')

            cursor.execute('''INSERT INTO awards
                (name, class_name, competition, prize, subject, teacher, remark, source_sheet, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (name, class_name, current_competition or '', prize,
                 subject_map.get(sheet_name, sheet_name),
                 current_teacher or resp_teacher or teacher_col,
                 remark or current_remark or '',
                 sheet_name, datetime.now().isoformat()))
            total += 1

    conn.commit()
    print(f"获奖数据导入完成: {total} 条")


def import_club_data(conn):
    """导入社团/拓展课数据"""
    base = "d:/EnsureAI/联通/宝山实验/学生数字画像/学生数字画像/学生参加社团"
    cursor = conn.cursor()
    total = 0

    files = [
        ("23年1年级.xlsx", "2023学年"),
        ("24年2年级.xlsx", "2024学年"),
        ("25年3年级.xlsx", "2025学年"),
    ]

    for fname, school_year in files:
        fpath = os.path.join(base, fname)
        if not os.path.exists(fpath):
            continue
        xl = pd.ExcelFile(fpath)

        for sheet_name in xl.sheet_names:
            try:
                df = pd.read_excel(fpath, sheet_name=sheet_name, header=None)
            except:
                continue

            if "1年级" in fname:
                # 23年格式: club info in row 2, students from row 6
                club_name = str(df.iloc[2, 0]).strip() if len(df) > 2 and pd.notna(df.iloc[2, 0]) else sheet_name
                teacher = str(df.iloc[2, 1]).strip() if len(df) > 2 and pd.notna(df.iloc[2, 1]) else ''
                location = str(df.iloc[2, 3]).strip() if len(df) > 2 and len(df.columns) > 3 and pd.notna(df.iloc[2, 3]) else ''
                # Extract club name from sheet name if needed
                if '(' in sheet_name:
                    club_name = sheet_name.split('(')[0].strip()

                for idx in range(6, len(df)):
                    row = df.iloc[idx]
                    grade = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                    cls = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ''
                    student = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ''
                    if not student or student == 'nan':
                        continue
                    cursor.execute('''INSERT INTO clubs
                        (student_name, grade, class_name, club_name, teacher, location, school_year, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                        (student, grade, cls, club_name, teacher, location, school_year, datetime.now().isoformat()))
                    total += 1
            else:
                # 24年/25年格式: header in row 0, data from row 1/2
                start_row = 1
                for idx in range(len(df)):
                    val = df.iloc[idx, 0] if pd.notna(df.iloc[idx, 0]) else ''
                    if '实验小学' in str(val) and idx > 0:
                        start_row = idx
                        break

                for idx in range(start_row, len(df)):
                    row = df.iloc[idx]
                    grade = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                    cls = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ''
                    student = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ''
                    club_name = str(row.iloc[4]).strip() if len(row) > 4 and pd.notna(row.iloc[4]) else ''
                    teacher = str(row.iloc[5]).strip() if len(row) > 5 and pd.notna(row.iloc[5]) else ''
                    location = str(row.iloc[6]).strip() if len(row) > 6 and pd.notna(row.iloc[6]) else ''

                    if not student or student == 'nan' or student == '学生姓名':
                        continue
                    cursor.execute('''INSERT INTO clubs
                        (student_name, grade, class_name, club_name, teacher, location, school_year, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                        (student, grade, cls, club_name, teacher, location, school_year, datetime.now().isoformat()))
                    total += 1

    conn.commit()
    print(f"社团数据导入完成: {total} 条")


def export_json(conn, output_path="d:/EnsureAI/联通/宝山实验/data.json"):
    """导出数据为JSON供前端使用"""
    import json
    
    cursor = conn.cursor()
    
    # 导出学生列表
    cursor.execute('''SELECT s.id_card, s.name, s.gender, s.grade_name, s.class_name,
        f.test_year, f.total_score, f.total_level, f.bmi_level, f.height, f.weight,
        f.vital_capacity, f.run_50m, f.sit_reach, f.jump_stand, f.jump_rope,
        f.sit_up, f.total_level, f.bmi, f.vital_level, f.run_50m_level, f.sit_reach_level,
        f.jump_stand_level, f.jump_rope_level
        FROM students s
        LEFT JOIN fitness_tests f ON s.id_card = f.id_card 
        AND f.test_year = (SELECT MAX(test_year) FROM fitness_tests WHERE id_card = s.id_card)
        LIMIT 500''')
    cols = [d[0] for d in cursor.description]
    students = [dict(zip(cols, r)) for r in cursor.fetchall()]
    
    # 导出AB菜单数据 - 包含营养素
    cursor.execute('''SELECT week_number, menu_date, meal_set, category, dish_name, ingredient,
        calories, protein, fat, vitamin_c, soup_name, soup_ingredient,
        fruit_name, fruit_amount, dessert_name, dessert_amount, milk_name, milk_amount
        FROM ab_menus ORDER BY week_number, menu_date, meal_set, category''')
    cols = [d[0] for d in cursor.description]
    menus = [dict(zip(cols, r)) for r in cursor.fetchall()]
    
    # 按周-天-套餐组织菜单，同时包含营养素
    menu_by_week = {}
    for m in menus:
        week = m['week_number']
        day = m['menu_date']
        set_type = m['meal_set']
        cat = m['category']
        
        if week not in menu_by_week:
            menu_by_week[week] = {}
        if day not in menu_by_week[week]:
            menu_by_week[week][day] = {'A': {'dishes': {}, 'nutrition': {}, 'soup': {}, 'fruit': {}, 'dessert': {}, 'milk': {}}, 
                                      'B': {'dishes': {}, 'nutrition': {}, 'soup': {}, 'fruit': {}, 'dessert': {}, 'milk': {}}}
        
        if m['dish_name']:
            menu_by_week[week][day][set_type]['dishes'][cat] = m['dish_name']
            
            # 添加营养素（只在主食行添加一次）
            if cat == '主食品名' or cat == '主食材份量（g)':
                if m['calories'] is not None:
                    menu_by_week[week][day][set_type]['nutrition'] = {
                        'calories': m['calories'],
                        'protein': m['protein'],
                        'fat': m['fat'],
                        'vitamin_c': m['vitamin_c']
                    }
            
            # 添加汤
            if m['soup_name']:
                menu_by_week[week][day][set_type]['soup'] = {
                    'name': m['soup_name'],
                    'ingredient': m['soup_ingredient']
                }
            
            # 添加水果
            if m['fruit_name']:
                menu_by_week[week][day][set_type]['fruit'] = {
                    'name': m['fruit_name'],
                    'amount': m['fruit_amount']
                }
            
            # 添加点心
            if m['dessert_name']:
                menu_by_week[week][day][set_type]['dessert'] = {
                    'name': m['dessert_name'],
                    'amount': m['dessert_amount']
                }
            
            # 添加奶制品
            if m['milk_name']:
                menu_by_week[week][day][set_type]['milk'] = {
                    'name': m['milk_name'],
                    'amount': m['milk_amount']
                }
    
    # 导出获奖数据
    cursor.execute('''SELECT name, class_name, competition, prize, subject, teacher, remark, source_sheet
        FROM awards ORDER BY subject, competition, name''')
    cols = [d[0] for d in cursor.description]
    awards = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # 导出社团数据
    cursor.execute('''SELECT student_name, grade, class_name, club_name, teacher, location, school_year
        FROM clubs ORDER BY school_year, grade, class_name, student_name''')
    cols = [d[0] for d in cursor.description]
    clubs = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # 导出体质测试历史 (所有年份)
    cursor.execute('''SELECT id_card, test_year, height, weight, bmi, bmi_level,
        vital_capacity, vital_level, run_50m, run_50m_level, sit_reach, sit_reach_level,
        jump_stand, jump_stand_level, jump_rope, jump_rope_level, sit_up, sit_up_level,
        total_score, total_level FROM fitness_tests ORDER BY id_card, test_year''')
    cols = [d[0] for d in cursor.description]
    fitness_history = [dict(zip(cols, r)) for r in cursor.fetchall()]

    data = {
        'students': students,
        'menu_by_week': menu_by_week,
        'awards': awards,
        'clubs': clubs,
        'fitness_history': fitness_history,
        'total_students': len(students),
        'total_weeks': len(menu_by_week),
        'total_awards': len(awards),
        'total_clubs': len(clubs)
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"JSON导出成功: {output_path}")
    print(f"  学生数: {len(students)}, 菜单周数: {len(menu_by_week)}")

if __name__ == "__main__":
    print("开始构建数据库...")
    conn = create_database()
    import_fitness_data(conn)
    import_vision_data(conn)
    import_menu_data(conn)
    import_awards_data(conn)
    import_club_data(conn)
    export_json(conn)

    print("\n=== 数据统计 ===")
    cursor = conn.cursor()
    for table in ['students', 'fitness_tests', 'vision_tests', 'ab_menus', 'awards', 'clubs']:
        cursor.execute(f'SELECT COUNT(*) FROM {table}')
        print(f"  {table}: {cursor.fetchone()[0]} 条")
    students = get_all_students(conn, 99999)
    print(f"\n学生总数: {len(students)}")
    if students:
        print(f"样本学生: {students[0]}")
