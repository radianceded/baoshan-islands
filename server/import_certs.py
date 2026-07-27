#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宝山学习群岛 · 证书扫描件批量导入

把 *年级.zip 处理成 assets/award-certs 下的图片 + assets/cert_awards.json 数据集。

用法：
    # 导入单个 zip（自动识别年级）
    python3 server/import_certs.py 三年级.zip

    # 导入多个
    python3 server/import_certs.py 一年级.zip 二年级.zip 三年级.zip

    # 只重建 JSON（不解压）
    python3 server/import_certs.py --rebuild-json

    # 列出当前数据集
    python3 server/import_certs.py --list

    # 清空某年级（删图 + 重建 JSON）
    python3 server/import_certs.py --clear 三年级

zip 内部结构假设：
    <年级>/
        <班级>/
            <学生姓名>_证书.png    # 或 .jpg / .jpeg

文件名规则：用 '_' '-' '—' 任一分隔，前半段视为学生姓名。
"""
import os, sys, json, re, zipfile, shutil, sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CERTS_DIR = os.path.join(BASE_DIR, 'assets', 'award-certs')
JSON_PATH = os.path.join(BASE_DIR, 'assets', 'cert_awards.json')
DB_PATH = os.path.join(BASE_DIR, 'student_data.db')

VALID_EXTS = ('.png', '.jpg', '.jpeg', '.webp')

def fix_chinese(name):
    """zip 里的中文文件名通常被 cp437 编码，转回 gbk"""
    try:
        return name.encode('cp437').decode('gbk')
    except Exception:
        return name

def extract_zip(zip_path):
    """解压一个 zip 到 assets/award-certs/<年级>/<班级>/<姓名>_证书.ext"""
    if not os.path.exists(zip_path):
        print(f'  ❌ 找不到 {zip_path}')
        return 0
    moved = 0
    skipped = 0
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            fixed = fix_chinese(info.filename)
            if info.is_dir():
                continue
            # 期望路径形如 三年级/三（1）/陈思麟_证书.png
            parts = [p for p in fixed.replace('\\','/').split('/') if p]
            if len(parts) < 3:
                continue
            # 跳过 macOS 系统隐藏文件
            if any(p.startswith('.') or p.startswith('__MACOSX') for p in parts):
                continue
            ext = os.path.splitext(parts[-1])[1].lower()
            if ext not in VALID_EXTS:
                continue
            grade, klass, fname = parts[-3], parts[-2], parts[-1]
            dest_dir = os.path.join(CERTS_DIR, grade, klass)
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, fname)
            if os.path.exists(dest_path) and os.path.getsize(dest_path) == info.file_size:
                skipped += 1
                continue
            with z.open(info) as src, open(dest_path, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            moved += 1
    return moved, skipped

def extract_name(stem):
    """文件名去后缀后，'_' / '-' / '—' 任一切，取首段"""
    return re.split(r'[_\-—\s]', stem, 1)[0].strip() or stem

def rebuild_json():
    """扫描 assets/award-certs 下全部图片，重建 cert_awards.json"""
    items = []
    if not os.path.exists(CERTS_DIR):
        os.makedirs(CERTS_DIR, exist_ok=True)
    for grade in sorted(os.listdir(CERTS_DIR)):
        grade_dir = os.path.join(CERTS_DIR, grade)
        if not os.path.isdir(grade_dir): continue
        for klass in sorted(os.listdir(grade_dir)):
            class_dir = os.path.join(grade_dir, klass)
            if not os.path.isdir(class_dir): continue
            for f in sorted(os.listdir(class_dir)):
                if not f.lower().endswith(VALID_EXTS): continue
                if f.startswith('.'): continue
                stem = os.path.splitext(f)[0]
                name = extract_name(stem)
                rel = os.path.join('assets','award-certs',grade,klass,f).replace('\\','/')
                items.append({
                    'name': name,
                    'grade': grade,
                    'class_name': klass,
                    'competition': f'{grade}班级表彰',
                    'prize': '班级奖状',
                    'subject': '综合',
                    'teacher': '',
                    'image_path': rel,
                    'source': 'cert-scan',
                })
    items.sort(key=lambda x: (x['grade'], x['class_name'], x['name']))
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump({'cert_awards': items, 'total': len(items)}, f, ensure_ascii=False, indent=2)
    return items

def cmd_to_db():
    """把 cert_awards.json (或者直接扫描目录) 灌进数据库"""
    items = rebuild_json()  # 顺便保证 JSON 也是最新
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS award_certs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id_card TEXT,
        student_name TEXT NOT NULL,
        grade TEXT NOT NULL,
        class_name TEXT NOT NULL,
        competition TEXT, prize TEXT, subject TEXT, teacher TEXT,
        image_path TEXT NOT NULL, source TEXT,
        uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(student_name, grade, class_name, image_path)
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_certs_name ON award_certs(student_name)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_certs_class ON award_certs(grade, class_name)')
    inserted = 0
    skipped = 0
    for it in items:
        try:
            conn.execute('''INSERT INTO award_certs(student_name, grade, class_name,
                competition, prize, subject, teacher, image_path, source)
                VALUES(?,?,?,?,?,?,?,?,?)''', (
                it['name'], it['grade'], it['class_name'],
                it.get('competition'), it.get('prize'), it.get('subject'), it.get('teacher'),
                it['image_path'], it.get('source')
            ))
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    total = conn.execute('SELECT COUNT(*) FROM award_certs').fetchone()[0]
    conn.close()
    print(f'✅ 入库 {inserted} 条（跳过已存在 {skipped} 条）；表中共 {total} 条')

def cmd_list():
    if not os.path.exists(JSON_PATH):
        print('（尚未生成 cert_awards.json）'); return
    with open(JSON_PATH, encoding='utf-8') as f:
        data = json.load(f)
    items = data.get('cert_awards', [])
    by_grade = {}
    by_class = {}
    for a in items:
        by_grade.setdefault(a['grade'], 0); by_grade[a['grade']] += 1
        key = (a['grade'], a['class_name'])
        by_class.setdefault(key, 0); by_class[key] += 1
    print(f'共 {len(items)} 条证书')
    print()
    for g, n in sorted(by_grade.items()):
        print(f'  · {g}: {n} 人')
        for (gg, k), nn in sorted(by_class.items()):
            if gg == g:
                print(f'      {k}: {nn}')

def cmd_clear(grade):
    target = os.path.join(CERTS_DIR, grade)
    if not os.path.exists(target):
        print(f'  {grade} 不存在，跳过')
        return
    cnt = sum(1 for _,_,fs in os.walk(target) for _ in fs)
    shutil.rmtree(target)
    print(f'  已删除 {grade}（{cnt} 个文件）')

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return

    if '--list' in args:
        cmd_list(); return
    if '--rebuild-json' in args:
        items = rebuild_json()
        print(f'✅ 重建完成：{len(items)} 条')
        return
    if '--to-db' in args:
        cmd_to_db(); return
    if '--clear' in args:
        i = args.index('--clear')
        if i+1 >= len(args):
            print('用法: --clear <年级名>'); return
        cmd_clear(args[i+1])
        items = rebuild_json()
        print(f'✅ 重建完成：{len(items)} 条')
        return

    # 默认：把所有非选项参数当成 zip 路径处理
    zips = [a for a in args if not a.startswith('-')]
    if not zips:
        print(__doc__); return

    total_moved = total_skip = 0
    for z in zips:
        print(f'▶ 处理 {z}…')
        m, s = extract_zip(z)
        print(f'  · 新增 {m} 张 · 已存在跳过 {s} 张')
        total_moved += m
        total_skip += s
    print()
    items = rebuild_json()
    print(f'✅ 共导入 {total_moved} 张（跳过 {total_skip}）；cert_awards.json 现有 {len(items)} 条记录')

if __name__ == '__main__':
    main()
