#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宝小学生画像 · 美育岛作品批量导入

把 *奖项名*.zip 处理成 assets/art-works/<奖项名>/<学生名>_<作品名>.<ext>,
并写入 student_data.db 的 art_works 表。

zip 内文件命名规则:
    学生名+作品名.png      (推荐)
    学生名_作品名.jpg
    学生名-作品名.jpeg
    学生名 作品名.webp
    (分隔符: + _ - — – 空格 任一,且可重复)
若文件名只有姓名没有作品名,作品名默认 "未命名作品"。

用法:
    python3 server/import_art.py 校园艺术节金奖.zip
    python3 server/import_art.py 一等奖.zip 二等奖.zip 三等奖.zip
    python3 server/import_art.py --list
    python3 server/import_art.py --clear 校园艺术节金奖
"""
import os, sys, re, zipfile, shutil, sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART_DIR = os.path.join(BASE_DIR, 'assets', 'art-works')
DB_PATH = os.path.join(BASE_DIR, 'student_data.db')

VALID_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
SEP_RE = re.compile(r'[+_\-—–\s]+')


def fix_chinese(name):
    try:
        return name.encode('cp437').decode('gbk')
    except Exception:
        return name


def safe_segment(seg):
    seg = (seg or '').strip().strip('.')
    seg = re.sub(r'[\\/:*?"<>|]', '_', seg)
    return seg or '未命名'


def parse_filename(stem):
    stem = stem.strip()
    if not stem:
        return None, None
    parts = SEP_RE.split(stem, 1)
    student = parts[0].strip()
    title = parts[1].strip() if len(parts) > 1 else ''
    return student or None, title or '未命名作品'


def classify_level(award_name):
    s = str(award_name or '')
    if re.search(r'特等|金奖|一等', s): return 'gold'
    if re.search(r'银奖|二等', s):       return 'silver'
    if re.search(r'铜奖|三等', s):       return 'bronze'
    return 'merit'


def ensure_table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS art_works(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        award_name TEXT NOT NULL,
        award_level TEXT,
        student_name TEXT NOT NULL,
        work_title TEXT NOT NULL,
        image_path TEXT NOT NULL,
        grade TEXT,
        class_name TEXT,
        uploaded_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(award_name, student_name, work_title)
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_art_award ON art_works(award_name)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_art_student ON art_works(student_name)')


def import_zip(zip_path):
    if not os.path.exists(zip_path):
        print(f'  ❌ 找不到 {zip_path}')
        return 0, 0, []

    award_name = safe_segment(os.path.splitext(os.path.basename(zip_path))[0])
    level = classify_level(award_name)
    dest_root = os.path.join(ART_DIR, award_name)
    os.makedirs(dest_root, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)

    inserted = skipped = 0
    errors = []
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            fixed = fix_chinese(info.filename)
            parts = [p for p in fixed.replace('\\', '/').split('/') if p]
            if not parts or any(p.startswith('.') or p.startswith('__MACOSX') for p in parts):
                continue
            fname = parts[-1]
            ext = os.path.splitext(fname)[1].lower()
            if ext not in VALID_EXTS:
                continue
            stem = os.path.splitext(fname)[0]
            student, title = parse_filename(stem)
            if not student:
                errors.append(f'解析失败: {fname}')
                continue
            grade = parts[-3] if len(parts) >= 3 else None
            klass = parts[-2] if len(parts) >= 2 else None

            safe_student = safe_segment(student)
            safe_title = safe_segment(title)
            dest_name = f'{safe_student}_{safe_title}{ext}'
            dest_path = os.path.join(dest_root, dest_name)
            if not (os.path.exists(dest_path) and os.path.getsize(dest_path) == info.file_size):
                with z.open(info) as src, open(dest_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)

            rel = f'assets/art-works/{award_name}/{dest_name}'
            try:
                conn.execute(
                    'INSERT INTO art_works(award_name, award_level, student_name, work_title, image_path, grade, class_name, uploaded_by) VALUES(?,?,?,?,?,?,?,?)',
                    (award_name, level, student, title, rel, grade, klass, 'cli')
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
    conn.commit()
    conn.close()
    return inserted, skipped, errors


def cmd_list():
    if not os.path.exists(DB_PATH):
        print('（数据库不存在）'); return
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)
    rows = conn.execute(
        'SELECT award_name, award_level, COUNT(*) FROM art_works GROUP BY award_name ORDER BY award_name'
    ).fetchall()
    total = conn.execute('SELECT COUNT(*) FROM art_works').fetchone()[0]
    conn.close()
    print(f'共 {total} 件作品')
    for aw, lv, n in rows:
        print(f'  · {aw}  [{lv}]  ·  {n} 件')


def cmd_clear(award_name):
    award_name = safe_segment(award_name)
    target = os.path.join(ART_DIR, award_name)
    if os.path.exists(target):
        shutil.rmtree(target)
        print(f'  已删除目录 {target}')
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)
    n = conn.execute('DELETE FROM art_works WHERE award_name = ?', (award_name,)).rowcount
    conn.commit()
    conn.close()
    print(f'  已删除记录 {n} 条')


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return
    if '--list' in args:
        cmd_list(); return
    if '--clear' in args:
        i = args.index('--clear')
        if i + 1 >= len(args):
            print('用法: --clear <奖项名>'); return
        cmd_clear(args[i + 1]); return

    zips = [a for a in args if not a.startswith('-')]
    if not zips:
        print(__doc__); return

    total_in = total_skip = 0
    all_errors = []
    for z in zips:
        print(f'▶ 处理 {z}…')
        ins, sk, errs = import_zip(z)
        print(f'  · 新增 {ins} 件 · 跳过 {sk} 件')
        total_in += ins
        total_skip += sk
        all_errors.extend(errs)
    print()
    print(f'✅ 共导入 {total_in} 件（跳过 {total_skip} 件已存在）')
    if all_errors:
        print(f'⚠️  {len(all_errors)} 个文件解析失败:')
        for e in all_errors[:10]:
            print(f'   · {e}')


if __name__ == '__main__':
    main()
