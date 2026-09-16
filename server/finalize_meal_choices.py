#!/usr/bin/env python3
"""每分钟检查本部/宝林已截止菜单，只将缺失的供餐日补为 A 餐。"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from server.app import app, get_db, _finalize_expired_meal_choices
from server import meal_history


def main():
    results = []
    with app.app_context():
        for campus in ('benbu', 'baolin'):
            results.append(
                _finalize_expired_meal_choices(get_db(campus), campus)
            )
            get_db(campus).commit()
        # Archive all campuses, without extending the existing default-A policy.
        for campus in ('benbu', 'baolin', 'luojing'):
            db = get_db(campus)
            if not meal_history.configured(db):
                continue
            db.execute('BEGIN IMMEDIATE')
            for menu in db.execute('SELECT * FROM weekly_menus').fetchall():
                if meal_history.closed(dict(menu)):
                    meal_history.snapshot(db, campus, menu)
            db.commit()
    print(json.dumps(results, ensure_ascii=False))


if __name__ == '__main__':
    main()
