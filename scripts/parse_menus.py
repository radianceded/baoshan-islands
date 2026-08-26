#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析宝山实验小学每周菜单 Excel，生成 js/menu_data.js
列结构：行4=[A套餐,B套餐, A套餐,B套餐, ...]对应周一~周五
A套餐列：2,4,6,8,10  B套餐列：3,5,7,9,11
需跳过：主食材份量（g) / 份量（g） 行
"""
import os, re, json, openpyxl
from datetime import datetime

MENU_DIR = "2025学年第一学期学生菜单"
OUTPUT_JS = "js/menu_data.js"

DAYS = ['周一', '周二', '周三', '周四', '周五']
# 每天 A列, B列 (0-based index)
DAY_COLS = {
    '周一': (2, 3),
    '周二': (4, 5),
    '周三': (6, 7),
    '周四': (8, 9),
    '周五': (10, 11),
}

def extract_week_num(filename):
    m = re.search(r'第(\d+)-(\d+)周', filename)
    if m:
        return int(m.group(1))  # 取第一周
    m = re.search(r'第(\d+)周', filename)
    if m:
        return int(m.group(1))
    return 0

def is_skip_row(field_name):
    """份量行和营养素行跳过，不作为菜品数据"""
    skip_keywords = ['份量', '主食材', '蛋白质', '脂肪', '维生素', '碳水', '钙', '铁']
    return any(k in field_name for k in skip_keywords)

def parse_one_excel(filepath):
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    
    # 找到AB套餐标题行 (行4, index=4 通常)
    ab_row_idx = None
    for ri, row in enumerate(rows[:10]):
        vals = [str(v).strip() if v else '' for v in row]
        if 'A套餐' in vals and 'B套餐' in vals:
            ab_row_idx = ri
            break
    
    if ab_row_idx is None:
        return None
    
    # 验证列位置：根据实际AB行重新确认列索引
    ab_row = rows[ab_row_idx]
    a_cols = []
    b_cols = []
    for ci, v in enumerate(ab_row):
        vs = str(v).strip() if v else ''
        if vs == 'A套餐':
            a_cols.append(ci)
        elif vs == 'B套餐':
            b_cols.append(ci)
    
    # 最多5天
    a_cols = a_cols[:5]
    b_cols = b_cols[:5]
    
    if not a_cols:
        return None
    
    # 初始化结果
    result = {}
    for i, day in enumerate(DAYS):
        result[day] = {
            'A': {'main': '', 'dishes': [], 'soup': '', 'fruit': '', 'calories': ''},
            'B': {'main': '', 'dishes': [], 'soup': '', 'fruit': '', 'calories': ''}
        }
    
    # 从AB行之后开始读取数据
    for ri in range(ab_row_idx + 1, len(rows)):
        row = rows[ri]
        # 第1列(index=1)是膳食品类标签
        field_raw = str(row[1]).strip() if len(row) > 1 and row[1] else ''
        
        if not field_raw:
            continue
        
        # 跳过份量行
        if is_skip_row(field_raw):
            continue
        
        # 判断字段类型
        if '主食品名' in field_raw:
            field = 'main'
        elif '菜品' in field_raw and '品名' in field_raw:
            field = 'dish'
        elif '例汤品名' in field_raw or ('汤' in field_raw and '品名' in field_raw):
            field = 'soup'
        elif '水果品名' in field_raw:
            field = 'fruit'
        elif '奶制品品名' in field_raw:
            field = 'milk'  # 跳过
        elif '热量' in field_raw:
            field = 'calories'
        else:
            continue
        
        if field == 'milk':
            continue
        
        # 按天填充
        for di, day in enumerate(DAYS):
            a_ci = a_cols[di] if di < len(a_cols) else None
            b_ci = b_cols[di] if di < len(b_cols) else None
            
            def get_val(ci):
                if ci is None or ci >= len(row):
                    return ''
                v = row[ci]
                return str(v).strip() if v else ''
            
            a_val = get_val(a_ci)
            b_val = get_val(b_ci)
            
            da = result[day]['A']
            db = result[day]['B']
            
            if field == 'main':
                if a_val and not da['main']:
                    da['main'] = a_val
                # B餐主食通常和A餐相同，若空则继承A
                if b_val and not db['main']:
                    db['main'] = b_val
                elif not db['main'] and a_val:
                    db['main'] = a_val  # B餐共享A餐主食
            elif field == 'dish':
                if a_val:
                    da['dishes'].append(a_val)
                if b_val:
                    db['dishes'].append(b_val)
            elif field == 'soup':
                if a_val and not da['soup']:
                    da['soup'] = a_val
                if b_val and not db['soup']:
                    db['soup'] = b_val
                elif not db['soup'] and a_val:
                    db['soup'] = a_val  # 例汤通常共享
            elif field == 'fruit':
                if a_val and not da['fruit']:
                    da['fruit'] = a_val
                if b_val and not db['fruit']:
                    db['fruit'] = b_val
                elif not db['fruit'] and a_val:
                    db['fruit'] = a_val
            elif field == 'calories':
                if a_val and not da['calories']:
                    da['calories'] = a_val
                if b_val and not db['calories']:
                    db['calories'] = b_val
    
    return result


def main():
    all_weeks = {}
    
    files = sorted(os.listdir(MENU_DIR), key=lambda f: (extract_week_num(f), f))
    
    for fname in files:
        if not fname.endswith('.xlsx'):
            continue
        week_num = extract_week_num(fname)
        if week_num == 0:
            print(f"跳过无法识别周次的文件: {fname}")
            continue
        
        # 避免重复（如第5-6周只存为第5周）
        key = str(week_num)
        if key in all_weeks:
            print(f"跳过重复周次 第{week_num}周: {fname}")
            continue
        
        fpath = os.path.join(MENU_DIR, fname)
        print(f"解析第{week_num}周: {fname}")
        
        try:
            week_data = parse_one_excel(fpath)
            if week_data:
                all_weeks[key] = {
                    'week': week_num,
                    'days': week_data
                }
                # 简单验证：第1周周一A餐
                mon_a = week_data.get('周一', {}).get('A', {})
                print(f"  OK | 周一A: {mon_a.get('main','')} + {','.join(mon_a.get('dishes',[])[:2])}")
            else:
                print(f"  SKIP: 解析失败")
        except Exception as e:
            import traceback
            print(f"  ERROR: {e}")
            traceback.print_exc()
    
    # 生成 JS
    os.makedirs('js', exist_ok=True)
    
    weeks_sorted = {k: all_weeks[k] for k in sorted(all_weeks.keys(), key=lambda x: int(x))}
    
    js_content = """// 宝山实验小学 2025学年第一学期菜单数据库
// 自动生成于 {ts}
// 共 {n} 周 (第 {wmin}-{wmax} 周)
// 数据来源：2025学年第一学期学生菜单 Excel 文件

const MENU_DATABASE = {data};
""".format(
        ts=datetime.now().strftime('%Y-%m-%d %H:%M'),
        n=len(weeks_sorted),
        wmin=min(int(k) for k in weeks_sorted),
        wmax=max(int(k) for k in weeks_sorted),
        data=json.dumps(weeks_sorted, ensure_ascii=False, indent=2)
    )
    
    with open(OUTPUT_JS, 'w', encoding='utf-8') as f:
        f.write(js_content)
    
    print(f"\nOK 生成完成: {OUTPUT_JS}")
    print(f"   共 {len(weeks_sorted)} 周，周次: {sorted(int(k) for k in weeks_sorted.keys())}")
    
    # 打印第1周完整数据验证
    if '1' in weeks_sorted:
        print("\n--- 第1周周一 A/B餐 ---")
        mon = weeks_sorted['1']['days']['周一']
        print("A餐:", json.dumps(mon['A'], ensure_ascii=False))
        print("B餐:", json.dumps(mon['B'], ensure_ascii=False))


if __name__ == '__main__':
    main()
