#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抢课窗口截止后，钉钉工作通知对应校区总务老师过目确认。

设计：
- 由 cron 每 5 分钟执行一次（独立于 Flask 进程，多 worker 不会重复发）
- 只处理最近 7 天内截止且尚未通知过的窗口（club_notify_log 去重）
- 校区未配置总务 userId 或钉钉 agentId 时跳过并记日志，不报错
"""
import json
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from server.club_courses import SEMESTER  # noqa: E402  与主应用保持同一学期

CAMPUS_DBS = {
    'benbu': BASE / 'student_data.db',
    'baolin': BASE / 'campus_data' / 'baolin' / 'student_data.db',
    'luojing': BASE / 'campus_data' / 'luojing' / 'student_data.db',
}

# 与 server/app.py 的 CLUB_NOTIFY_GENERAL_USERIDS 保持一致；campus_config.json 的 clubNotifyUserIds 可覆盖
DEFAULT_NOTIFY_USERIDS = {
    'benbu': [],
    'baolin': [],
    'luojing': [],
}

CONFIG = json.loads((BASE / 'server' / 'campus_config.json').read_text(encoding='utf-8'))


def log(msg):
    print(f'[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}', flush=True)


def campus_cfg(campus):
    return CONFIG.get(campus, {}) if isinstance(CONFIG.get(campus), dict) else {}


def notify_userids(campus):
    ids = campus_cfg(campus).get('clubNotifyUserIds') or DEFAULT_NOTIFY_USERIDS.get(campus, [])
    return [str(u).strip() for u in ids if str(u).strip()]


def get_access_token(campus):
    cfg = campus_cfg(campus)
    app_key, app_secret = cfg.get('appKey'), cfg.get('appSecret')
    if not (app_key and app_secret):
        return None
    try:
        body = json.dumps({'appKey': app_key, 'appSecret': app_secret}).encode('utf-8')
        req = urllib.request.Request(
            'https://api.dingtalk.com/v1.0/oauth2/accessToken',
            data=body, headers={'Content-Type': 'application/json'}, method='POST')
        data = json.loads(urllib.request.urlopen(req, timeout=8).read().decode('utf-8'))
        return data.get('accessToken')
    except Exception as e:
        log(f'{campus}: 获取 access_token 失败 {e}')
        return None


def send_work_notification(campus, userids, title, text):
    agent_id = str(campus_cfg(campus).get('agentId') or '').strip()
    if not agent_id:
        log(f'{campus}: 未配置 agentId，无法发送工作通知')
        return False
    token = get_access_token(campus)
    if not token:
        return False
    msg = {
        'agent_id': int(agent_id) if agent_id.isdigit() else agent_id,
        'userid_list': ','.join(userids),
        'msg': {'msgtype': 'markdown', 'markdown': {'title': title, 'text': text}},
    }
    try:
        body = json.dumps(msg, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            f'https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2?access_token={token}',
            data=body, headers={'Content-Type': 'application/json'}, method='POST')
        result = json.loads(urllib.request.urlopen(req, timeout=8).read().decode('utf-8'))
        if result.get('errcode') == 0:
            log(f'{campus}: 通知发送成功 → {",".join(userids)}')
            return True
        log(f'{campus}: 通知发送失败 {result.get("errmsg")} (errcode={result.get("errcode")})')
    except Exception as e:
        log(f'{campus}: 通知发送异常 {e}')
    return False


def parse_dt(value):
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def grade_summary(db, grade):
    """统计某年级：可选课程数、报名人次、满员课程数。"""
    courses = db.execute(
        '''SELECT id, name, capacity, eligible_grades, grade_quotas, selection_mode
           FROM club_course_catalog WHERE semester = ? AND is_active = 1''',
        (SEMESTER,)
    ).fetchall()
    grade_counts = {
        r['course_id']: r['count'] for r in db.execute(
            '''SELECT course_id, COUNT(*) AS count FROM club_signups
               WHERE semester = ? AND status != 'rejected' AND grade = ?
               GROUP BY course_id''', (SEMESTER, grade)).fetchall()
    }
    total_counts = {
        r['course_id']: r['count'] for r in db.execute(
            '''SELECT course_id, COUNT(*) AS count FROM club_signups
               WHERE semester = ? AND status != 'rejected'
               GROUP BY course_id''', (SEMESTER,)).fetchall()
    }
    eligible = 0
    signups = 0
    full = 0
    for c in courses:
        try:
            grades = json.loads(c['eligible_grades'] or '[]')
        except (TypeError, ValueError):
            grades = []
        if c['selection_mode'] != 'selectable' or grade not in grades:
            continue
        eligible += 1
        signups += grade_counts.get(c['id'], 0)
        try:
            quotas = json.loads(c['grade_quotas']) if c['grade_quotas'] else {}
        except (TypeError, ValueError):
            quotas = {}
        if quotas:
            if grade_counts.get(c['id'], 0) >= int(quotas.get(grade, 0) or 0) > 0:
                full += 1
        elif total_counts.get(c['id'], 0) >= (c['capacity'] or 0):
            full += 1
    return eligible, signups, full


def main():
    now = datetime.now()
    for campus, db_path in CAMPUS_DBS.items():
        if not db_path.exists():
            continue
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        try:
            if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='club_admission_windows'"
            ).fetchone():
                continue
            db.execute('''CREATE TABLE IF NOT EXISTS club_notify_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                semester TEXT NOT NULL, campus TEXT NOT NULL,
                kind TEXT NOT NULL, ref TEXT NOT NULL, sent_to TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(semester, campus, kind, ref))''')
            userids = notify_userids(campus)
            windows = db.execute(
                'SELECT grade, close_at FROM club_admission_windows WHERE semester = ?',
                (SEMESTER,)
            ).fetchall()
            for w in windows:
                close_at = parse_dt(w['close_at'])
                if not close_at or close_at > now:
                    continue
                if now - close_at > timedelta(days=7):
                    continue  # 历史窗口不补发，避免部署时轰炸
                if not userids:
                    log(f'{campus}: {w["grade"]} 已截止但未配置总务 userId，跳过')
                    continue
                cur = db.execute(
                    '''INSERT OR IGNORE INTO club_notify_log(semester, campus, kind, ref, sent_to)
                       VALUES(?, ?, 'window_closed', ?, ?)''',
                    (SEMESTER, campus, w['grade'], ','.join(userids)))
                db.commit()
                if cur.rowcount == 0:
                    continue  # 已通知过
                eligible, signups, full = grade_summary(db, w['grade'])
                title = f'社团抢课已截止：{w["grade"]}'
                text = (
                    f'### ⏰ 抢课截止提醒\n\n'
                    f'**{w["grade"]}**的社团抢课已于 {close_at:%m-%d %H:%M} 截止。\n\n'
                    f'- 面向该年级的可选课程：{eligible} 门\n'
                    f'- 该年级报名总人次：{signups} 人次\n'
                    f'- 已满员课程：{full} 门\n'
                    f'- 学期：{SEMESTER}\n\n'
                    f'请进入「活动岛 → 社团抢课」查看报名名单，确认后发布录取结果。'
                )
                send_work_notification(campus, userids, title, text)
        finally:
            db.close()


if __name__ == '__main__':
    main()
