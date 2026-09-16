#!/usr/bin/env python3
"""Explicit, additive meal archive migration. Default is read-only dry-run."""
import argparse
import json
import sqlite3
from pathlib import Path

try:
    from . import meal_history as history
except ImportError:
    import meal_history as history


def run(root, campus, semester, apply=False, finalized_only=False):
    path = root/'student_data.db' if campus == 'benbu' else root/'campus_data'/campus/'student_data.db'
    db = sqlite3.connect(path.resolve().as_uri() + ('?mode=rw' if apply else '?mode=ro'), uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        current = history.configured(db)
        if current and current != semester:
            raise ValueError(f'{campus}: 当前学期为{current}，禁止直接覆盖；请另行审核换学期')
        rows = db.execute('SELECT * FROM weekly_menus ORDER BY week_number').fetchall()
        eligible, skipped, warnings = [], [], []
        for row in rows:
            if not row['date_start'] or history.semester_for(row['date_start']) != semester:
                skipped.append({'week':row['week_number'],'reason':'日期不在指定学期'})
                continue
            menu = history.menu_data(db,row)
            warnings.extend(menu['warnings'])
            if not history.closed(menu):
                continue
            if finalized_only and not dict(row).get('default_a_finalized_at'):
                continue
            if current and history.latest(db,semester,row['week_number']):
                continue
            eligible.append(row)
        report = {'campus':campus,'apply':apply,'semester':semester,
                  'archiveWeeks':[r['week_number'] for r in eligible], 'skipped':skipped,'warnings':warnings}
        if apply:
            history.migrate(db,semester)
            db.execute('BEGIN IMMEDIATE')
            # Reread within the write transaction; live writes may have occurred since dry-run.
            for old in eligible:
                row = db.execute('SELECT * FROM weekly_menus WHERE id=?',(old['id'],)).fetchone()
                if row and history.closed(history.menu_data(db,row)):
                    history.snapshot(db,campus,row,source='backfill',operator='migration',
                                     reason='现存菜单与选餐数据回填；不保证还原已被覆盖或删除的记录')
            db.commit()
        return report
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--campus', choices=['all','benbu','baolin','luojing'], default='all')
    parser.add_argument('--semester', required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--finalized-only',action='store_true', help='仅回填已完成截止补选的周次')
    args = parser.parse_args()
    campuses = ['benbu','baolin','luojing'] if args.campus=='all' else [args.campus]
    for campus in campuses:
        print(json.dumps(run(args.root,campus,args.semester,args.apply,args.finalized_only),ensure_ascii=False))


if __name__ == '__main__':
    main()
