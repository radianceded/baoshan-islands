# -*- coding: utf-8 -*-
"""
宝山实验智慧教育平台 - Flask API 服务
用于手动读写学生数据
"""
import os
import sys
import json
import sqlite3
import re
import time
import hmac
import base64
import ssl
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib import error as urllib_error
from flask import Flask, jsonify, request, g, make_response, send_from_directory, session, redirect, has_request_context
from flask_cors import CORS
from werkzeug.security import check_password_hash

try:
    from .club_courses import COURSES, SEMESTER as CLUB_SEMESTER
    from .menu_excel import MenuWorkbookError, parse_menu_workbook
except ImportError:
    from club_courses import COURSES, SEMESTER as CLUB_SEMESTER
    from menu_excel import MenuWorkbookError, parse_menu_workbook

# ==================== 启动时自动加载 server/.env ====================
def _load_env_file():
    """无需 python-dotenv：手动解析 server/.env,
       仅在环境变量未设置时填充，让 shell export 仍然优先。"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
_load_env_file()

# ==================== 校区物理隔离：按 campus 返回对应表名 ====================
ALLOWED_CAMPUSES = frozenset(('benbu', 'baolin', 'luojing'))


def _valid_campus(value, default=None):
    campus = str(value or '').strip().lower()
    return campus if campus in ALLOWED_CAMPUSES else default


def _students_table(campus_id=None):
    """按校区返回对应学生表：benbu→students_benbu，luojing→students_luojing，其他→students"""
    if campus_id == 'benbu':
        return 'students_benbu'
    if campus_id == 'baolin':
        return 'students_baolin'
    if campus_id == 'luojing':
        return 'students_luojing'
    return 'students'

def _teacher_roster_table(campus_id=None):
    """按校区返回对应教师表：benbu→teacher_roster_benbu，luojing→teacher_roster_luojing，其他→teacher_roster"""
    if campus_id == 'benbu':
        return 'teacher_roster_benbu'
    if campus_id == 'baolin':
        return 'teacher_roster_baolin'
    if campus_id == 'luojing':
        return 'teacher_roster_luojing'
    return 'teacher_roster'

def _resolve_campus():
    """从多个来源解析当前请求的校区：session token > query param > 默认 benbu"""
    # 1) 从 session token 中取
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        info = _verify_session(auth[7:])
        if info and _valid_campus(info.get('campus')):
            return _valid_campus(info['campus'])
    # 2) 从 query param 中取
    campus = (request.args.get('campus') or '').strip()
    if _valid_campus(campus):
        return _valid_campus(campus)
    # 3) 默认本部
    return 'benbu'

def _ensure_session_secret():
    """启动时若 .env 没有 SESSION_SECRET,生成一个并写回(确保重启不掉登录)"""
    if os.environ.get('SESSION_SECRET'):
        return
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    new_secret = secrets.token_hex(32)
    os.environ['SESSION_SECRET'] = new_secret
    try:
        # 追加到 .env,避免覆盖已有内容
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                txt = f.read()
            if 'SESSION_SECRET' not in txt:
                with open(env_path, 'a', encoding='utf-8') as f:
                    f.write(f'\n# 自动生成(请勿外泄)\nSESSION_SECRET={new_secret}\n')
        else:
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write(f'SESSION_SECRET={new_secret}\n')
    except Exception as e:
        print(f'[警告] SESSION_SECRET 无法写回 .env: {e}', flush=True)
_ensure_session_secret()

# ==================== 配置 ====================
# 文本 AI：优先复用本机 DeepSeek Key；未配置时兼容原百度千帆配置。
_DEEPSEEK_AI_KEY = os.environ.get('DEEPSEEK_API_KEY', '').strip()
_BAIDU_AI_KEY = os.environ.get('BAIDU_AI_KEY', '').strip()
if _DEEPSEEK_AI_KEY:
    AI_PROVIDER = 'deepseek'
    AI_API_KEY = _DEEPSEEK_AI_KEY
    AI_MODEL = os.environ.get('DEEPSEEK_AI_MODEL', 'deepseek-v4-pro')
    AI_URL = os.environ.get(
        'DEEPSEEK_AI_URL',
        'https://api.deepseek.com/chat/completions',
    )
else:
    AI_PROVIDER = 'baidu'
    AI_API_KEY = _BAIDU_AI_KEY
    AI_MODEL = os.environ.get('BAIDU_AI_MODEL', 'ernie-5.1')
    AI_URL = os.environ.get(
        'BAIDU_AI_URL',
        'https://qianfan.baidubce.com/v2/chat/completions',
    )

# 奖状图片识别仍使用原视觉模型；DeepSeek 文本 Key 不冒充视觉能力。
VISION_AI_API_KEY = _BAIDU_AI_KEY
VISION_AI_MODEL = os.environ.get('BAIDU_VISION_MODEL', 'ernie-4.5-8k-preview')
VISION_AI_URL = os.environ.get(
    'BAIDU_AI_URL',
    'https://qianfan.baidubce.com/v2/chat/completions',
)

DINGTALK_AGENT_ID = os.environ.get('DINGTALK_AGENT_ID', '').strip()
DINGTALK_APP_KEY = os.environ.get('DINGTALK_APP_KEY', '').strip()
DINGTALK_APP_SECRET = os.environ.get('DINGTALK_APP_SECRET', '').strip()
DINGTALK_CORP_ID = os.environ.get('DINGTALK_CORP_ID', '').strip()
SESSION_SECRET = os.environ['SESSION_SECRET']

# ==================== 多校区钉钉配置 ====================
_CAMPUS_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'campus_config.json')
_campus_config_cache = None
_campus_config_mtime = 0

def _load_campus_config():
    """加载 campus_config.json，支持热更新（文件修改后自动重载）"""
    global _campus_config_cache, _campus_config_mtime
    try:
        mtime = os.path.getmtime(_CAMPUS_CONFIG_PATH)
        if _campus_config_cache is None or mtime > _campus_config_mtime:
            with open(_CAMPUS_CONFIG_PATH, 'r', encoding='utf-8') as f:
                _campus_config_cache = json.load(f)
            _campus_config_mtime = mtime
    except Exception:
        if _campus_config_cache is None:
            _campus_config_cache = {}
    return _campus_config_cache

def _get_campus_dt(campus_id):
    """获取校区的钉钉配置。如果 campus_config.json 未配置，回退到 .env 全局配置"""
    cfg = _load_campus_config()
    campus = cfg.get(campus_id, {})
    app_key = campus.get('appKey') or DINGTALK_APP_KEY
    app_secret = campus.get('appSecret') or DINGTALK_APP_SECRET
    corp_id = campus.get('corpId') or DINGTALK_CORP_ID
    school_name = campus.get('school_name', '')
    return {
        'appKey': app_key,
        'appSecret': app_secret,
        'corpId': corp_id,
        'school_name': school_name,
        'name': campus.get('name', campus_id),
    }


def _grade_sort_sql(col='grade_name'):
    """按中文年级名数字顺序排序的 CASE 表达式"""
    return f"""CASE {col}
        WHEN '一年级' THEN 1
        WHEN '二年级' THEN 2
        WHEN '三年级' THEN 3
        WHEN '四年级' THEN 4
        WHEN '五年级' THEN 5
        WHEN '六年级' THEN 6
        WHEN '七年级' THEN 7
        WHEN '八年级' THEN 8
        WHEN '九年级' THEN 9
        ELSE 99
    END"""

# 运行模式 + 跨域白名单
DEBUG = os.environ.get('DEBUG', '').lower() in ('1', 'true', 'yes', 'on')
_default_origins = '*' if DEBUG else ''
CORS_ORIGINS = [o.strip() for o in os.environ.get('CORS_ORIGINS', _default_origins).split(',') if o.strip()]

# 上传与限流
MAX_UPLOAD_MB = int(os.environ.get('MAX_UPLOAD_MB', '1024'))
UPLOAD_RATE_PER_MIN = int(os.environ.get('UPLOAD_RATE_PER_MIN', '5'))

# 生产模式禁用 demo 旁路(?role= 直接拿 admin)
# DISABLE_DEMO=true 时,_current_user 忽略 demo headers/params,仅认 Bearer token
PASSWORD_LOGIN_ONLY = os.environ.get('PASSWORD_LOGIN_ONLY', 'true').lower() in ('1', 'true', 'yes', 'on')
DISABLE_DEMO = PASSWORD_LOGIN_ONLY or os.environ.get('DISABLE_DEMO', '').lower() in ('1', 'true', 'yes', 'on')
REQUIRE_STUDENT_USERID = os.environ.get('REQUIRE_STUDENT_USERID', '').lower() in ('1', 'true', 'yes', 'on')

# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'student_data.db')
AUTH_DB_PATH = os.environ.get('AUTH_DB_PATH') or os.path.join(BASE_DIR, 'auth_accounts.db')
BAOLIN_DATA_DIR = os.environ.get('BAOLIN_DATA_DIR') or os.path.join(BASE_DIR, 'campus_data', 'baolin')
BAOLIN_DB_PATH = os.environ.get('BAOLIN_DB_PATH') or os.path.join(BAOLIN_DATA_DIR, 'student_data.db')
BAOLIN_AUTH_DB_PATH = os.environ.get('BAOLIN_AUTH_DB_PATH') or os.path.join(BAOLIN_DATA_DIR, 'auth_accounts.db')
ACCOUNT_SESSION_TTL = int(os.environ.get('ACCOUNT_SESSION_TTL', str(90 * 24 * 60 * 60)))
app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')
app.config['NUTRITION_ALLOW_DEMO_HEADERS'] = not DISABLE_DEMO
# 儿童营养餐智能分配系统
import sys as _sys_nutrition
_sys_nutrition.path.insert(0, os.path.join(BASE_DIR, "nutrition"))
from nutrition import init_app as init_nutrition
init_nutrition(app)
app.secret_key = SESSION_SECRET  # 启用 Flask session（双角色切换用）
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_MB * 1024 * 1024
if CORS_ORIGINS:
    CORS(app, origins=CORS_ORIGINS, supports_credentials=True)
else:
    pass  # 生产 + 未配置白名单 → 仅放行同源

# 启动时确保核心表存在
try:
    _startup_db = sqlite3.connect(DB_PATH)
    _startup_db.row_factory = sqlite3.Row
    _startup_db.execute('''CREATE TABLE IF NOT EXISTS user_bindings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dingtalk_unionid TEXT UNIQUE,
        role TEXT NOT NULL DEFAULT 'parent',
        sub_role TEXT,
        bound_id_card TEXT,
        bound_grade TEXT,
        bound_class TEXT,
        bound_name TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    # ==================== 统一事件流表（6岛数字画像数据底座）====================
    _startup_db.execute('''CREATE TABLE IF NOT EXISTS unified_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL,
        student_name TEXT,
        grade TEXT,
        class_name TEXT,
        campus TEXT DEFAULT '',
        island TEXT NOT NULL,
        branch TEXT NOT NULL,
        event_type TEXT NOT NULL,
        event_data TEXT,
        event_summary TEXT,
        event_date TEXT,
        school_year TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    _startup_db.execute('CREATE INDEX IF NOT EXISTS idx_ue_student ON unified_events(student_id)')
    _startup_db.execute('CREATE INDEX IF NOT EXISTS idx_ue_island ON unified_events(island, branch)')
    _startup_db.execute('CREATE INDEX IF NOT EXISTS idx_ue_campus ON unified_events(campus)')
    # ==================== 心情管理表（Phase 2）====================
    _startup_db.execute('''CREATE TABLE IF NOT EXISTS mood_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL,
        student_name TEXT,
        grade TEXT, class_name TEXT, campus TEXT DEFAULT '',
        source TEXT NOT NULL CHECK(source IN ('zhixin_jiejie','mentor','system','ai_alert')),
        type TEXT NOT NULL CHECK(type IN ('self_report','teacher_observation','ai_alert','escalation')),
        severity INTEGER NOT NULL CHECK(severity BETWEEN 1 AND 5),
        content TEXT NOT NULL,
        tags TEXT,
        recorded_by TEXT,
        visibility TEXT DEFAULT '1,2',
        status TEXT DEFAULT 'open' CHECK(status IN ('open','tracking','resolved')),
        linked_event_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    _startup_db.execute('CREATE INDEX IF NOT EXISTS idx_mood_student ON mood_events(student_id)')
    _startup_db.execute('CREATE INDEX IF NOT EXISTS idx_mood_severity ON mood_events(severity, status)')
    _startup_db.execute('CREATE INDEX IF NOT EXISTS idx_mood_campus ON mood_events(campus)')
    _startup_db.execute('''CREATE TABLE IF NOT EXISTS mood_escalations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mood_event_id INTEGER NOT NULL,
        escalated_to TEXT,
        escalated_by TEXT,
        reason TEXT,
        action_taken TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (mood_event_id) REFERENCES mood_events(id)
    )''')
    _startup_db.execute('''CREATE TABLE IF NOT EXISTS mood_authorizations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL,
        parent_consent INTEGER DEFAULT 0,
        student_consent INTEGER DEFAULT 0,
        authorized_at TEXT,
        UNIQUE(student_id)
    )''')
    _startup_db.execute('''CREATE TABLE IF NOT EXISTS mood_weekly_reports(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campus TEXT, grade TEXT, class_name TEXT,
        report_week TEXT NOT NULL,
        report_data TEXT,
        ai_generated INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    _startup_db.commit()
    _startup_db.close()
except Exception as _e:
    import logging
    logging.warning(f'[startup] user_bindings init: {_e}')

    CORS(app, origins=[], supports_credentials=True)

# ==================== 日志 ====================
import logging
from logging.handlers import TimedRotatingFileHandler
_LOG_DIR = os.environ.get('LOG_DIR', os.path.join(BASE_DIR, 'logs'))
os.makedirs(_LOG_DIR, exist_ok=True)

def _setup_logging():
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s :: %(message)s')
    access_h = TimedRotatingFileHandler(os.path.join(_LOG_DIR, 'access.log'), when='midnight', backupCount=14, encoding='utf-8')
    access_h.setFormatter(fmt); access_h.setLevel(logging.INFO)
    error_h = TimedRotatingFileHandler(os.path.join(_LOG_DIR, 'error.log'), when='midnight', backupCount=30, encoding='utf-8')
    error_h.setFormatter(fmt); error_h.setLevel(logging.WARNING)
    # Flask / Werkzeug
    for name in ('werkzeug', 'gunicorn.access'):
        lg = logging.getLogger(name); lg.addHandler(access_h)
    app.logger.addHandler(error_h); app.logger.setLevel(logging.INFO)
    logging.getLogger().addHandler(error_h)
_setup_logging()

# ==================== 上传频率限制(简易,进程内) ====================
# ⚠️ 注意:in-memory bucket 不在多进程间共享。
# gunicorn -w N 时实际限额 = N × UPLOAD_RATE_PER_MIN。
# 试点期(单进程或 -w 1)够用;全量上线建议接 Redis(参考 docs/钉钉上线就绪说明.md)
from collections import defaultdict, deque
_upload_buckets = defaultdict(deque)
def _rate_check(key, limit=UPLOAD_RATE_PER_MIN, window=60):
    now = time.time()
    bucket = _upload_buckets[key]
    while bucket and bucket[0] < now - window:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True

@app.errorhandler(413)
def _too_large(e):
    return jsonify({'error': f'文件过大(单次上传 ≤ {MAX_UPLOAD_MB} MB)'}), 413

# ==================== 隐私保护 - 姓名去敏 ====================

# 去敏配置
ANONYMIZATION_CONFIG = {
    'enabled': True,  # 是否启用去敏
    'mode': 'mask',   # mask: 张三->张**, random: 随机姓名
    'name_mapping': {}  # 真实姓名到去敏姓名的映射缓存
}

# 隐私字段列表（需要处理的字段名）
PRIVACY_FIELDS = ['name', 'student_name', 'real_name', '姓名', '学生姓名']

def mask_name(name):
    """
    对姓名进行脱敏处理
    张三 -> 张**
    王五 -> 王*
    """
    if not name or not isinstance(name, str):
        return name
    
    if name in ANONYMIZATION_CONFIG['name_mapping']:
        return ANONYMIZATION_CONFIG['name_mapping'][name]
    
    # 脱敏规则：保留姓氏，其余替换为*
    if len(name) <= 1:
        masked = name
    else:
        masked = name[0] + '*' * (len(name) - 1)
    
    ANONYMIZATION_CONFIG['name_mapping'][name] = masked
    return masked

def anonymize_data(data):
    """
    递归处理数据结构，对隐私字段进行去敏
    支持 dict, list 类型
    """
    if not ANONYMIZATION_CONFIG['enabled']:
        return data
    
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            # 如果键名匹配隐私字段，对值进行去敏
            if key in PRIVACY_FIELDS and isinstance(value, str):
                result[key] = mask_name(value)
            else:
                result[key] = anonymize_data(value)
        return result
    elif isinstance(data, list):
        return [anonymize_data(item) for item in data]
    else:
        return data

def anonymize_response(f):
    """
    装饰器：自动对 API 响应进行去敏处理。
    例外：家长查看自己绑定的孩子时，返回真实姓名。
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        response = f(*args, **kwargs)
        
        # 处理不同类型的响应
        if isinstance(response, tuple):
            data, status_code = response[0], response[1] if len(response) > 1 else 200
            # 如果是 jsonify 对象，提取数据
            if hasattr(data, 'get_json'):
                data = data.get_json()
        elif hasattr(response, 'get_json'):
            data = response.get_json()
            status_code = response.status_code
        else:
            return response
        
        # 检查是否请求不打码（钉钉微应用等内部场景）
        if request.args.get('nomask') == '1':
            return jsonify(data), status_code if isinstance(response, tuple) else 200
        
        # 检查是否是家长查看自己绑定的孩子 → 跳过姓名去敏
        try:
            u = _current_user();
            if u['role'] == 'parent' and u['bound_id_card']:
                resp_id = data.get('id_card') if isinstance(data, dict) else None
                resp_name = data.get('name') if isinstance(data, dict) else None
                # 精确匹配（BS 格式）
                if resp_id and resp_id == u['bound_id_card']:
                    return jsonify(data), status_code if isinstance(response, tuple) else 200
                # G 格式 → 姓名映射
                if resp_name:
                    db = get_db()
                    acct = db.execute('SELECT kid_name FROM accounts WHERE bound_id_card = ?', (u['bound_id_card'],)).fetchone()
                    if acct and acct['kid_name'] == resp_name:
                        return jsonify(data), status_code if isinstance(response, tuple) else 200
        except Exception:
            pass
        
        # 进行去敏处理
        anonymized_data = anonymize_data(data)
        
        return jsonify(anonymized_data), status_code if isinstance(response, tuple) else 200
    
    return decorated_function

def _campus_db_path(campus_id, auth=False):
    campus = _valid_campus(campus_id, 'benbu')
    if campus == 'baolin':
        return BAOLIN_AUTH_DB_PATH if auth else BAOLIN_DB_PATH
    return AUTH_DB_PATH if auth else DB_PATH


def _open_existing_campus_db(path, campus):
    # 本部沿用历史行为；新校区必须预先部署独立库，禁止请求自动创建空库。
    if campus != 'benbu' and not os.path.isfile(path):
        raise sqlite3.OperationalError(f'{campus} database is not provisioned')
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return db


def get_db(campus_id=None):
    requested = campus_id or (_resolve_campus() if has_request_context() else None)
    campus = _valid_campus(requested, 'benbu')
    key = f'db_{campus}'
    if key not in g:
        setattr(g, key, _open_existing_campus_db(_campus_db_path(campus), campus))
    return getattr(g, key)


def get_auth_db(campus_id=None):
    """校区独立认证库；绝不在业务库中创建或更新账号。"""
    requested = campus_id or (_resolve_campus() if has_request_context() else None)
    campus = _valid_campus(requested, 'benbu')
    key = f'auth_db_{campus}'
    if key not in g:
        setattr(g, key, _open_existing_campus_db(_campus_db_path(campus, auth=True), campus))
    return getattr(g, key)

@app.teardown_appcontext
def close_db(exception):
    for campus in ALLOWED_CAMPUSES:
        for prefix in ('db', 'auth_db'):
            db = g.pop(f'{prefix}_{campus}', None)
            if db is not None:
                db.close()

# ==================== 学生数据 API ====================

@app.route('/api/students', methods=['GET'])
@anonymize_response
def get_students():
    """老师 / 管理员：返回全部学生；家长：只返回自己绑定的那个孩子"""
    u = _current_user(); role, bound = u['role'], u['bound_id_card']
    if role == 'none':
        return jsonify({'students': [], 'total': 0, 'message': '请先登录'})
    db = get_db()
    base = 'SELECT s.*, f.test_year, f.total_score, f.total_level, f.bmi_level, f.height, f.weight, f.bmi FROM students s LEFT JOIN fitness_tests f ON s.id_card = f.id_card AND f.test_year = (SELECT MAX(test_year) FROM fitness_tests WHERE id_card = s.id_card)'

    if role == 'parent':
        if not bound:
            return jsonify({'students': [], 'total': 0, 'role': role,
                            'message': '家长账号未绑定学生，请联系班主任'})
        cursor = db.execute(base + ' WHERE s.id_card = ?', (bound,))
        students = [dict(row) for row in cursor.fetchall()]
        return jsonify({'students': students, 'total': len(students), 'role': role})

    # teacher / admin
    grade = request.args.get('grade')
    keyword = request.args.get('keyword')
    school = request.args.get('school')
    query = base
    where_clauses = []
    params = []
    if grade:
        where_clauses.append('s.grade_name = ?')
        params.append(grade)
    if school:
        where_clauses.append('s.school_name = ?')
        params.append(school)
    if keyword:
        where_clauses.append('(s.name LIKE ? OR s.id_card LIKE ?)')
        params.extend([f'%{keyword}%', f'%{keyword}%'])
    if where_clauses:
        query += ' WHERE ' + ' AND '.join(where_clauses)
    query += ' ORDER BY s.class_name, s.name'
    cursor = db.execute(query, params)
    students = [dict(row) for row in cursor.fetchall()]
    return jsonify({'students': students, 'total': len(students), 'role': role})

@app.route('/api/students/<id_card>', methods=['GET'])
@anonymize_response
def get_student(id_card):
    """获取单个学生详情（接受 BS 或 G 格式 id_card）"""
    db = get_db()
    u = _current_user()
    campus = _resolve_campus()
    stable = _students_table(campus)

    # 宽松权限检查
    if not _require_can_see(id_card):
        # 家长：G格式 id_card → 查 accounts.kid_name 映射
        ok = False
        if u['role'] == 'parent' and u['bound_id_card']:
            acct = db.execute('SELECT kid_name FROM accounts WHERE bound_id_card = ?', (u['bound_id_card'],)).fetchone()
            if acct:
                stu = db.execute(f'SELECT id_card FROM {stable} WHERE name = ?', (acct['kid_name'],)).fetchone()
                if stu and stu['id_card'] == id_card:
                    ok = True
        if not ok:
            return jsonify({'error': '无权限查看该学生'}), 403

    # 基础信息（校区隔离）
    cursor = db.execute(f'SELECT * FROM {stable} WHERE id_card = ?', (id_card,))
    student = cursor.fetchone()
    # G 格式 id_card 找不到？通过 accounts → kid_name 反查
    if student is None:
        acct = db.execute('SELECT kid_name FROM accounts WHERE bound_id_card = ?', (id_card,)).fetchone()
        if acct:
            cursor = db.execute(f'SELECT * FROM {stable} WHERE name = ?', (acct['kid_name'],))
            student = cursor.fetchone()
    if student is None:
        return jsonify({'error': '学生不存在'}), 404
    
    student_dict = dict(student)
    # 用学生真实的 id_card 和 name 做后续查询（兼容 G 格式 → BS 格式映射）
    real_id = student_dict['id_card']
    real_name = student_dict['name']
    
    # 体质数据（按学生姓名匹配）
    cursor = db.execute('SELECT * FROM fitness_tests WHERE name = ? ORDER BY test_year ASC', (real_name,))
    student_dict['fitness'] = [dict(row) for row in cursor.fetchall()]

    # 屈光数据
    cursor = db.execute('SELECT * FROM vision_tests WHERE name = ? ORDER BY test_date ASC', (real_name,))
    student_dict['vision'] = [dict(row) for row in cursor.fetchall()]

    # 体检数据
    try:
        cursor = db.execute('SELECT * FROM physical_exams WHERE name = ? ORDER BY exam_year ASC', (real_name,))
        student_dict['physical_exams'] = [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        student_dict['physical_exams'] = []

    # 过敏数据
    cursor = db.execute('SELECT * FROM allergies WHERE id_card = ?', (real_id,))
    student_dict['allergies'] = [dict(row) for row in cursor.fetchall()]

    # 获奖数据（按学生姓名）
    cursor = db.execute('SELECT * FROM awards WHERE name = ?', (real_name,))
    student_dict['awards'] = [dict(row) for row in cursor.fetchall()]

    # 班级证书（校区隔离）
    # 旧数据 campus 为空视为本部；新数据严格匹配 campus
    if campus == 'benbu':
        cursor = db.execute('''SELECT * FROM award_certs
                               WHERE (student_id_card = ? OR student_name = ?)
                                 AND (campus = ? OR campus = "" OR campus IS NULL)
                               ORDER BY grade, class_name''', (real_id, real_name, campus))
    else:
        cursor = db.execute('''SELECT * FROM award_certs
                               WHERE (student_id_card = ? OR student_name = ?)
                                 AND campus = ?
                               ORDER BY grade, class_name''', (real_id, real_name, campus))
    student_dict['award_certs'] = [dict(row) for row in cursor.fetchall()]

    # 社团数据
    cursor = db.execute('SELECT * FROM clubs WHERE student_name = ? ORDER BY school_year ASC', (real_name,))
    student_dict['clubs'] = [dict(row) for row in cursor.fetchall()]

    # 午餐选餐数据
    cursor = db.execute('SELECT * FROM meal_choices WHERE id_card = ? OR name = ? ORDER BY week_number DESC, parity, weekday', (real_id, real_name))
    student_dict['meal_choices'] = [dict(row) for row in cursor.fetchall()]

    return jsonify(student_dict)

@app.route('/api/students/name/<name>', methods=['GET'])
def get_student_by_name(name):
    """按学生姓名查详情（家长找不到 id_card 时的兜底）"""
    db = get_db()
    # 找该姓名的第一个学生
    row = db.execute('SELECT id_card FROM students WHERE name = ? LIMIT 1', (name,)).fetchone()
    if not row:
        return jsonify({'error': '学生不存在'}), 404
    return get_student(row['id_card'])

@app.route('/api/students', methods=['POST'])
def create_student():
    """添加新学生（入库明文存储，返回数据会脱敏）"""
    data = request.get_json()
    db = get_db()
    
    required = ['id_card', 'name']
    for field in required:
        if field not in data:
            return jsonify({'error': f'缺少必填字段: {field}'}), 400
    
    # 检查学号唯一性
    cursor = db.execute('SELECT id_card FROM students WHERE id_card = ?', (data.get('id_card'),))
    if cursor.fetchone():
        return jsonify({'error': '学号已存在'}), 400
    
    # 检查姓名长度
    name = data.get('name', '').strip()
    if len(name) < 2 or len(name) > 10:
        return jsonify({'error': '姓名长度需在2-10个字符之间'}), 400
    
    try:
        # 校验 id_card 格式（学籍号通常为19位数字）
        id_card = data.get('id_card', '').strip()
        if not re.match(r'^\d{10,20}$', id_card):
            return jsonify({'error': '学号格式不正确，应为10-20位数字'}), 400
        
        cursor = db.execute('''
            INSERT INTO students (id_card, name, gender, birth_date, grade_name, class_name, school_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ''', (
            id_card,
            name,
            data.get('gender', ''),
            data.get('birth_date', ''),
            data.get('grade_name', ''),
            data.get('class_name', ''),
            data.get('school_name', '宝山实验小学')
        ))
        db.commit()
        
        # 批量插入过敏信息
        allergies = data.get('allergies', [])
        for allergen in allergies:
            if allergen and allergen.strip():
                db.execute('''
                    INSERT INTO allergies (id_card, allergen, source, created_at)
                    VALUES (?, ?, '系统录入', datetime('now'))
                ''', (id_card, allergen.strip()))
        db.commit()
        
        return jsonify({
            'id_card': id_card,
            'display_name': mask_name(name),
            'message': '添加成功'
        })
    except sqlite3.IntegrityError:
        return jsonify({'error': '学生ID已存在'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/students/<id_card>', methods=['PUT'])
def update_student(id_card):
    """更新学生信息"""
    data = request.get_json()
    db = get_db()
    
    # 检查学生是否存在
    cursor = db.execute('SELECT id_card FROM students WHERE id_card = ?', (id_card,))
    if not cursor.fetchone():
        return jsonify({'error': '学生不存在'}), 404
    
    fields = []
    values = []
    allowed_fields = ['name', 'gender', 'birth_date', 'grade_name', 'class_name', 'school_name']
    
    for field in allowed_fields:
        if field in data:
            fields.append(f'{field} = ?')
            values.append(data[field])
    
    if not fields:
        return jsonify({'error': '没有要更新的字段'}), 400
    
    values.append(id_card)
    
    db.execute(f'UPDATE students SET {", ".join(fields)} WHERE id_card = ?', values)
    db.commit()
    
    # 更新过敏信息
    if 'allergies' in data:
        db.execute('DELETE FROM allergies WHERE id_card = ?', (id_card,))
        for allergen in data['allergies']:
            if allergen and allergen.strip():
                db.execute('''
                    INSERT INTO allergies (id_card, allergen, source, created_at)
                    VALUES (?, ?, '系统更新', datetime('now'))
                ''', (id_card, allergen.strip()))
        db.commit()
    
    return jsonify({'message': '更新成功'})

@app.route('/api/students/<id_card>', methods=['DELETE'])
def delete_student(id_card):
    """软删除学生（标记删除而非真删除）"""
    db = get_db()
    
    cursor = db.execute('SELECT id_card, name FROM students WHERE id_card = ?', (id_card,))
    student = cursor.fetchone()
    if student is None:
        return jsonify({'error': '学生不存在'}), 404
    
    # 使用 soft delete 标记
    db.execute('UPDATE students SET name = name || " [已注销]" WHERE id_card = ?', (id_card,))
    db.commit()
    
    return jsonify({'message': '学生已标记为注销状态'})

# ==================== 体质数据 API ====================

@app.route('/api/fitness', methods=['GET'])
@anonymize_response
def get_fitness():
    """获取体质测试数据（家长仅能看自己孩子）"""
    u = _current_user(); role, bound = u['role'], u['bound_id_card']
    db = get_db()
    id_card = request.args.get('id_card')
    # 家长强制锁定到自己孩子
    if role == 'parent':
        if not bound:
            return jsonify([])
        id_card = bound
    if id_card:
        if not _require_can_see(id_card):
            return jsonify({'error': '无权限'}), 403
        cursor = db.execute('''
            SELECT ft.*, s.name, s.class_name, s.grade_name
            FROM fitness_tests ft
            JOIN students s ON ft.id_card = s.id_card
            WHERE ft.id_card = ? ORDER BY ft.test_year DESC
        ''', (id_card,))
    else:
        cursor = db.execute('''
            SELECT ft.*, s.name, s.class_name, s.grade_name
            FROM fitness_tests ft
            JOIN students s ON ft.id_card = s.id_card
            ORDER BY ft.id DESC LIMIT 500
        ''')
    fitness = [dict(row) for row in cursor.fetchall()]
    return jsonify(fitness)

@app.route('/api/fitness', methods=['POST'])
def add_fitness():
    """添加体质测试数据"""
    data = request.get_json()
    db = get_db()
    
    cursor = db.execute('''
        INSERT INTO fitness_tests (id_card, test_year, height, weight, bmi, bmi_level,
            vital_capacity, vital_level, run_50m, run_50m_level, sit_reach, sit_reach_level,
            jump_stand, jump_stand_level, jump_rope, jump_rope_level, sit_up, sit_up_level,
            total_score, total_level, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    ''', (
        data.get('id_card'), data.get('test_year'), data.get('height'),
        data.get('weight'), data.get('bmi'), data.get('bmi_level'),
        data.get('vital_capacity'), data.get('vital_level'),
        data.get('run_50m'), data.get('run_50m_level'),
        data.get('sit_reach'), data.get('sit_reach_level'),
        data.get('jump_stand'), data.get('jump_stand_level'),
        data.get('jump_rope'), data.get('jump_rope_level'),
        data.get('sit_up'), data.get('sit_up_level'),
        data.get('total_score'), data.get('total_level')
    ))
    db.commit()
    return jsonify({'id': cursor.lastrowid, 'message': '添加成功'})

# ==================== 屈光数据 API ====================

@app.route('/api/vision', methods=['GET'])
def get_vision():
    """获取屈光数据"""
    db = get_db()
    id_card = request.args.get('id_card')
    if id_card:
        cursor = db.execute('SELECT * FROM vision_tests WHERE id_card = ? ORDER BY test_date DESC', (id_card,))
    else:
        cursor = db.execute('SELECT * FROM vision_tests ORDER BY id DESC')
    vision = [dict(row) for row in cursor.fetchall()]
    return jsonify(vision)

# ==================== 菜单数据 API ====================

@app.route('/api/menu', methods=['GET'])
def get_menu():
    """获取AB餐菜单"""
    db = get_db()
    week = request.args.get('week')
    if week:
        cursor = db.execute('SELECT * FROM ab_menus WHERE week_number = ?', (week,))
    else:
        cursor = db.execute('SELECT * FROM ab_menus ORDER BY week_number DESC, menu_date ASC')
    menu = [dict(row) for row in cursor.fetchall()]
    return jsonify(menu)

# ==================== 统计 API ====================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """获取统计数据"""
    db = get_db()
    
    # 学生总数
    cursor = db.execute('SELECT COUNT(*) as total FROM students')
    total_students = cursor.fetchone()['total']
    
    # 各年级人数
    cursor = db.execute('SELECT grade_name, COUNT(*) as count FROM students GROUP BY grade_name')
    grade_stats = {row['grade_name']: row['count'] for row in cursor.fetchall() if row['grade_name']}
    
    # 隐私保护状态
    cursor = db.execute('SELECT COUNT(DISTINCT id_card) as total FROM allergies')
    allergy_count = cursor.fetchone()['total']
    
    return jsonify({
        'total_students': total_students,
        'grade_stats': grade_stats,
        'students_with_allergies': allergy_count,
        'privacy_mode': ANONYMIZATION_CONFIG['enabled']
    })

# ==================== 隐私控制 API ====================

@app.route('/api/privacy/toggle', methods=['POST'])
def toggle_privacy():
    """切换去敏模式（用于测试和授权查看）"""
    data = request.get_json() or {}
    enable = data.get('enable')
    
    if enable is not None:
        ANONYMIZATION_CONFIG['enabled'] = bool(enable)
    else:
        ANONYMIZATION_CONFIG['enabled'] = not ANONYMIZATION_CONFIG['enabled']
    
    return jsonify({
        'enabled': ANONYMIZATION_CONFIG['enabled'],
        'message': '姓名脱敏已' + ('开启' if ANONYMIZATION_CONFIG['enabled'] else '关闭')
    })

@app.route('/api/privacy/status', methods=['GET'])
def get_privacy_status():
    """获取隐私保护状态"""
    return jsonify({
        'enabled': ANONYMIZATION_CONFIG['enabled'],
        'mode': ANONYMIZATION_CONFIG['mode'],
        'cached_names': len(ANONYMIZATION_CONFIG['name_mapping'])
    })

# ==================== 登录 API ====================

def _ensure_accounts_table():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS accounts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        sub_role TEXT,
        bound_id_card TEXT,
        bound_grade TEXT,
        bound_class TEXT,
        kid_name TEXT,
        demo_idx INTEGER,
        display_name TEXT,
        dingtalk_unionid TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    db.commit()

def _hash_pwd(p):
    """演示阶段：SHA-256 + 固定盐。生产可换 bcrypt。"""
    return hashlib.sha256(('bs_salt_2026:' + (p or '')).encode()).hexdigest()

LOGIN_ENTRY_ROLES = {
    'general_teacher': ('teacher', 'general'),
    'class_teacher': ('teacher', 'class'),
    'parent': ('parent', None),
}

# 指定总务名单：钉钉组织内 userId → 姓名。
# 这些老师用钉钉免登进入时，强制识别为总务（role=teacher, sub_role='general'）。
# 依据是 dingtalk_userid（兑码得到的 userId），而非 unionId，因为 userId 是教师名单里的稳定键。
def _env_userid_set(name):
    return frozenset(
        value.strip() for value in os.environ.get(name, '').split(',')
        if value.strip()
    )


# 真实教师 UserID 只在部署环境配置，不进入公开仓库。
GENERAL_TEACHER_BY_USERID = _env_userid_set('GENERAL_TEACHER_USERIDS')

# 本部班主任/家长双身份切换白名单。
BENBU_DUAL_ROLE_TEACHER_USERIDS = _env_userid_set('BENBU_DUAL_ROLE_TEACHER_USERIDS')

# 班主任识别：class_teachers_* 表。
# 表结构: class_name / grade_name / teacher_name / dingtalk_userid
# 钉钉免登拿到 dingtalk_userid 后反查该表，命中则 sub_role='class'，并绑定 bound_grade/bound_class。
# 通用约定：跨校区可扩展为 class_teachers_{campus}，当前仅本部 class_teachers_benbu。
def _class_teachers_table(campus_id=None):
    if campus_id == 'luojing':
        return 'class_teachers_luojing'
    if campus_id == 'baolin':
        return 'class_teachers_baolin'
    return 'class_teachers_benbu'

@app.route('/api/login', methods=['POST'])
def login():
    """独立账号密码登录；角色和绑定范围只读取 auth_accounts.db。"""
    data = request.get_json() or {}
    username = (data.get('username') or '').replace('\u200b', '').strip()
    password = (data.get('password') or '').strip()
    entry = (data.get('entry') or '').strip()
    campus = _valid_campus(data.get('campus'))
    if not username or not password:
        return jsonify({'success': False, 'error': '账号密码不能为空'}), 400
    if not campus:
        return jsonify({'success': False, 'error': '登录校区无效'}), 400
    if entry and entry not in LOGIN_ENTRY_ROLES:
        return jsonify({'success': False, 'error': '登录身份入口无效'}), 400
    try:
        db = get_auth_db(campus)
        row = db.execute(
            'SELECT * FROM auth_accounts WHERE username=? AND campus_id=?',
            (username, campus),
        ).fetchone()
    except sqlite3.Error:
        app.logger.exception('独立认证库不可用')
        return jsonify({'success': False, 'error': '登录服务暂不可用'}), 503
    now = int(time.time())
    if not row or not row['is_active']:
        return jsonify({'success': False, 'error': '账号或密码错误'}), 401
    if row['locked_until'] and int(row['locked_until']) > now:
        return jsonify({'success': False, 'error': '尝试次数过多，请15分钟后再试'}), 429
    if not check_password_hash(row['password_hash'], password):
        failures = int(row['failed_attempts'] or 0) + 1
        locked_until = now + 15 * 60 if failures >= 5 else None
        db.execute(
            'UPDATE auth_accounts SET failed_attempts=?, locked_until=? WHERE id=?',
            (0 if locked_until else failures, locked_until, row['id']),
        )
        db.commit()
        return jsonify({'success': False, 'error': '账号或密码错误'}), 401
    if entry:
        expected_role, expected_sub_role = LOGIN_ENTRY_ROLES[entry]
        role_matches = row['role'] == expected_role
        sub_role_matches = (
            expected_sub_role is None or row['sub_role'] == expected_sub_role
        )
        if not role_matches or not sub_role_matches:
            return jsonify({
                'success': False,
                'error': '该账号不属于所选身份入口',
            }), 403
    user = {
        'role':         row['role'],
        'sub_role':     row['sub_role'],
        'bound_id_card':row['bound_id_card'],
        'bound_grade':  row['bound_grade'],
        'bound_class':  row['bound_class'],
        'kid_name':     row['display_name'] if row['role'] == 'parent' else None,
        'demo_idx':     None,
        'displayName':  row['display_name'],
        'bound_student_userid': row['bound_student_userid'],
        'campus': campus,
    }
    db.execute(
        'UPDATE auth_accounts SET failed_attempts=0, locked_until=NULL, last_login_at=CURRENT_TIMESTAMP WHERE id=?',
        (row['id'],),
    )
    db.commit()
    session_token = _sign_session({
        'accountId': row['id'],
        'authVersion': row['auth_version'],
        'campus': campus,
        'exp': now + ACCOUNT_SESSION_TTL,
    })
    return jsonify({
        'success': True,
        'sessionToken': session_token,
        'user': user,
    })

# ==================== 角色 & 用户绑定 ====================
# user_bindings: 把钉钉 unionId 映射到角色 + 绑定的学生
#   role: 'teacher' | 'parent' | 'admin'
#   bound_id_card: 家长才用，对应自己孩子的学籍号

def _ensure_user_bindings_table():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS user_bindings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dingtalk_unionid TEXT UNIQUE,
        role TEXT NOT NULL DEFAULT 'teacher',
        sub_role TEXT,           -- 'general' (总务) | 'class' (班主任) for teachers
        bound_id_card TEXT,      -- parents: 学生 id_card
        bound_grade TEXT,        -- 班主任: 本班年级
        bound_class TEXT,        -- 班主任: 本班 class_name
        bound_name TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    # 兼容旧库：缺列补齐
    cols = {r[1] for r in db.execute('PRAGMA table_info(user_bindings)').fetchall()}
    for col_def in [
        ('sub_role','TEXT'),
        ('bound_grade','TEXT'),
        ('bound_class','TEXT'),
        ('dingtalk_userid','TEXT'),
        ('bound_student_userid','TEXT'),
    ]:
        if col_def[0] not in cols:
            db.execute(f'ALTER TABLE user_bindings ADD COLUMN {col_def[0]} {col_def[1]}')
    db.commit()

def _ensure_meal_tables():
    db = get_db()
    # 周菜单（总务老师上传）
    db.execute('''CREATE TABLE IF NOT EXISTS weekly_menus(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_number INTEGER NOT NULL,
        parity TEXT NOT NULL CHECK(parity IN ('odd','even')),
        date_start TEXT,
        date_end TEXT,
        selection_deadline TEXT,
        image_path TEXT,
        notes TEXT,
        uploaded_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(week_number, parity)
    )''')
    menu_cols = {r[1] for r in db.execute('PRAGMA table_info(weekly_menus)').fetchall()}
    if 'selection_deadline' not in menu_cols:
        db.execute('ALTER TABLE weekly_menus ADD COLUMN selection_deadline TEXT')
    for column, column_type in (
        ('import_batch_id', 'INTEGER'),
        ('service_days_json', "TEXT DEFAULT '[]'"),
    ):
        if column not in menu_cols:
            db.execute(f'ALTER TABLE weekly_menus ADD COLUMN {column} {column_type}')
    db.execute('''CREATE TABLE IF NOT EXISTS menu_import_batches(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_number INTEGER NOT NULL,
        parity TEXT NOT NULL CHECK(parity IN ('odd','even')),
        date_start TEXT,
        date_end TEXT,
        selection_deadline TEXT NOT NULL,
        image_path TEXT NOT NULL,
        excel_path TEXT NOT NULL,
        parsed_json TEXT NOT NULL,
        issues_json TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','rejected')),
        uploaded_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        published_at TEXT
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS nutrition_meal_plans(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plan_date DATE NOT NULL,
        plan_type TEXT CHECK(plan_type IN ('A','B')) NOT NULL,
        plan_name TEXT,
        ingredients TEXT DEFAULT '[]',
        calories_kcal REAL,
        protein_g REAL,
        fat_g REAL,
        carbs_g REAL,
        sugar_g REAL,
        sodium_mg REAL,
        fiber_g REAL,
        allergens TEXT DEFAULT '[]',
        suitable_tags TEXT DEFAULT '[]',
        unsuitable_notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(plan_date, plan_type)
    )''')
    meal_plan_cols = {r[1] for r in db.execute('PRAGMA table_info(nutrition_meal_plans)').fetchall()}
    for column, column_type in (
        ('weekly_menu_id', 'INTEGER'),
        ('service_status', "TEXT DEFAULT 'normal'"),
        ('menu_items', "TEXT DEFAULT '[]'"),
        ('protein_pct', 'REAL'),
        ('fat_pct', 'REAL'),
        ('vitamin_c_mg', 'REAL'),
        ('source_raw', 'TEXT'),
    ):
        if column not in meal_plan_cols:
            db.execute(f'ALTER TABLE nutrition_meal_plans ADD COLUMN {column} {column_type}')
    # 学生选餐（家长一次性提交奇/偶周周一~周日）
    db.execute('''CREATE TABLE IF NOT EXISTS meal_choices(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_card TEXT NOT NULL,
        name TEXT,
        grade_name TEXT,
        class_name TEXT,
        week_number INTEGER NOT NULL,
        parity TEXT NOT NULL CHECK(parity IN ('odd','even')),
        weekday INTEGER NOT NULL CHECK(weekday BETWEEN 1 AND 7),   -- 1=周一..7=周日
        choice TEXT NOT NULL CHECK(choice IN ('A','B')),
        chosen_by TEXT,                                            -- dt:unionId / ip:xxx
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(id_card, week_number, parity, weekday) ON CONFLICT REPLACE
    )''')
    # 迁移：旧表 weekday 约束 1-5 → 1-7（支持周六/周日选餐）
    _old = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='meal_choices'").fetchone()
    if _old and _old[0] and re.search(r'weekday\s+BETWEEN\s+1\s+AND\s+5', _old[0], re.IGNORECASE):
        db.execute('DROP INDEX IF EXISTS idx_meal_choices_week')
        db.execute('DROP INDEX IF EXISTS idx_meal_choices_class')
        db.execute('ALTER TABLE meal_choices RENAME TO meal_choices_old')
        db.execute('''CREATE TABLE meal_choices(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_card TEXT NOT NULL,
            name TEXT,
            grade_name TEXT,
            class_name TEXT,
            week_number INTEGER NOT NULL,
            parity TEXT NOT NULL CHECK(parity IN ('odd','even')),
            weekday INTEGER NOT NULL CHECK(weekday BETWEEN 1 AND 7),
            choice TEXT NOT NULL CHECK(choice IN ('A','B')),
            chosen_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(id_card, week_number, parity, weekday) ON CONFLICT REPLACE
        )''')
        db.execute('''INSERT INTO meal_choices (id, id_card, name, grade_name, class_name, week_number, parity, weekday, choice, chosen_by, created_at)
                      SELECT id, id_card, name, grade_name, class_name, week_number, parity, weekday, choice, chosen_by, created_at FROM meal_choices_old''')
        db.execute('DROP TABLE meal_choices_old')
        db.execute("UPDATE sqlite_sequence SET seq = (SELECT COALESCE(MAX(id),0) FROM meal_choices) WHERE name='meal_choices'")
    db.execute('CREATE INDEX IF NOT EXISTS idx_meal_choices_week ON meal_choices(week_number, parity)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_meal_choices_class ON meal_choices(grade_name, class_name)')
    db.commit()

def _lookup_binding(union_id):
    if not union_id: return None
    _ensure_user_bindings_table()
    db = get_db()
    cur = db.execute('SELECT * FROM user_bindings WHERE dingtalk_unionid = ?', (union_id,))
    row = cur.fetchone()
    return dict(row) if row else None

def _ensure_parent_kids_table():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS parent_kids(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        union_id TEXT NOT NULL,
        kid_id_card TEXT NOT NULL,
        kid_name TEXT NOT NULL,
        kid_grade TEXT,
        kid_class TEXT,
        campus TEXT,
        is_active INTEGER DEFAULT 0,
        bound_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(union_id, kid_id_card)
    )''')
    cols = {row[1] for row in db.execute('PRAGMA table_info(parent_kids)').fetchall()}
    if 'bound_at' not in cols:
        db.execute('ALTER TABLE parent_kids ADD COLUMN bound_at TEXT')
    if 'kid_dingtalk_userid' not in cols:
        db.execute('ALTER TABLE parent_kids ADD COLUMN kid_dingtalk_userid TEXT')
    db.execute('CREATE INDEX IF NOT EXISTS idx_pk_union ON parent_kids(union_id)')
    db.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_pk_union_student_userid
                  ON parent_kids(union_id, kid_dingtalk_userid)
                  WHERE kid_dingtalk_userid IS NOT NULL''')
    db.commit()


def _table_columns(db, table):
    return {row[1] for row in db.execute(f'PRAGMA table_info({table})').fetchall()}


def _student_by_userid(db, campus, dingtalk_userid):
    """用客户通讯录中的稳定学生 UserID 精确定位学生。"""
    if not dingtalk_userid:
        return None
    table = _students_table(campus)
    if 'dingtalk_userid' not in _table_columns(db, table):
        return None
    return db.execute(
        f'''SELECT dingtalk_userid, id_card, name, grade_name, class_name
            FROM {table} WHERE dingtalk_userid=? LIMIT 1''',
        (dingtalk_userid,),
    ).fetchone()


_PARENT_NICK_RELATION_RE = re.compile(
    r'^(?P<name>.+?)(?:爸爸|妈妈|父亲|母亲|家长|爷爷|奶奶|外公|外婆|祖父|祖母)$'
)


def _student_names_from_parent_nick(nick):
    """解析钉钉家校昵称中的孩子姓名，不把普通用户昵称当成学生姓名。"""
    names = []
    for part in re.split(r'[/／,，、;；]+', (nick or '').strip()):
        match = _PARENT_NICK_RELATION_RE.fullmatch(part.strip())
        if not match:
            continue
        name = match.group('name').strip()
        if name and name not in names:
            names.append(name)
    return names


def _auto_bind_parent_kids_from_nick(db, union_id, campus, nick):
    """用钉钉家校昵称补全家长关系。

    客户学生表没有家长 UserID，登录返回的又是家长账号 UserID，因此不能
    直接拿登录 UserID 查询学生。这里只接受钉钉生成的“孩子姓名+关系”昵称，
    且要求每个姓名在当前校区名册中精确唯一；重名、缺失、已被其他账号绑定
    时全部拒绝，避免按姓名 LIMIT 1 导致串班。
    """
    names = _student_names_from_parent_nick(nick)
    if not union_id or not names:
        return []

    table = _students_table(campus)
    columns = _table_columns(db, table)
    if 'dingtalk_userid' not in columns:
        return []

    students = []
    for name in names:
        matches = db.execute(
            f'''SELECT dingtalk_userid, id_card, name, grade_name, class_name
                FROM {table} WHERE name=? LIMIT 2''',
            (name,),
        ).fetchall()
        if len(matches) != 1:
            app.logger.warning(
                '[家长自动绑定] 拒绝昵称匹配: campus=%s name=%s matches=%s',
                campus, name, len(matches),
            )
            return []
        students.append(matches[0])

    _ensure_parent_kids_table()
    for student in students:
        conflict = db.execute(
            '''SELECT 1 FROM parent_kids
               WHERE union_id<>?
                 AND (kid_dingtalk_userid=? OR kid_id_card=?) LIMIT 1''',
            (union_id, student['dingtalk_userid'], student['id_card']),
        ).fetchone()
        if conflict:
            app.logger.warning(
                '[家长自动绑定] 拒绝重复关系: campus=%s name=%s',
                campus, student['name'],
            )
            return []

    has_active = db.execute(
        'SELECT 1 FROM parent_kids WHERE union_id=? AND is_active=1 LIMIT 1',
        (union_id,),
    ).fetchone()
    for student in students:
        existing = db.execute(
            '''SELECT id FROM parent_kids
               WHERE union_id=?
                 AND (kid_dingtalk_userid=? OR kid_id_card=?) LIMIT 1''',
            (union_id, student['dingtalk_userid'], student['id_card']),
        ).fetchone()
        if existing:
            continue
        db.execute(
            '''INSERT INTO parent_kids(
                   union_id, kid_dingtalk_userid, kid_id_card, kid_name,
                   kid_grade, kid_class, campus, is_active
               ) VALUES(?,?,?,?,?,?,?,?)''',
            (
                union_id, student['dingtalk_userid'], student['id_card'],
                student['name'], student['grade_name'], student['class_name'],
                campus, 0,
            ),
        )

    if not has_active:
        first = students[0]
        db.execute(
            '''UPDATE parent_kids SET is_active=1
               WHERE id=(
                   SELECT id FROM parent_kids
                   WHERE union_id=?
                     AND (kid_dingtalk_userid=? OR kid_id_card=?)
                   ORDER BY id LIMIT 1
               )''',
            (union_id, first['dingtalk_userid'], first['id_card']),
        )

    active = db.execute(
        '''SELECT kid_dingtalk_userid, kid_id_card, kid_name, kid_grade, kid_class
           FROM parent_kids WHERE union_id=? AND is_active=1 LIMIT 1''',
        (union_id,),
    ).fetchone()
    if active:
        db.execute(
            '''UPDATE user_bindings
               SET bound_student_userid=?, bound_id_card=?, bound_name=?,
                   bound_grade=?, bound_class=?
               WHERE dingtalk_unionid=? AND role='parent' ''',
            (
                active['kid_dingtalk_userid'], active['kid_id_card'],
                active['kid_name'], active['kid_grade'], active['kid_class'],
                union_id,
            ),
        )
    db.commit()
    app.logger.info(
        '[家长自动绑定] 成功: campus=%s kids=%s',
        campus, '/'.join(student['name'] for student in students),
    )
    return students


def _authoritative_parent_kid(db, kid):
    """用当前校区学生名册刷新家长绑定中的年级和班级。

    旧测试数据里的学籍号可能与本部新名册冲突；只有学籍号+姓名同时
    命中，或姓名在当前名册中唯一时才采用新数据，避免同名误绑。
    """
    if not kid:
        return None
    stored = dict(kid)
    campus = (stored.get('campus') or 'benbu').strip()
    table = _students_table(campus)
    exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        return stored
    table_columns = _table_columns(db, table)
    userid_select = 'dingtalk_userid' if 'dingtalk_userid' in table_columns else 'NULL AS dingtalk_userid'
    current = None
    if stored.get('kid_dingtalk_userid') and 'dingtalk_userid' in table_columns:
        current = db.execute(
            f'''SELECT dingtalk_userid, id_card, name, grade_name, class_name
                FROM {table} WHERE dingtalk_userid=? LIMIT 1''',
            (stored['kid_dingtalk_userid'],),
        ).fetchone()
    if not current:
        current = db.execute(
            f'''SELECT {userid_select}, id_card, name, grade_name, class_name
                FROM {table} WHERE id_card=? AND name=? LIMIT 1''',
            (stored.get('kid_id_card'), stored.get('kid_name')),
        ).fetchone()
    if not current and stored.get('kid_name'):
        matches = db.execute(
            f'''SELECT {userid_select}, id_card, name, grade_name, class_name
                FROM {table} WHERE name=? LIMIT 2''',
            (stored['kid_name'],),
        ).fetchall()
        current = matches[0] if len(matches) == 1 else None
    if not current:
        return stored
    return {
        **stored,
        'kid_dingtalk_userid': current['dingtalk_userid'],
        'kid_id_card': current['id_card'],
        'kid_name': current['name'],
        'kid_grade': current['grade_name'],
        'kid_class': current['class_name'],
        'campus': campus,
    }


def _parent_kid_payload(db, kid):
    current = _authoritative_parent_kid(db, kid)
    return {
        'studentUserId': current.get('kid_dingtalk_userid'),
        'idCard': current['kid_id_card'],
        'name': current['kid_name'],
        'grade': current['kid_grade'],
        'class': current['kid_class'],
        'campus': current.get('campus'),
        'active': bool(current.get('is_active')),
    }


def _student_row_as_kid(student, campus, active=True):
    if not student:
        return None
    return {
        'kid_dingtalk_userid': student['dingtalk_userid'],
        'kid_id_card': student['id_card'],
        'kid_name': student['name'],
        'kid_grade': student['grade_name'],
        'kid_class': student['class_name'],
        'campus': campus,
        'is_active': 1 if active else 0,
    }


def _resolve_meal_student_for_user(db, binding, union_id, campus):
    """按稳定学生 UserID 解析选餐学生；监护人绑定仅作为关系表。"""
    direct_userid = (binding or {}).get('bound_student_userid')
    if not direct_userid:
        login_userid = (binding or {}).get('dingtalk_userid')
        if _student_by_userid(db, campus, login_userid):
            direct_userid = login_userid
    if direct_userid:
        student = _student_by_userid(db, campus, direct_userid)
        if student:
            return _student_row_as_kid(student, campus)

    _ensure_parent_kids_table()
    kid = db.execute(
        '''SELECT kid_dingtalk_userid, kid_id_card, kid_name, kid_grade,
                  kid_class, campus, is_active
           FROM parent_kids WHERE union_id=? AND is_active=1 LIMIT 1''',
        (union_id,),
    ).fetchone()
    return _authoritative_parent_kid(db, kid)

def _current_user():
    """
    返回 dict {role, sub_role, bound_id_card, bound_grade, bound_class, identity}
    URL demo 支持：
      ?role=parent&kid=BS001
      ?role=teacher&sub=general            (总务老师)
      ?role=teacher&sub=class&grade=五年级&class=2班   (班主任)
    """
    query_role = request.args.get('role')
    header_role = request.headers.get('X-Demo-Role')
    role = None if DISABLE_DEMO else (query_role or header_role)
    if role in ('teacher','parent','admin'):
        # URL demo 身份和请求头身份不能混用。否则业务查询中的 grade/class
        # 会覆盖班主任账号的绑定范围，造成跨班读取。
        use_query_identity = bool(query_role)
        return {
            'role': role,
            'sub_role': request.args.get('sub') if use_query_identity else request.headers.get('X-Demo-Sub'),
            'bound_id_card': request.args.get('kid') if use_query_identity else request.headers.get('X-Demo-Kid'),
            'bound_grade': request.args.get('grade') if use_query_identity else request.headers.get('X-Demo-Grade'),
            'bound_class': request.args.get('class') if use_query_identity else request.headers.get('X-Demo-Class'),
            'identity': f'demo:{role}',
        }

    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        info = _verify_session(auth[7:])
        if info and info.get('accountId'):
            # 旧版账号令牌没有 campus，只可能来自宝林上线前，因此兼容为本部。
            account_campus = _valid_campus(info.get('campus'), 'benbu')
            try:
                row = get_auth_db(account_campus).execute(
                    '''SELECT * FROM auth_accounts
                       WHERE id=? AND campus_id=? AND is_active=1''',
                    (info['accountId'], account_campus),
                ).fetchone()
            except sqlite3.Error:
                row = None
            if not row or int(info.get('authVersion') or 0) != int(row['auth_version'] or 0):
                return {
                    'role': 'none', 'sub_role': None, 'bound_id_card': None,
                    'bound_student_userid': None, 'bound_grade': None,
                    'bound_class': None, 'identity': 'none',
                }
            return {
                'role': row['role'],
                'sub_role': row['sub_role'],
                'display_name': row['display_name'],
                'bound_id_card': row['bound_id_card'],
                'bound_student_userid': row['bound_student_userid'],
                'bound_grade': row['bound_grade'],
                'bound_class': row['bound_class'],
                'campus': account_campus,
                'identity': f"account:{row['id']}",
            }
        if info and info.get('unionId'):
            uid = info['unionId']
            b = _lookup_binding(uid)
            db = get_db()
            campus = info.get('campus') or _resolve_campus()
            pk = _resolve_meal_student_for_user(db, b, uid, campus)
            
            if b:
                base_role = b['role']
                # 双角色检测：教师也有绑定的孩子 → 可切家长模式
                if base_role == 'teacher':
                    all_kids = db.execute('SELECT kid_dingtalk_userid, kid_id_card, kid_name, kid_grade, kid_class, campus, is_active FROM parent_kids WHERE union_id = ?', (uid,)).fetchall()
                    dual_role_whitelisted = (
                        campus == 'benbu'
                        and info.get('dingtalkUserId') in BENBU_DUAL_ROLE_TEACHER_USERIDS
                    )
                    if all_kids or dual_role_whitelisted:
                        # 存入 session（持久化），_current_user 无需每次查 DB
                        session['available_roles'] = ['teacher', 'parent']
                        session['parent_uid'] = uid
                        # 优先用 session 中的 active_role_override
                        override = session.get('active_role_override')
                        if override == 'parent':
                            bound = None
                            if all_kids:
                                bound = _authoritative_parent_kid(
                                    db, next((k for k in all_kids if k['is_active']), all_kids[0])
                                )
                            return {
                                'role': 'parent',
                                'sub_role': None,
                                'bound_student_userid': bound.get('kid_dingtalk_userid') if bound else None,
                                'bound_id_card': bound['kid_id_card'] if bound else None,
                                'bound_grade': bound['kid_grade'] if bound else None,
                                'bound_class': bound['kid_class'] if bound else None,
                                'identity': f"dt:{uid}",
                            }
                return {
                    'role': base_role,
                    'sub_role': b.get('sub_role'),
                    'bound_student_userid': None if base_role in ('teacher', 'admin') else (pk.get('kid_dingtalk_userid') if pk else None),
                    'bound_id_card': None if base_role in ('teacher', 'admin') else (pk['kid_id_card'] if pk else None),
                    'bound_grade': b.get('bound_grade') if base_role in ('teacher', 'admin') else (pk['kid_grade'] if pk else None),
                    'bound_class': b.get('bound_class') if base_role in ('teacher', 'admin') else (pk['kid_class'] if pk else None),
                    'identity': f"dt:{uid}",
                }
            return {'role':'parent','sub_role':None,'bound_student_userid':(pk.get('kid_dingtalk_userid') if pk else None),'bound_id_card':(pk['kid_id_card'] if pk else None),'bound_grade':(pk['kid_grade'] if pk else None),'bound_class':(pk['kid_class'] if pk else None),'identity':f"dt:{uid}"}
    return {'role':'none','sub_role':None,'bound_student_userid':None,'bound_id_card':None,'bound_grade':None,'bound_class':None,'identity':f"ip:{request.remote_addr}"}

@app.before_request
def _bridge_nutrition_auth():
    """把平台认证结果注入营养蓝图，避免信任营养页面自报的角色。"""
    if not request.path.startswith('/api/nutrition/'):
        return None
    user = _current_user()
    g.user_role = user['role']
    g.nutrition_child_code = user.get('bound_id_card')
    return None

def _require_can_see(id_card):
    """家长只能看自己绑定的孩子；老师/管理员通行"""
    u = _current_user(); role, bound = u['role'], u['bound_id_card']
    if role in ('teacher','admin'):
        return True
    if role == 'none':
        return False
    if role == 'parent':
        return bool(bound and id_card and bound == id_card)
    return False

@app.route('/api/health', methods=['GET'])
def health():
    """部署健康检查 - Nginx upstream / 钉钉应用探针用"""
    ok_db = False
    try:
        get_db().execute('SELECT 1').fetchone()
        ok_db = True
    except Exception:
        pass
    return jsonify({
        'status': 'ok' if ok_db else 'degraded',
        'db': ok_db,
        'ai_configured': bool(AI_API_KEY),
        'ai_provider': AI_PROVIDER if AI_API_KEY else None,
        'dingtalk_configured': bool(DINGTALK_APP_KEY and DINGTALK_APP_SECRET),
        'mode': 'debug' if DEBUG else 'prod',
        'ts': int(time.time()),
    }), (200 if ok_db else 503)

@app.route('/api/auth/diag', methods=['POST'])
def auth_diag():
    """前端 JSAPI 错误诊断上报（仅记录日志）"""
    data = request.get_json() or {}
    app.logger.error(f'[DIAG] JSAPI错误: {json.dumps(data, ensure_ascii=False)[:2000]}')
    return jsonify({'ok': True})

@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    """前端调用：返回角色 / 子角色 / 绑定的学生或班级"""
    u = _current_user()
    info = {
        'role': u['role'],
        'subRole': u['sub_role'],
        'displayName': u.get('display_name'),
        'campus': u.get('campus'),
        'boundStudentUserId': u.get('bound_student_userid'),
        'boundIdCard': u['bound_id_card'],
        'boundGrade': u['bound_grade'],
        'boundClass': u['bound_class'],
        'owner': u['identity'],
    }
    if u.get('bound_student_userid') or u['bound_id_card']:
        db = get_db()
        # 校区隔离：罗泾使用独立学生表
        campus = _resolve_campus()
        stable = _students_table(campus)
        if u.get('bound_student_userid') and 'dingtalk_userid' in _table_columns(db, stable):
            cur = db.execute(
                f'''SELECT dingtalk_userid, id_card, name, grade_name, class_name
                    FROM {stable} WHERE dingtalk_userid=?''',
                (u['bound_student_userid'],),
            )
        else:
            cur = db.execute(
                f'''SELECT NULL AS dingtalk_userid, id_card, name, grade_name, class_name
                    FROM {stable} WHERE id_card=?''',
                (u['bound_id_card'],),
            )
        row = cur.fetchone()
        if row:
            info['boundStudent'] = {
                'studentUserId': row['dingtalk_userid'],
                'idCard': row['id_card'],
                # 家长只能拿到自己已绑定的学生，因此允许显示完整姓名，
                # 方便在选餐前核对；其他角色仍保持脱敏。
                'displayName': row['name'] if u['role'] == 'parent' else mask_name(row['name']),
                'grade': row['grade_name'],
                'class': row['class_name'],
            }
    # 多娃：返回所有已绑定的孩子列表
    if u['role'] == 'parent' and 'identity' in u and u['identity'].startswith('dt:'):
        uid = u['identity'][3:]
        db = get_db()
        kids = db.execute('SELECT kid_dingtalk_userid, kid_id_card, kid_name, kid_grade, kid_class, campus, is_active FROM parent_kids WHERE union_id = ? ORDER BY bound_at', (uid,)).fetchall()
        if kids:
            info['kids'] = [_parent_kid_payload(db, kid) for kid in kids]
    
    # 双角色信息：教师→家长切换用
    av = session.get('available_roles')
    if av:
        info['availableRoles'] = av
        info['parentBound'] = True
    else:
        info['availableRoles'] = [u['role']] if u['role'] in ('teacher','parent') else []
        info['parentBound'] = False
    
    return jsonify(info)

@app.route('/api/switch-role', methods=['POST'])
def switch_role():
    """双角色用户切换当前活跃角色（teacher ↔ parent）"""
    u = _current_user()
    av = session.get('available_roles')
    if not av:
        return jsonify({'success': False, 'error': '当前用户没有多角色权限'}), 403
    
    data = request.get_json() or {}
    target = (data.get('role') or '').strip()
    if target not in av:
        return jsonify({'success': False, 'error': f'无效的目标角色: {target}'}), 400
    
    session['active_role_override'] = target
    return jsonify({'success': True, 'role': target})


@app.route('/api/auth/bind', methods=['POST'])
def auth_bind():
    """管理员用：把一个钉钉 unionId 绑定到学生（家长账号）"""
    data = request.get_json() or {}
    union_id = data.get('unionId')
    role = data.get('role', 'parent')
    bound_id_card = data.get('boundIdCard')
    if not union_id:
        return jsonify({'error': 'unionId required'}), 400
    if role == 'parent' and not bound_id_card:
        return jsonify({'error': 'parent 必须指定 boundIdCard'}), 400
    _ensure_user_bindings_table()
    db = get_db()
    db.execute('''INSERT INTO user_bindings(dingtalk_unionid, role, bound_id_card, bound_name)
        VALUES(?,?,?,?)
        ON CONFLICT(dingtalk_unionid) DO UPDATE SET role=excluded.role, bound_id_card=excluded.bound_id_card''',
        (union_id, role, bound_id_card, data.get('boundName','')))
    db.commit()
    return jsonify({'message': '绑定成功'})

# ==================== AI 代理（后端持有 Key） ====================

def _ai_call(system_prompt, user_prompt):
    """服务端代理调用 OpenAI Chat Completions 兼容接口，避免泄漏 Key。"""
    if not AI_API_KEY:
        raise RuntimeError('服务端未配置 AI API Key')
    body = json.dumps({
        'model': AI_MODEL,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': 0.7,
        'max_tokens': 8000,
        'enable_thinking': False,
    }).encode('utf-8')
    req = Request(AI_URL, data=body, method='POST', headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {AI_API_KEY}',
    })
    for attempt in range(3):
        try:
            with urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            break
        except (ssl.SSLError, OSError, urllib_error.URLError) as net_err:
            if attempt < 2:
                time.sleep((attempt + 1) * 2)
            else:
                raise
    msg = (data.get('choices') or [{}])[0].get('message') or {}
    return (msg.get('content') or '').strip() or (msg.get('reasoning_content') or '').strip()

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    """前端统一调用这个端点，不直接接触供应商 Key。"""
    payload = request.get_json() or {}
    system_prompt = payload.get('system') or ''
    user_prompt = payload.get('user') or ''
    if not user_prompt:
        return jsonify({'error': 'user prompt is required'}), 400
    if not AI_API_KEY:
        return jsonify({'error': 'AI 服务未配置，请联系管理员', 'configured': False}), 503
    try:
        text = _ai_call(system_prompt, user_prompt)
        return jsonify({'content': text})
    except Exception as e:
        return jsonify({'error': f'AI 调用失败：{str(e)[:200]}'}), 502

@app.route('/api/ai/status', methods=['GET'])
def ai_status():
    """前端可用来判断是否需要展示"AI 不可用"状态"""
    return jsonify({
        'configured': bool(AI_API_KEY),
        'provider': AI_PROVIDER if AI_API_KEY else None,
        'model': AI_MODEL if AI_API_KEY else None,
    })

# ==================== 钉钉 SSO ====================

@app.route('/api/auth/dingtalk', methods=['POST'])
def dingtalk_login():
    """前端通过钉钉 JSAPI 拿 authCode，后端换成用户身份。
    【自动识别校区】三个校区是三个独立钉钉组织（corpId 不同），authCode 绑定来源组织：
    遍历所有已配置校区的 AppKey/Secret 尝试兑码，只有用户真实所属组织能成功，据此自动判定 campus。
    前端不再需要（也不信任）传 campus 参数。"""
    if PASSWORD_LOGIN_ONLY:
        return jsonify({'error': '钉钉免登录已停用，请使用账号密码登录'}), 410
    payload = request.get_json() or {}
    auth_code = (payload.get('authCode') or '').strip()
    # 彻底清洗：去掉所有不可打印字符，只保留字母数字
    import re
    auth_code_clean = re.sub(r'[^a-zA-Z0-9]', '', auth_code)
    app.logger.info(
        '[钉钉登录] 收到请求 raw_len=%s clean_len=%s',
        len(auth_code),
        len(auth_code_clean),
    )
    
    if not auth_code_clean:
        return jsonify({'error': 'authCode required'}), 400

    # 自动遍历所有已配置校区，哪个兑码成功就判定为哪个校区
    campus_id = ''
    user = None
    campus_candidates = []
    cfg = _load_campus_config()
    for cid in cfg.keys():
        if cid.startswith('_'):
            continue
        dt_cfg = _get_campus_dt(cid)
        app_key = dt_cfg.get('appKey') or ''
        app_secret = dt_cfg.get('appSecret') or ''
        if not (app_key and app_secret):
            continue
        campus_candidates.append(cid)
        # 每个校区依次尝试三种兑码 API
        u = _exchange_auth_code_via_accesstoken(app_key, app_secret, auth_code_clean)
        if not u or not (u.get('unionId') or u.get('userId')):
            u = _exchange_auth_code_old(app_key, app_secret, auth_code_clean)
        if not u or not (u.get('unionId') or u.get('userId')):
            u = _exchange_auth_code_new(app_key, app_secret, auth_code_clean)
        if u and (u.get('unionId') or u.get('userId')):
            campus_id = cid
            user = u
            app.logger.info(f'[钉钉登录] 自动判定校区成功: campus={cid} (遍历顺序={campus_candidates})')
            break
        else:
            app.logger.info(f'[钉钉登录] campus={cid} 兑码失败（非该组织用户），继续尝试下一校区')

    if not user:
        return jsonify({'error': '钉钉身份校验失败：遍历所有校区均无法解析该 authCode（可能不在已配置校区组织中）'}), 502
    try:
        union_id = user.get('unionId') or ''
        nick = user.get('nick') or ''
        avatar_url = user.get('avatarUrl') or ''
        dingtalk_userid = user.get('userId') or ''
        # 兜底：若所有 API 都无法获取 unionId，用 userId 构造标识（避免 double prefix）
        if not union_id and dingtalk_userid:
            union_id = f'uid:{dingtalk_userid}'
            # 如果 nick 也空，用 userId 显示
            if not nick:
                nick = f'钉钉用户({dingtalk_userid[:8]}…)'
            app.logger.info(f'[钉钉登录] unionId 为空，使用 userId 兜底: {union_id}')
        if not union_id:
            return jsonify({'error': '钉钉身份校验失败：无法获取用户标识'}), 502
        
        # 自动 upsert user_bindings(便于试点期免去逐人手工绑定)
        # 默认 role=parent 未绑定学生；教师通过 teacher_roster 识别
        try:
            _ensure_user_bindings_table()
            db = get_db()
            existing = db.execute('SELECT id, role FROM user_bindings WHERE dingtalk_unionid = ?', (union_id,)).fetchone()
            direct_student = _student_by_userid(db, campus_id, dingtalk_userid)
            # 是否命中指定总务名单（基于钉钉 userId 精确匹配）
            is_general = dingtalk_userid in GENERAL_TEACHER_BY_USERID
            # 是否班主任：反查 class_teachers 表（dingtalk_userid -> 年级/班级）
            class_teacher_row = None
            if dingtalk_userid and not is_general:
                ctable = _class_teachers_table(campus_id)
                try:
                    class_teacher_row = db.execute(
                        f'SELECT * FROM {ctable} WHERE dingtalk_userid = ?', (dingtalk_userid,)
                    ).fetchone()
                except Exception:
                    class_teacher_row = None
            if not existing and union_id:
                # 1) teacher_roster 里查 userId → 教师（校区隔离）
                default_role = 'parent'
                default_sub_role = None
                default_grade = None
                default_class = None
                teacher_row = None
                if dingtalk_userid:
                    troster = _teacher_roster_table(campus_id)
                    teacher_row = db.execute(
                        f'SELECT * FROM {troster} WHERE dingtalk_userid = ?', (dingtalk_userid,)
                    ).fetchone()
                    if teacher_row:
                        default_role = 'teacher'
                # 2) 环境变量 admin 列表（unionId 匹配）
                if default_role == 'parent':
                    admins = {u.strip() for u in os.environ.get('DINGTALK_DEFAULT_ADMINS', '').split(',') if u.strip()}
                    if union_id in admins:
                        default_role = 'admin'
                # 3) 指定总务名单 => 强制 teacher + sub_role=general
                if is_general:
                    default_role = 'teacher'
                    default_sub_role = 'general'
                # 4) 班主任 => teacher + sub_role=class + 绑定年级班级
                elif class_teacher_row:
                    default_role = 'teacher'
                    default_sub_role = 'class'
                    default_grade = class_teacher_row['grade_name']
                    default_class = class_teacher_row['class_name']
                
                db.execute('''INSERT INTO user_bindings(
                                  dingtalk_unionid, role, sub_role, bound_name,
                                  dingtalk_userid, bound_student_userid,
                                  bound_id_card, bound_grade, bound_class
                              ) VALUES(?,?,?,?,?,?,?,?,?)''',
                           (
                               union_id, default_role, default_sub_role, nick,
                               dingtalk_userid,
                               direct_student['dingtalk_userid'] if direct_student else None,
                               direct_student['id_card'] if direct_student else None,
                               default_grade or (direct_student['grade_name'] if direct_student else None),
                               default_class or (direct_student['class_name'] if direct_student else None),
                           ))
                if default_role == 'parent':
                    _auto_bind_parent_kids_from_nick(
                        db, union_id, campus_id, nick
                    )
                db.commit()
                teacher_info = f' teacher_campus={campus_id}' if teacher_row else ''
                general_info = ' 指定总务' if is_general else ''
                class_info = f' 班主任({default_grade}{default_class})' if class_teacher_row else ''
                app.logger.info(f'[钉钉登录] 新用户自动入库: {union_id} ({default_role}/{default_sub_role}) {nick}{teacher_info}{general_info}{class_info}')
            elif existing and union_id and dingtalk_userid:
                # 已有用户：回填 dingtalk_userid（首次未记录时补上）
                db.execute('UPDATE user_bindings SET dingtalk_userid=? WHERE dingtalk_unionid=? AND (dingtalk_userid IS NULL OR dingtalk_userid="")', (dingtalk_userid, union_id))
                if direct_student and existing['role'] == 'parent':
                    db.execute(
                        '''UPDATE user_bindings
                           SET bound_student_userid=?, bound_id_card=?, bound_name=?,
                               bound_grade=?, bound_class=?
                           WHERE dingtalk_unionid=?''',
                        (
                            direct_student['dingtalk_userid'], direct_student['id_card'],
                            direct_student['name'], direct_student['grade_name'],
                            direct_student['class_name'], union_id,
                        ),
                    )
                if existing['role'] == 'parent':
                    _auto_bind_parent_kids_from_nick(
                        db, union_id, campus_id, nick
                    )
                # 角色修正：查 teacher_roster
                current_role = existing['role']
                if is_general:
                    # 指定总务名单：强制修正为 teacher + sub_role=general
                    db.execute('UPDATE user_bindings SET role=?, sub_role=? WHERE dingtalk_unionid=?', ('teacher', 'general', union_id))
                    db.commit()
                    app.logger.info(f'[钉钉登录] 角色修正(指定总务): {union_id} -> teacher/general')
                elif class_teacher_row:
                    # 班主任：修正为 teacher + sub_role=class + 绑定年级班级
                    db.execute('UPDATE user_bindings SET role=?, sub_role=?, bound_grade=?, bound_class=? WHERE dingtalk_unionid=?',
                               ('teacher', 'class', class_teacher_row['grade_name'], class_teacher_row['class_name'], union_id))
                    db.commit()
                    app.logger.info(f'[钉钉登录] 角色修正(班主任): {union_id} -> teacher/class {class_teacher_row["grade_name"]}{class_teacher_row["class_name"]}')
                elif current_role == 'parent':
                    troster = _teacher_roster_table(campus_id)
                    teacher_row = db.execute(
                        f'SELECT dingtalk_userid FROM {troster} WHERE dingtalk_userid = ?', (dingtalk_userid,)
                    ).fetchone()
                    if teacher_row:
                        db.execute('UPDATE user_bindings SET role=? WHERE dingtalk_unionid=?', ('teacher', union_id))
                        db.commit()
                        app.logger.info(f'[钉钉登录] 角色修正: {union_id} parent→teacher campus={campus_id}')
                db.commit()
        except Exception as ee:
            app.logger.warning(f'[钉钉登录] upsert user_bindings 失败: {ee}')
        except Exception as ee:
            app.logger.warning(f'[钉钉登录] upsert user_bindings 失败: {ee}')
        sess_token = _sign_session({
            'unionId': union_id,
            'dingtalkUserId': dingtalk_userid,
            'nick': nick,
            'campus': campus_id,
            'ts': int(time.time()),
        })
        app.logger.info(f'[钉钉登录] 成功: {union_id} ({nick}) campus={campus_id}')
        return jsonify({
            'sessionToken': sess_token,
            'user': {'nick': nick, 'avatarUrl': avatar_url, 'unionId': union_id},
            'campus': campus_id
        })
    except urllib_error.HTTPError as e:
        body = ''
        try: body = e.read().decode('utf-8')[:500]
        except: pass
        app.logger.error(f'[钉钉登录] HTTP {e.code}: {body}')
        return jsonify({'error': f'钉钉API返回 {e.code}: {body[:200]}'}), 502
    except Exception as e:
        app.logger.error(f'[钉钉登录] 失败: {e}')
        return jsonify({'error': f'钉钉登录失败:{str(e)[:200]}'}), 502

def _exchange_auth_code_new(app_key, app_secret, auth_code):
    """新版 API：v1.0/oauth2/userAccessToken → contact/users/me"""
    try:
        token_req = Request('https://api.dingtalk.com/v1.0/oauth2/userAccessToken',
            data=json.dumps({
                'clientId': app_key,
                'clientSecret': app_secret,
                'code': auth_code,
                'grantType': 'authorization_code',
            }).encode('utf-8'),
            headers={'Content-Type': 'application/json'})
        with urlopen(token_req, timeout=10) as r:
            tok = json.loads(r.read().decode('utf-8'))
        access_token = tok.get('accessToken')
        if not access_token:
            app.logger.warning(f'[新API] 无 accessToken: {json.dumps(tok, ensure_ascii=False)[:300]}')
            return None
        user_req = Request('https://api.dingtalk.com/v1.0/contact/users/me',
            headers={'x-acs-dingtalk-access-token': access_token})
        with urlopen(user_req, timeout=10) as r:
            user = json.loads(r.read().decode('utf-8'))
        if not user.get('unionId'):
            app.logger.warning(f'[新API] 无 unionId: {json.dumps(user, ensure_ascii=False)[:200]}')
            return None
        # 保留 userId 用于教师身份识别
        return {
            'unionId': user.get('unionId'),
            'openId': user.get('openId'),
            'userId': user.get('userId') or '',
            'nick': user.get('nick') or '',
            'avatarUrl': user.get('avatarUrl') or '',
            'mobile': user.get('mobile') or '',
        }
    except Exception as e_new:
        try:
            body = e_new.read().decode('utf-8')[:300]
        except:
            body = str(e_new)[:300]
        app.logger.warning(f'[新API失败] {body}')
        return None

def _exchange_auth_code_via_accesstoken(app_key, app_secret, auth_code):
    """dd.getAuthCode() 免登兑码：gettoken → user/getuserinfo → topapi/v2/user/get"""
    try:
        # Step 1: get enterprise access_token
        tok_req = Request(f'https://oapi.dingtalk.com/gettoken?appkey={app_key}&appsecret={app_secret}')
        with urlopen(tok_req, timeout=10) as r:
            tok = json.loads(r.read().decode('utf-8'))
        access_token = tok.get('access_token')
        if not access_token:
            app.logger.warning(f'[免登兑码] gettoken 失败: {json.dumps(tok, ensure_ascii=False)[:200]}')
            return None
        
        # Step 2: get userid from authCode
        user_req = Request(f'https://oapi.dingtalk.com/user/getuserinfo?access_token={access_token}&code={auth_code}')
        with urlopen(user_req, timeout=10) as r:
            info = json.loads(r.read().decode('utf-8'))
        if info.get('errcode') != 0:
            app.logger.warning(f'[免登兑码] user/getuserinfo 失败: {json.dumps(info, ensure_ascii=False)[:200]}')
            return None
        userid = info.get('userid')
        device_id = info.get('deviceId', '')
        
        # Step 3: get user detail (name, unionid)
        detail_req = Request(f'https://oapi.dingtalk.com/topapi/v2/user/get?access_token={access_token}',
            data=json.dumps({'userid': userid, 'language': 'zh_CN'}).encode('utf-8'),
            headers={'Content-Type': 'application/json'})
        with urlopen(detail_req, timeout=10) as r:
            detail = json.loads(r.read().decode('utf-8'))
        result = detail.get('result', {})
        
        union_id = result.get('unionid', '')
        nick = result.get('name', '')
        avatar = result.get('avatar', '')
        if not union_id and userid:
            # 罗泾等校区的钉钉应用未开通通讯录权限，topapi/v2/user/get 无 unionid
            # 直接在这里兜底，不再走后续 API（它们同样拿不到 unionid）
            app.logger.warning(f'[免登兑码] 无 unionid，用 userId 兜底: userid={userid} nick={nick}')
            return {
                'unionId': f'uid:{userid}',
                'userId': userid,
                'nick': nick,
                'avatarUrl': avatar,
            }
        if not union_id:
            app.logger.warning(f'[免登兑码] 无 unionid 且无 userid')
        
        app.logger.info(f'[免登兑码] 成功: {nick} unionid={union_id} userid={userid}')
        return {
            'unionId': union_id,
            'userId': userid,
            'openId': result.get('openid', ''),
            'nick': nick,
            'avatarUrl': avatar,
            'mobile': result.get('mobile', ''),
            'deviceId': device_id,
        }
    except Exception as e:
        try:
            body = e.read().decode('utf-8')[:300] if hasattr(e, 'read') else str(e)[:300]
        except:
            body = str(e)[:300]
        app.logger.warning(f'[免登兑码异常] {body}')
        return None

def _exchange_auth_code_old(app_key, app_secret, auth_code):
    """旧版 API：sns/getuserinfo_bycode（用于开了 open_app_api_base 权限的企业内部应用）"""
    try:
        ts_ms = str(int(time.time() * 1000))
        sig_raw = hmac.new(app_secret.encode('utf-8'), ts_ms.encode('utf-8'), hashlib.sha256).digest()
        sig = base64.b64encode(sig_raw).decode('utf-8')
        from urllib.parse import urlencode
        params = urlencode({'accessKey': app_key, 'timestamp': ts_ms, 'signature': sig})
        url = f'https://oapi.dingtalk.com/sns/getuserinfo_bycode?{params}'
        req = Request(url,
            data=json.dumps({'tmp_auth_code': auth_code}).encode('utf-8'),
            headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=10) as r:
            result = json.loads(r.read().decode('utf-8'))
        if result.get('errcode') != 0:
            app.logger.warning(f'[旧API失败] {json.dumps(result, ensure_ascii=False)[:300]}')
            return None
        user_info = result.get('user_info', {})
        return {
            'unionId': user_info.get('unionid') or user_info.get('openid'),
            'nick': user_info.get('nick') or '',
            'avatarUrl': '',
        }
    except Exception as e_old:
        try:
            body = e_old.read().decode('utf-8')[:300]
        except:
            body = str(e_old)[:300]
        app.logger.warning(f'[旧API异常] {body}')
        return None

def _sign_session(payload):
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(',',':')).encode('utf-8')).decode()
    sig = hmac.new(SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f'{body}.{sig}'

def _verify_session(token):
    try:
        body, sig = token.split('.')
        expect = hmac.new(SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expect): return None
        payload = json.loads(base64.urlsafe_b64decode(body.encode()).decode())
        if payload.get('accountId') and (
            not payload.get('exp') or int(payload['exp']) <= int(time.time())
        ):
            return None
        return payload
    except Exception:
        return None

# ==================== 自定义学生（钉钉账户绑定） ====================

def _ensure_custom_table():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS custom_students(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner TEXT NOT NULL,
        data TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    db.commit()

def _current_owner():
    """从 Authorization: Bearer <sessionToken> 解出 owner，否则用 IP 作为兜底"""
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        info = _verify_session(auth[7:])
        if info and info.get('unionId'): return f"dt:{info['unionId']}"
    return f"ip:{request.remote_addr}"

@app.route('/api/custom-students', methods=['GET'])
@anonymize_response
def list_custom_students():
    _ensure_custom_table()
    db = get_db()
    cursor = db.execute('SELECT id, data, created_at FROM custom_students WHERE owner = ? ORDER BY id', (_current_owner(),))
    items = []
    for row in cursor.fetchall():
        d = json.loads(row['data'])
        d['_id'] = f"c_{row['id']}"
        d['_custom'] = True
        d['_createdAt'] = row['created_at']
        items.append(d)
    return jsonify({'students': items})

@app.route('/api/custom-students', methods=['POST'])
def add_custom_student():
    _ensure_custom_table()
    data = request.get_json() or {}
    if not data.get('displayName'):
        return jsonify({'error': 'displayName 必填'}), 400
    db = get_db()
    cursor = db.execute('INSERT INTO custom_students(owner, data) VALUES(?, ?)',
                        (_current_owner(), json.dumps(data, ensure_ascii=False)))
    db.commit()
    return jsonify({'id': f'c_{cursor.lastrowid}', 'message': '已添加'})

@app.route('/api/custom-students/<id_str>', methods=['DELETE'])
def del_custom_student(id_str):
    _ensure_custom_table()
    if not id_str.startswith('c_'): return jsonify({'error': '无效 id'}), 400
    try:
        sid = int(id_str[2:])
    except ValueError:
        return jsonify({'error': '无效 id'}), 400
    db = get_db()
    db.execute('DELETE FROM custom_students WHERE id = ? AND owner = ?', (sid, _current_owner()))
    db.commit()
    return jsonify({'message': '已删除'})

# ==================== 社团抢课（活动岛） ====================

CLUB_MAX_SIGNUPS_PER_STUDENT = 1

# 简单分类规则：按关键字猜类别（art / sport / tech / subject）
def _club_category(name):
    n = (name or '').lower()
    SPORT  = ['足球','篮球','击剑','街舞','武术','体育','跑','操','运动','排球','乒乓','羽毛球','游泳','橄榄球','跳绳','跆拳道','体适能','啦啦操','羽毛球','足球社团']
    TECH   = ['乐高','机器','无人机','创客','编程','ai','电子','工程','科技','创新','发明','木工','om','赛车','ai趣']
    ART    = ['艺术','画','绘','美术','戏','舞','音乐','合唱','器乐','陶','粘土','纸','拓印','书法','摄影','插画','播音','戏剧','小囡']
    SUBJ   = ['阅读','书虫','英语','abc','数学','古诗','诗文','辩论','作文','心理','启蒙','哲学','财商','史','地理','文学','劳动','健康','卫生','天文']
    for kw in SPORT:
        if kw in n: return 'sport'
    for kw in TECH:
        if kw in n: return 'tech'
    for kw in ART:
        if kw in n: return 'art'
    for kw in SUBJ:
        if kw in n: return 'subject'
    return 'subject'

def _club_emoji(name, cat):
    n = (name or '')
    if '足球' in n: return '⚽'
    if '篮球' in n: return '🏀'
    if '击剑' in n: return '🤺'
    if '街舞' in n or '舞' in n: return '💃'
    if '乐高' in n: return '🧩'
    if '机器' in n: return '🤖'
    if '无人机' in n: return '🛸'
    if '画' in n or '绘' in n or '美术' in n: return '🎨'
    if '音乐' in n or '合唱' in n or '器乐' in n: return '🎵'
    if '阅读' in n or '书' in n: return '📖'
    if '诗' in n: return '📜'
    if 'ABC' in n or 'abc' in n or '英语' in n: return '🔤'
    if '编程' in n or 'AI' in n or 'ai' in n: return '💻'
    if '辩论' in n: return '🗣️'
    if '心理' in n: return '🧠'
    if '财商' in n: return '💰'
    if '天文' in n: return '🔭'
    if '戏' in n: return '🎭'
    return {'sport':'⚽','tech':'🤖','art':'🎨','subject':'📚'}.get(cat,'🎯')

def _ensure_club_signups_table():
    """保存社团目录与抢课结果；静态目录仅作为首次初始化种子。"""
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS club_course_catalog(
        id TEXT PRIMARY KEY,
        semester TEXT NOT NULL,
        campus TEXT NOT NULL,
        name TEXT NOT NULL,
        teacher TEXT NOT NULL,
        weekday TEXT NOT NULL,
        location TEXT NOT NULL,
        capacity INTEGER NOT NULL CHECK(capacity > 0),
        note TEXT DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    course_columns = {row[1] for row in db.execute('PRAGMA table_info(club_course_catalog)').fetchall()}
    for name, definition in (
        ('selection_mode', "TEXT NOT NULL DEFAULT 'selectable'"),
        ('eligible_grades', "TEXT NOT NULL DEFAULT '[]'"),
        ('source_number', 'INTEGER'),
    ):
        if name not in course_columns:
            db.execute(f'ALTER TABLE club_course_catalog ADD COLUMN {name} {definition}')
    db.execute('''CREATE TABLE IF NOT EXISTS club_signups(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL,
        course_id TEXT NOT NULL,
        semester TEXT NOT NULL,
        registered_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(student_id, course_id, semester)
    )''')
    signup_columns = {row[1] for row in db.execute('PRAGMA table_info(club_signups)').fetchall()}
    for name, definition in (
        ('status', "TEXT NOT NULL DEFAULT 'pending'"),
        ('confirmed_by', 'TEXT'),
        ('confirmed_at', 'TEXT'),
    ):
        if name not in signup_columns:
            db.execute(f'ALTER TABLE club_signups ADD COLUMN {name} {definition}')
    db.execute('''CREATE TABLE IF NOT EXISTS club_admission_windows(
        semester TEXT NOT NULL,
        grade TEXT NOT NULL,
        preview_at TEXT NOT NULL,
        open_at TEXT NOT NULL,
        close_at TEXT NOT NULL,
        published_at TEXT,
        updated_by TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(semester, grade)
    )''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_club_signups_course ON club_signups(course_id, semester)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_club_signups_student ON club_signups(student_id, semester)')
    for sort_order, course in enumerate(COURSES):
        db.execute(
            '''INSERT OR IGNORE INTO club_course_catalog(
                   id, semester, campus, name, teacher, weekday, location,
                   capacity, note, is_active, sort_order, selection_mode,
                   eligible_grades, source_number
               ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)''',
            (
                course['id'], course['semester'], course['campus'],
                course['name'], course['teacher'], course['weekday'],
                course['location'], course['capacity'], course.get('note', ''),
                sort_order, course.get('selection_mode', 'selectable'),
                json.dumps(course.get('eligible_grades', []), ensure_ascii=False),
                course.get('source_number'),
            )
        )
    db.commit()


def _club_courses_from_db(db, include_inactive=False):
    where = '' if include_inactive else 'AND is_active = 1'
    rows = db.execute(
        f'''SELECT id, semester, campus, name, teacher, weekday, location,
                   capacity, note, is_active, selection_mode,
                   eligible_grades, source_number
            FROM club_course_catalog
            WHERE semester = ? {where}
            ORDER BY sort_order, created_at, id''',
        (CLUB_SEMESTER,)
    ).fetchall()
    return [dict(row) for row in rows]


def _club_course_from_db(db, course_id, include_inactive=False):
    active_clause = '' if include_inactive else 'AND is_active = 1'
    row = db.execute(
        f'''SELECT id, semester, campus, name, teacher, weekday, location,
                   capacity, note, is_active, selection_mode,
                   eligible_grades, source_number
            FROM club_course_catalog
            WHERE id = ? AND semester = ? {active_clause}''',
        (course_id, CLUB_SEMESTER)
    ).fetchone()
    return dict(row) if row else None


def _club_general_teacher():
    user = _current_user()
    allowed = (
        user['role'] == 'admin'
        or (user['role'] == 'teacher' and user.get('sub_role') == 'general')
    )
    if not allowed:
        return None, (jsonify({'error': '仅总务老师可管理社团'}), 403)
    return user, None


CLUB_GRADES = ('一年级', '二年级', '三年级', '四年级', '五年级')


def _club_grades(course):
    raw = course.get('eligible_grades') or '[]'
    if isinstance(raw, list):
        values = raw
    else:
        try:
            values = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            values = re.split(r'[,，、\s]+', str(raw))
    return [grade for grade in CLUB_GRADES if grade in values]


def _club_window(db, grade):
    if not grade:
        return None
    row = db.execute(
        '''SELECT semester, grade, preview_at, open_at, close_at, published_at
           FROM club_admission_windows WHERE semester = ? AND grade = ?''',
        (CLUB_SEMESTER, grade)
    ).fetchone()
    return dict(row) if row else None


def _club_datetime(value):
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _club_phase(course, grade, window, now=None):
    mode = course.get('selection_mode') or 'selectable'
    if mode == 'draft':
        return 'draft'
    if grade and grade not in _club_grades(course):
        return 'ineligible'
    if not window:
        return 'open' if not DISABLE_DEMO and mode == 'selectable' else (
            'information' if not DISABLE_DEMO and mode == 'info_only' else 'unscheduled'
        )
    now = now or datetime.now()
    preview_at = _club_datetime(window.get('preview_at'))
    open_at = _club_datetime(window.get('open_at'))
    close_at = _club_datetime(window.get('close_at'))
    if not all((preview_at, open_at, close_at)) or now < preview_at:
        return 'hidden'
    if mode == 'info_only':
        return 'information'
    if window.get('published_at'):
        return 'published'
    if now < open_at:
        return 'preview'
    if now < close_at:
        return 'open'
    return 'review'


def _club_phase_message(phase):
    return {
        'draft': '资料待补充',
        'unscheduled': '开放时间待设置',
        'preview': '社团信息预览中',
        'open': '正在开放申请',
        'review': '申请已截止，等待学校确认',
        'published': '录取结果已发布',
        'information': '信息展示，无需选课',
        'ineligible': '不面向当前年级',
    }.get(phase, '')


def _club_course_payload(course, count=0, include_counts=False, phase=None):
    cat = _club_category(course['name'])
    capacity = course['capacity']
    payload = {
        key: value for key, value in course.items()
        if key not in ('capacity', 'is_active', 'eligible_grades', 'selection_mode')
    }
    mode = course.get('selection_mode') or 'selectable'
    phase = phase or ('draft' if mode == 'draft' else 'unscheduled')
    payload.update({
        'remaining': max(0, capacity - count),
        'full': mode == 'selectable' and count >= capacity,
        'cat': cat,
        'ic': _club_emoji(course['name'], cat),
        'time': course['weekday'],
        'selectionMode': mode,
        'eligibleGrades': _club_grades(course),
        'phase': phase,
        'phaseMessage': _club_phase_message(phase),
        'canApply': mode == 'selectable' and phase == 'open',
    })
    if include_counts and mode == 'selectable':
        payload.update({
            'capacity': capacity,
            'count': count,
            'max': capacity,
        })
    else:
        payload.pop('remaining')
    return payload


def _club_signup_user():
    user = _current_user()
    if user['role'] != 'parent' or not user['bound_id_card']:
        return None, (jsonify({
            'success': False,
            'error': '请先以家长身份登录并绑定学生后再抢课',
        }), 401)
    return user, None


def _club_user_grade(user, db):
    if user.get('bound_grade'):
        return user['bound_grade']
    if not user.get('bound_id_card'):
        return None
    student_table = _students_table(_resolve_campus())
    if not db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (student_table,)
    ).fetchone():
        return None
    row = db.execute(
        f'SELECT grade_name FROM {student_table} WHERE id_card = ?',
        (user['bound_id_card'],)
    ).fetchone()
    return row['grade_name'] if row else None


@app.route('/api/clubs/windows', methods=['GET'])
def list_club_windows():
    """总务查看本学期各年级的展示、抢课和发布时间。"""
    _, error = _club_general_teacher()
    if error:
        return error
    _ensure_club_signups_table()
    rows = get_db().execute(
        '''SELECT grade, preview_at, open_at, close_at, published_at
           FROM club_admission_windows WHERE semester = ? ORDER BY grade''',
        (CLUB_SEMESTER,)
    ).fetchall()
    return jsonify({'semester': CLUB_SEMESTER, 'windows': [dict(row) for row in rows]})


@app.route('/api/clubs/windows/<grade>', methods=['PUT'])
def save_club_window(grade):
    """总务按年级设置预览、开放和截止时间。"""
    user, error = _club_general_teacher()
    if error:
        return error
    if grade not in CLUB_GRADES:
        return jsonify({'error': '年级无效'}), 400
    data = request.get_json(silent=True) or {}
    values = {
        key: str(data.get(key) or '').strip()
        for key in ('previewAt', 'openAt', 'closeAt')
    }
    parsed = [_club_datetime(values[key]) for key in ('previewAt', 'openAt', 'closeAt')]
    if not all(parsed):
        return jsonify({'error': '预览、开放和截止时间均为必填'}), 400
    if not parsed[0] <= parsed[1] < parsed[2]:
        return jsonify({'error': '时间顺序必须为：预览时间 ≤ 开放时间 < 截止时间'}), 400
    _ensure_club_signups_table()
    db = get_db()
    db.execute(
        '''INSERT INTO club_admission_windows(
               semester, grade, preview_at, open_at, close_at,
               published_at, updated_by, updated_at
           ) VALUES(?, ?, ?, ?, ?, NULL, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(semester, grade) DO UPDATE SET
               preview_at = excluded.preview_at,
               open_at = excluded.open_at,
               close_at = excluded.close_at,
               published_at = NULL,
               updated_by = excluded.updated_by,
               updated_at = CURRENT_TIMESTAMP''',
        (
            CLUB_SEMESTER, grade, values['previewAt'], values['openAt'],
            values['closeAt'], user['identity'],
        )
    )
    db.commit()
    return jsonify({'success': True, 'window': _club_window(db, grade)})


@app.route('/api/clubs/windows/<grade>/publish', methods=['POST'])
def publish_club_results(grade):
    """总务确认并发布一个年级的最终录取结果。"""
    user, error = _club_general_teacher()
    if error:
        return error
    if grade not in CLUB_GRADES:
        return jsonify({'error': '年级无效'}), 400
    _ensure_club_signups_table()
    db = get_db()
    window = _club_window(db, grade)
    if not window:
        return jsonify({'error': '请先设置该年级的抢课时间'}), 409
    close_at = _club_datetime(window['close_at'])
    if not close_at or datetime.now() < close_at:
        return jsonify({'error': '抢课尚未截止，不能发布结果'}), 409
    student_table = _students_table(_resolve_campus())
    table_exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (student_table,)
    ).fetchone()
    if not table_exists:
        return jsonify({'error': '当前校区学生名册不存在'}), 409
    published_at = datetime.now().isoformat(timespec='minutes')
    cursor = db.execute(
        f'''UPDATE club_signups
            SET status = 'confirmed', confirmed_by = ?, confirmed_at = ?
            WHERE semester = ? AND status = 'pending'
              AND student_id IN (
                  SELECT id_card FROM {student_table} WHERE grade_name = ?
              )''',
        (user['identity'], published_at, CLUB_SEMESTER, grade)
    )
    db.execute(
        '''UPDATE club_admission_windows
           SET published_at = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP
           WHERE semester = ? AND grade = ?''',
        (published_at, user['identity'], CLUB_SEMESTER, grade)
    )
    db.commit()
    return jsonify({
        'success': True,
        'grade': grade,
        'confirmed': cursor.rowcount,
        'publishedAt': published_at,
    })


@app.route('/api/clubs', methods=['GET'])
def list_clubs():
    """本学期可抢课程目录，附实时报名人数与剩余名额。"""
    _ensure_club_signups_table()
    db = get_db()
    user = _current_user()
    include_counts = (
        user['role'] == 'admin'
        or (user['role'] == 'teacher' and user.get('sub_role') == 'general')
    )
    counts = {
        row['course_id']: row['count']
        for row in db.execute(
            '''SELECT course_id, COUNT(*) AS count
               FROM club_signups
               WHERE semester = ? AND status != 'rejected'
               GROUP BY course_id''',
            (CLUB_SEMESTER,)
        ).fetchall()
    }
    items = []
    campus = (request.args.get('campus') or '').strip()
    viewer_grade = _club_user_grade(user, db)
    window = _club_window(db, viewer_grade)
    for course in _club_courses_from_db(db):
        if campus and campus != course['campus']:
            continue
        phase = _club_phase(course, viewer_grade, window)
        if user['role'] == 'parent' and phase in ('hidden', 'draft', 'ineligible', 'unscheduled'):
            continue
        if user['role'] == 'teacher' and user.get('sub_role') == 'class' and phase in ('draft', 'ineligible'):
            continue
        items.append(_club_course_payload(
            course,
            counts.get(course['id'], 0),
            include_counts=include_counts,
            phase=phase,
        ))
    return jsonify({
        'clubs': items,
        'total': len(items),
        'semester': CLUB_SEMESTER,
        'grade': viewer_grade,
        'window': window,
    })


@app.route('/api/clubs', methods=['POST'])
def create_club():
    """总务老师新增本学期社团。"""
    _, error = _club_general_teacher()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    fields = {
        key: str(data.get(key) or '').strip()
        for key in ('campus', 'name', 'teacher', 'weekday', 'location')
    }
    if any(not value for value in fields.values()):
        return jsonify({'error': '校区、社团名称、负责老师、上课日和地点均为必填'}), 400
    limits = {'campus': 30, 'name': 60, 'teacher': 60, 'weekday': 20, 'location': 80}
    if any(len(fields[key]) > limit for key, limit in limits.items()):
        return jsonify({'error': '社团信息过长，请缩短后重试'}), 400
    selection_mode = str(data.get('selectionMode') or 'selectable').strip()
    if selection_mode not in ('selectable', 'info_only', 'draft'):
        return jsonify({'error': '社团类型无效'}), 400
    eligible_grades = [
        grade for grade in data.get('eligibleGrades', []) if grade in CLUB_GRADES
    ]
    if not eligible_grades:
        return jsonify({'error': '至少选择一个适用年级'}), 400
    try:
        capacity = int(data.get('capacity') or 1)
    except (TypeError, ValueError):
        return jsonify({'error': '人数上限必须是正整数'}), 400
    if capacity < 1 or capacity > 500:
        return jsonify({'error': '人数上限须在 1 到 500 之间'}), 400
    note = str(data.get('note') or '').strip()
    if len(note) > 500:
        return jsonify({'error': '备注不能超过 500 个字符'}), 400

    _ensure_club_signups_table()
    db = get_db()
    sort_order = db.execute(
        '''SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order
           FROM club_course_catalog WHERE semester = ?''',
        (CLUB_SEMESTER,)
    ).fetchone()['next_order']
    course_id = f"custom-{secrets.token_hex(6)}"
    db.execute(
        '''INSERT INTO club_course_catalog(
               id, semester, campus, name, teacher, weekday, location,
               capacity, note, is_active, sort_order, selection_mode,
               eligible_grades
           ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)''',
        (
            course_id, CLUB_SEMESTER, fields['campus'], fields['name'],
            fields['teacher'], fields['weekday'], fields['location'],
            capacity, note, sort_order, selection_mode,
            json.dumps(eligible_grades, ensure_ascii=False),
        )
    )
    db.commit()
    course = _club_course_from_db(db, course_id)
    return jsonify({
        'success': True,
        'message': '社团已新增',
        'course': _club_course_payload(course, 0, include_counts=True),
    }), 201


@app.route('/api/clubs/<course_id>', methods=['PATCH'])
def update_club_capacity(course_id):
    """总务老师调整本学期社团信息。"""
    _, error = _club_general_teacher()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    _ensure_club_signups_table()
    db = get_db()
    course = _club_course_from_db(db, course_id)
    if not course:
        return jsonify({'error': '社团不存在或已下架'}), 404
    count = db.execute(
        '''SELECT COUNT(*) AS count FROM club_signups
           WHERE course_id = ? AND semester = ? AND status != 'rejected' ''',
        (course_id, CLUB_SEMESTER)
    ).fetchone()['count']
    updates = []
    params = []
    if 'capacity' in data:
        try:
            capacity = int(data.get('capacity'))
        except (TypeError, ValueError):
            return jsonify({'error': '人数上限必须是正整数'}), 400
        if capacity < 1 or capacity > 500:
            return jsonify({'error': '人数上限须在 1 到 500 之间'}), 400
        if capacity < count:
            return jsonify({'error': f'人数上限不能低于当前已提交人数（{count} 人）'}), 409
        updates.append('capacity = ?')
        params.append(capacity)
    for api_name, column, limit in (
        ('campus', 'campus', 30), ('name', 'name', 60),
        ('teacher', 'teacher', 60), ('weekday', 'weekday', 20),
        ('location', 'location', 80), ('note', 'note', 500),
    ):
        if api_name in data:
            value = str(data.get(api_name) or '').strip()
            if api_name != 'note' and not value:
                return jsonify({'error': f'{api_name}不能为空'}), 400
            if len(value) > limit:
                return jsonify({'error': '社团信息过长，请缩短后重试'}), 400
            updates.append(f'{column} = ?')
            params.append(value)
    if 'selectionMode' in data:
        mode = str(data.get('selectionMode') or '').strip()
        if mode not in ('selectable', 'info_only', 'draft'):
            return jsonify({'error': '社团类型无效'}), 400
        updates.append('selection_mode = ?')
        params.append(mode)
    if 'eligibleGrades' in data:
        eligible_grades = [grade for grade in data.get('eligibleGrades', []) if grade in CLUB_GRADES]
        if not eligible_grades:
            return jsonify({'error': '至少选择一个适用年级'}), 400
        updates.append('eligible_grades = ?')
        params.append(json.dumps(eligible_grades, ensure_ascii=False))
    if not updates:
        return jsonify({'error': '没有需要更新的社团信息'}), 400
    params.extend([course_id, CLUB_SEMESTER])
    db.execute(
        f'''UPDATE club_course_catalog
            SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND semester = ? AND is_active = 1''',
        params
    )
    db.commit()
    course = _club_course_from_db(db, course_id)
    return jsonify({
        'success': True,
        'message': '人数上限已更新',
        'course': _club_course_payload(course, count, include_counts=True),
    })


@app.route('/api/clubs/<course_id>', methods=['DELETE'])
def archive_club(course_id):
    """总务老师下架社团，保留已有报名记录。"""
    _, error = _club_general_teacher()
    if error:
        return error
    _ensure_club_signups_table()
    db = get_db()
    course = _club_course_from_db(db, course_id)
    if not course:
        return jsonify({'error': '社团不存在或已下架'}), 404
    db.execute(
        '''UPDATE club_course_catalog
           SET is_active = 0, updated_at = CURRENT_TIMESTAMP
           WHERE id = ? AND semester = ?''',
        (course_id, CLUB_SEMESTER)
    )
    db.commit()
    return jsonify({'success': True, 'message': '社团已下架'})


@app.route('/api/clubs/<course_id>/signups', methods=['GET'])
def list_club_signup_students(course_id):
    """总务老师查看指定课程在当前学期的报名学生。"""
    _, error = _club_general_teacher()
    if error:
        return error
    _ensure_club_signups_table()
    db = get_db()
    course = _club_course_from_db(db, course_id, include_inactive=True)
    if not course:
        return jsonify({'error': '社团不存在'}), 404
    student_table = _students_table(_resolve_campus())
    student_table_exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (student_table,)
    ).fetchone()
    if student_table_exists:
        rows = db.execute(
            f'''SELECT cs.student_id, cs.created_at, cs.status, cs.confirmed_at,
                       s.name, s.grade_name, s.class_name
                FROM club_signups cs
                LEFT JOIN {student_table} s ON s.id_card = cs.student_id
                WHERE cs.course_id = ? AND cs.semester = ?
                ORDER BY {_grade_sort_sql('s.grade_name')}, s.class_name, s.name, cs.student_id''',
            (course_id, CLUB_SEMESTER)
        ).fetchall()
    else:
        rows = db.execute(
            '''SELECT student_id, created_at, status, confirmed_at,
                      NULL AS name, NULL AS grade_name, NULL AS class_name
               FROM club_signups
               WHERE course_id = ? AND semester = ?
               ORDER BY student_id''',
            (course_id, CLUB_SEMESTER)
        ).fetchall()

    students = [{
        'studentId': row['student_id'],
        'name': row['name'] or row['student_id'],
        'grade': row['grade_name'] or '',
        'class': row['class_name'] or '',
        'registeredAt': row['created_at'],
        'status': row['status'],
        'confirmedAt': row['confirmed_at'],
    } for row in rows]
    return jsonify({
        'course': _club_course_payload(
            course, len(students), include_counts=True
        ),
        'students': students,
        'total': len(students),
        'semester': CLUB_SEMESTER,
    })


@app.route('/api/clubs/class-signups', methods=['GET'])
def list_class_club_signups():
    """班主任查看自己班每名学生在当前学期选择的社团。"""
    user = _current_user()
    if user['role'] != 'teacher' or user.get('sub_role') != 'class':
        return jsonify({'error': '仅班主任可查看本班社团报名'}), 403
    grade = user.get('bound_grade')
    klass = user.get('bound_class')
    if not grade or not klass:
        return jsonify({'error': '班主任账号尚未绑定年级和班级'}), 403

    _ensure_club_signups_table()
    db = get_db()
    student_table = _students_table(_resolve_campus())
    table_exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (student_table,)
    ).fetchone()
    if not table_exists:
        return jsonify({
            'grade': grade,
            'class': klass,
            'semester': CLUB_SEMESTER,
            'students': [],
            'totalStudents': 0,
            'signedStudents': 0,
        })

    rows = db.execute(
        f'''SELECT s.id_card, s.name,
                   c.id AS course_id, c.name AS course_name,
                   c.teacher AS course_teacher, c.weekday,
                   c.location, c.campus, cs.status, cs.confirmed_at
            FROM {student_table} s
            LEFT JOIN club_signups cs
              ON cs.student_id = s.id_card AND cs.semester = ?
            LEFT JOIN club_course_catalog c
              ON c.id = cs.course_id AND c.semester = cs.semester
            WHERE s.grade_name = ? AND s.class_name = ?
            ORDER BY s.name, s.id_card, c.weekday, c.name''',
        (CLUB_SEMESTER, grade, klass)
    ).fetchall()

    students = []
    by_student = {}
    for row in rows:
        student = by_student.get(row['id_card'])
        if student is None:
            student = {
                'studentId': row['id_card'],
                'name': row['name'] or row['id_card'],
                'clubs': [],
            }
            by_student[row['id_card']] = student
            students.append(student)
        if row['course_id']:
            student['clubs'].append({
                'id': row['course_id'],
                'name': row['course_name'],
                'teacher': row['course_teacher'],
                'weekday': row['weekday'],
                'location': row['location'],
                'campus': row['campus'],
                'status': row['status'],
                'confirmedAt': row['confirmed_at'],
            })

    return jsonify({
        'grade': grade,
        'class': klass,
        'semester': CLUB_SEMESTER,
        'students': students,
        'totalStudents': len(students),
        'signedStudents': sum(bool(student['clubs']) for student in students),
        'confirmedStudents': sum(
            any(club.get('status') == 'confirmed' for club in student['clubs'])
            for student in students
        ),
    })


@app.route('/api/clubs/signups', methods=['GET'])
def club_signups():
    """当前绑定学生在本学期的抢课结果。"""
    user, error = _club_signup_user()
    if error:
        return error
    _ensure_club_signups_table()
    db = get_db()
    rows = db.execute(
        '''SELECT course_id, created_at, status, confirmed_at
           FROM club_signups
           WHERE student_id = ? AND semester = ?
           ORDER BY created_at, id''',
        (user['bound_id_card'], CLUB_SEMESTER)
    ).fetchall()
    signups = []
    for row in rows:
        course = _club_course_from_db(db, row['course_id'], include_inactive=True)
        if course:
            grade = _club_user_grade(user, db)
            window = _club_window(db, grade)
            published = bool(window and window.get('published_at'))
            result_status = 'confirmed' if published and row['status'] == 'confirmed' else 'pending'
            signups.append({
                **_club_course_payload(
                    course,
                    phase=_club_phase(course, grade, window),
                ),
                'created_at': row['created_at'],
                'status': result_status,
                'confirmedAt': row['confirmed_at'] if result_status == 'confirmed' else None,
            })
    return jsonify({
        'signups': signups,
        'semester': CLUB_SEMESTER,
        'maxSignups': CLUB_MAX_SIGNUPS_PER_STUDENT,
    })


@app.route('/api/clubs/signups', methods=['POST'])
def create_club_signup():
    """原子抢占一个课程名额。"""
    user, error = _club_signup_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    course_id = (data.get('course_id') or '').strip()
    _ensure_club_signups_table()
    db = get_db()
    try:
        db.execute('BEGIN IMMEDIATE')
        course = _club_course_from_db(db, course_id)
        if not course:
            db.rollback()
            return jsonify({'success': False, 'error': '课程不存在或已下架'}), 404
        grade = _club_user_grade(user, db)
        if not grade:
            db.rollback()
            return jsonify({'success': False, 'error': '学生年级信息缺失，暂时无法提交'}), 409
        if course.get('selection_mode') != 'selectable':
            db.rollback()
            return jsonify({'success': False, 'error': '该社团仅展示信息，不开放选课'}), 409
        if grade not in _club_grades(course):
            db.rollback()
            return jsonify({'success': False, 'error': '该社团不面向当前学生年级'}), 403
        phase = _club_phase(course, grade, _club_window(db, grade))
        if phase != 'open':
            db.rollback()
            return jsonify({
                'success': False,
                'error': _club_phase_message(phase) or '当前不在开放抢课时间',
                'code': 'CLUB_NOT_OPEN',
            }), 409
        exists = db.execute(
            '''SELECT 1 FROM club_signups
               WHERE student_id = ? AND course_id = ? AND semester = ?''',
            (user['bound_id_card'], course_id, CLUB_SEMESTER)
        ).fetchone()
        if exists:
            db.rollback()
            return jsonify({'success': False, 'error': '该学生已提交过社团申请'}), 409

        conflict = db.execute(
            '''SELECT c.name
               FROM club_signups cs
               JOIN club_course_catalog c
                 ON c.id = cs.course_id AND c.semester = cs.semester
               WHERE cs.student_id = ? AND cs.semester = ?
                 AND cs.status != 'rejected' AND c.weekday = ?
               LIMIT 1''',
            (user['bound_id_card'], CLUB_SEMESTER, course['weekday'])
        ).fetchone()
        if conflict:
            db.rollback()
            return jsonify({
                'success': False,
                'error': f"上课时间冲突：{course['weekday']}已报名“{conflict['name']}”",
                'code': 'CLUB_TIME_CONFLICT',
            }), 409

        student_signup_count = db.execute(
            '''SELECT COUNT(*) AS count FROM club_signups
               WHERE student_id = ? AND semester = ? AND status != 'rejected' ''',
            (user['bound_id_card'], CLUB_SEMESTER)
        ).fetchone()['count']
        if student_signup_count >= CLUB_MAX_SIGNUPS_PER_STUDENT:
            db.rollback()
            return jsonify({
                'success': False,
                'error': f'每名学生最多报名 {CLUB_MAX_SIGNUPS_PER_STUDENT} 门社团',
                'code': 'CLUB_LIMIT_REACHED',
            }), 409

        count = db.execute(
            '''SELECT COUNT(*) AS count FROM club_signups
               WHERE course_id = ? AND semester = ? AND status != 'rejected' ''',
            (course_id, CLUB_SEMESTER)
        ).fetchone()['count']
        if count >= course['capacity']:
            db.rollback()
            return jsonify({'success': False, 'error': '课程名额已满'}), 409

        db.execute(
            '''INSERT INTO club_signups(
                   student_id, course_id, semester, registered_by, status
               ) VALUES(?, ?, ?, ?, 'pending')''',
            (user['bound_id_card'], course_id, CLUB_SEMESTER, user['identity'])
        )
        db.commit()
    except sqlite3.Error:
        db.rollback()
        app.logger.exception('club signup failed')
        return jsonify({'success': False, 'error': '抢课繁忙，请稍后重试'}), 503

    return jsonify({
        'success': True,
        'message': '申请已提交，等待学校确认',
        'status': 'pending',
    }), 201


@app.route('/api/clubs/signups/<course_id>', methods=['DELETE'])
def delete_club_signup(course_id):
    """取消当前绑定学生的一条课程报名。"""
    user, error = _club_signup_user()
    if error:
        return error
    _ensure_club_signups_table()
    db = get_db()
    course = _club_course_from_db(db, course_id, include_inactive=True)
    if not course:
        return jsonify({'success': False, 'error': '课程不存在'}), 404
    grade = _club_user_grade(user, db)
    phase = _club_phase(course, grade, _club_window(db, grade))
    if phase != 'open':
        return jsonify({'success': False, 'error': '只能在开放抢课期间撤回申请'}), 409
    cursor = db.execute(
        '''DELETE FROM club_signups
           WHERE student_id = ? AND course_id = ? AND semester = ?
             AND status = 'pending' ''',
        (user['bound_id_card'], course_id, CLUB_SEMESTER)
    )
    db.commit()
    if cursor.rowcount == 0:
        return jsonify({'success': False, 'error': '没有找到该课程的报名记录'}), 404
    return jsonify({'success': True, 'message': '已撤回申请'})

# ==================== 证书奖项（带扫描件） ====================

def _classify_wuyu(competition, prize, subject):
    """根据奖状内容自动分类到五育（德智体美劳）"""
    text = f'{competition or ""} {prize or ""} {subject or ""}'
    rules = [
        ('德育', ['品德','三好','优秀少先','文明','雷锋','美德','孝','诚信','守纪','行为规范','道德','标兵','礼仪','爱国','思想品德','遵纪','好人好事']),
        ('体育', ['体育','运动','篮球','足球','排球','乒乓','羽毛','游泳','田径','体操','武术','跳绳','跑步','广播操','阳光体育','健康','体质','跳远','跳高','投掷','接力','运动会','跆拳道','滑冰','滑雪']),
        ('美育', ['艺术','美术','绘画','书法','音乐','舞蹈','合唱','乐器','钢琴','小提琴','摄影','手工','创作','作品展','文化节','艺术节','表演','朗诵','演讲','讲故事','节','画','歌','曲','剧','海报','设计']),
        ('劳育', ['劳动','实践','值日','卫生','环保','种','养','志愿者','服务','公益','自理','美食','烹饪','烘焙','制作','维修','家务','种植','养殖','清扫']),
        ('智育', ['学科','语文','数学','英语','科学','物理','化学','生物','地理','历史','竞赛','奥数','作文','阅读','知识','素养','成绩','学霸','学习','探究','实验','计算','编程','信息','科技','创新','发明','课题','研究','考试','测试','学科素养','表彰']),
    ]
    # 先看 subject
    subj = (subject or '').strip()
    subj_map = {'艺术':'美育','美术':'美育','音乐':'美育','书法':'美育','体育':'体育','劳动':'劳育','品德':'德育'}
    for k, v in subj_map.items():
        if k in subj:
            return v
    # 再看关键词
    for name, keywords in rules:
        for kw in keywords:
            if kw in text:
                return name
    return '智育'

def _ensure_award_certs_table():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS award_certs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id_card TEXT,
        student_name TEXT NOT NULL,
        grade TEXT NOT NULL,
        class_name TEXT NOT NULL,
        campus TEXT NOT NULL DEFAULT "",
        wuyu TEXT NOT NULL DEFAULT "",
        competition TEXT,
        prize TEXT,
        subject TEXT,
        teacher TEXT,
        image_path TEXT NOT NULL,
        source TEXT,
        uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(student_name, grade, class_name, image_path)
    )''')
    # 兼容旧表：如果 campus 列不存在则添加
    try:
        db.execute('ALTER TABLE award_certs ADD COLUMN campus TEXT NOT NULL DEFAULT ""')
    except:
        pass
    # 兼容旧表：如果 wuyu 列不存在则添加
    try:
        db.execute('ALTER TABLE award_certs ADD COLUMN wuyu TEXT NOT NULL DEFAULT ""')
    except:
        pass
    db.execute('CREATE INDEX IF NOT EXISTS idx_certs_name ON award_certs(student_name)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_certs_class ON award_certs(grade, class_name)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_certs_campus ON award_certs(campus)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_certs_wuyu ON award_certs(wuyu)')
    db.commit()

@app.route('/api/award-certs', methods=['GET'])
def list_award_certs():
    """列出证书奖项。
       家长：服务端强制只返回自己绑定学生的证书（按 student_id_card 或姓名）
       老师/管理员：可按 grade / class / name 自由过滤"""
    _ensure_award_certs_table()
    u = _current_user()
    if u['role'] == 'none':
        return jsonify({'certs': [], 'total': 0, 'note': '未认证'})
    db = get_db()
    name = request.args.get('name')
    grade = request.args.get('grade')
    klass = request.args.get('class')
    offset = max(0, int(request.args.get('offset', 0)))
    limit = min(int(request.args.get('limit', 200)), 5000)

    where, params = [], []

    if u['role'] == 'parent':
        # 强制锁定到绑定学生：先按 id_card，找不到再用 students.name 兜底（校区隔离）
        bound_id = u.get('bound_id_card')
        bound_name = None
        if bound_id:
            campus = _resolve_campus()
            stable = _students_table(campus)
            row = db.execute(f'SELECT name FROM {stable} WHERE id_card = ?', (bound_id,)).fetchone()
            if row:
                bound_name = row['name']
        if bound_id and bound_name:
            where.append('(student_id_card = ? OR student_name = ?)')
            params.extend([bound_id, bound_name])
        elif bound_id:
            where.append('student_id_card = ?'); params.append(bound_id)
        elif bound_name:
            where.append('student_name = ?'); params.append(bound_name)
        else:
            return jsonify({'certs': [], 'total': 0, 'note': '家长未绑定学生'})
    else:
        # 老师/管理员才能用 query 过滤
        # 按 campus 隔离：每个校区只看自己的奖状
        campus = (request.args.get('campus') or '').strip()
        if campus:
            where.append('campus = ?'); params.append(campus)
        # 按五育分类过滤
        wuyu = (request.args.get('wuyu') or '').strip()
        if wuyu:
            where.append('wuyu = ?'); params.append(wuyu)
        if name:
            like_pattern = f'%{name}%'
            where.append('(student_name LIKE ? OR competition LIKE ?)')
            params.extend([like_pattern, like_pattern])
        if grade:
            where.append('grade = ?'); params.append(grade)
        if klass:
            where.append('class_name = ?'); params.append(klass)

    # 先查总数
    count_sql = 'SELECT COUNT(*) FROM award_certs'
    if where:
        count_sql += ' WHERE ' + ' AND '.join(where)
    total = db.execute(count_sql, params.copy()).fetchone()[0]

    sql = 'SELECT * FROM award_certs'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY grade, class_name, student_name, id LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    rows = db.execute(sql, params).fetchall()
    return jsonify({'certs': [dict(r) for r in rows], 'total': total, 'offset': offset, 'limit': limit, 'has_more': offset + limit < total})

@app.route('/api/award-certs/<int:cert_id>', methods=['PUT'])
def update_award_cert(cert_id):
    """教师/管理员修改奖状字段：student_name, grade, class_name, wuyu"""
    u = _current_user()
    if u['role'] not in ('teacher', 'admin'):
        return jsonify({'error': '仅教师和管理员可编辑'}), 403
    data = request.get_json() or {}
    db = get_db()
    _ensure_award_certs_table()
    row = db.execute('SELECT * FROM award_certs WHERE id = ?', (cert_id,)).fetchone()
    if not row:
        return jsonify({'error': '奖状不存在'}), 404
    allowed = ['student_name', 'grade', 'class_name', 'wuyu']
    updates = {}
    for k in allowed:
        v = data.get(k)
        if v is not None and str(v).strip():
            updates[k] = str(v).strip()
    if not updates:
        return jsonify({'error': '没有可更新的字段'}), 400
    sets = ', '.join(f'{k}=?' for k in updates)
    vals = list(updates.values())
    vals.append(cert_id)
    db.execute(f'UPDATE award_certs SET {sets} WHERE id=?', vals)
    db.commit()
    app.logger.info(f'[奖状编辑] id={cert_id} 更新: {updates}')
    return jsonify({'success': True, 'updated': updates})

@app.route('/api/award-certs/<int:cert_id>', methods=['DELETE'])
def delete_award_cert(cert_id):
    """教师/管理员删除奖状"""
    u = _current_user()
    if u['role'] not in ('teacher', 'admin'):
        return jsonify({'error': '仅教师和管理员可删除'}), 403
    db = get_db()
    _ensure_award_certs_table()
    row = db.execute('SELECT * FROM award_certs WHERE id = ?', (cert_id,)).fetchone()
    if not row:
        return jsonify({'error': '奖状不存在'}), 404
    db.execute('DELETE FROM award_certs WHERE id = ?', (cert_id,))
    db.commit()
    app.logger.info(f'[奖状删除] id={cert_id} student={row["student_name"]} competition={row["competition"]}')
    return jsonify({'success': True, 'deleted': {'id': cert_id, 'student_name': row['student_name']}})

@app.route('/api/awards', methods=['GET'])
def list_awards():
    """列出 awards 表中的比赛奖项，支持 campus 过滤加速加载"""
    u = _current_user()
    if u['role'] == 'none':
        return jsonify({'awards': [], 'total': 0})
    db = get_db()
    name = request.args.get('name')
    subject = request.args.get('subject')
    campus = (request.args.get('campus') or '').strip()
    offset = max(0, int(request.args.get('offset', 0)))
    limit = min(int(request.args.get('limit', 200)), 2000)
    where, params = [], []
    
    # campus → school_name 映射
    campus_school_map = {'benbu':'本部校区','baolin':'宝林校区','luojing':'罗泾校区'}
    school_name = campus_school_map.get(campus)
    
    if u['role'] == 'parent':
        bound_id = u.get('bound_id_card')
        if bound_id:
            p_campus = _resolve_campus()
            p_stable = _students_table(p_campus)
            row = db.execute(f'SELECT name FROM {p_stable} WHERE id_card = ?', (bound_id,)).fetchone()
            if row:
                where.append('a.name = ?'); params.append(row['name'])
    else:
        if name:
            like_pattern = f'%{name}%'
            where.append('(a.name LIKE ? OR a.competition LIKE ?)')
            params.extend([like_pattern, like_pattern])
        if subject:
            where.append('a.subject = ?'); params.append(subject)
    
    # JOIN students 按校区过滤（awards 表无 school_name，通过 name+class_name 关联）
    stable = _students_table(campus)
    if school_name:
        if campus == 'luojing':
            # 罗泾独立表无 school_name 列，直接 JOIN
            sql = f'''SELECT a.* FROM awards a INNER JOIN {stable} s
                     ON a.name = s.name AND a.class_name = s.class_name WHERE 1=1'''
        else:
            sql = f'''SELECT a.* FROM awards a INNER JOIN {stable} s
                     ON a.name = s.name AND a.class_name = s.class_name
                     WHERE s.school_name = ?'''
            params.insert(0, school_name)
        if where:
            sql += ' AND ' + ' AND '.join(where)
        sql += ' ORDER BY a.created_at DESC, a.name LIMIT ?'
    else:
        sql = 'SELECT a.* FROM awards a'
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY a.created_at DESC, a.name LIMIT ?'
    # 先查总数（去掉 ORDER BY 和 LIMIT）
    count_sql = sql.replace('SELECT a.* FROM', 'SELECT COUNT(*) FROM').split(' ORDER BY ')[0]
    total = db.execute(count_sql, params.copy()).fetchone()[0]

    params.extend([limit, offset])
    sql += ' OFFSET ?'
    rows = db.execute(sql, params).fetchall()
    return jsonify({'awards': [dict(r) for r in rows], 'total': total, 'offset': offset, 'limit': limit, 'has_more': offset + limit < total})

# ==================== 美育岛 · 数字美术馆 ====================
import zipfile, shutil as _shutil_art

ART_WORKS_DIR = os.path.join(BASE_DIR, 'assets', 'art-works')
os.makedirs(ART_WORKS_DIR, exist_ok=True)
ART_TMP_DIR = os.path.join(BASE_DIR, 'assets', 'art-tmp')
os.makedirs(ART_TMP_DIR, exist_ok=True)
ART_VALID_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
ART_SEP_RE = re.compile(r'[+_\-—–\s]+')

def _art_fix_chinese(name):
    """zip 内中文文件名常被 cp437 编码，转回 gbk"""
    try:
        return name.encode('cp437').decode('gbk')
    except Exception:
        return name

def _art_safe_segment(seg):
    """把奖项名 / 学生名 / 作品名清洗成可入文件系统的安全字符串"""
    seg = (seg or '').strip().strip('.')
    seg = re.sub(r'[\\/:*?"<>|]', '_', seg)
    return seg or '未命名'

def _art_parse_filename(stem):
    """宽松分隔符切学生名 / 作品名;若无分隔符,作品名置空"""
    stem = stem.strip()
    if not stem:
        return None, None
    parts = ART_SEP_RE.split(stem, 1)
    student = parts[0].strip()
    title = parts[1].strip() if len(parts) > 1 else ''
    return student or None, title or '未命名作品'

def _art_classify_level(award_name):
    """按关键字给奖项配色:gold | silver | bronze | merit"""
    s = str(award_name or '')
    if re.search(r'特等|金奖|一等', s): return 'gold'
    if re.search(r'银奖|二等', s):       return 'silver'
    if re.search(r'铜奖|三等', s):       return 'bronze'
    return 'merit'

def _ensure_art_works_table():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS art_works(
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
    db.execute('CREATE INDEX IF NOT EXISTS idx_art_award ON art_works(award_name)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_art_student ON art_works(student_name)')
    db.commit()

def _art_import_zip(zip_path, uploaded_by='system', default_award_name=None):
    """解析 zip → 落盘 → 入库。返回 (inserted, skipped, errors[], award_name)"""
    _ensure_art_works_table()
    db = get_db()

    award_name = default_award_name or _art_safe_segment(
        os.path.splitext(os.path.basename(zip_path))[0]
    )
    level = _art_classify_level(award_name)
    safe_award = _art_safe_segment(award_name)
    dest_root = os.path.join(ART_WORKS_DIR, safe_award)
    os.makedirs(dest_root, exist_ok=True)

    inserted = 0
    skipped = 0
    errors = []

    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            fixed = _art_fix_chinese(info.filename)
            parts = [p for p in fixed.replace('\\', '/').split('/') if p]
            if not parts:
                continue
            # 跳过 macOS 元数据
            if any(p.startswith('.') or p.startswith('__MACOSX') for p in parts):
                continue
            fname = parts[-1]
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ART_VALID_EXTS:
                continue
            stem = os.path.splitext(fname)[0]
            student, title = _art_parse_filename(stem)
            if not student:
                errors.append(f'解析失败: {fname}')
                continue
            # 子目录里若像 "<年级>/<班级>" 顺便存
            grade = parts[-3] if len(parts) >= 3 else None
            klass = parts[-2] if len(parts) >= 2 else None

            safe_student = _art_safe_segment(student)
            safe_title = _art_safe_segment(title)
            dest_name = f'{safe_student}_{safe_title}{ext}'
            dest_path = os.path.join(dest_root, dest_name)
            # 文件已存在且大小一致 → 跳文件,继续入库(可能数据库还没记录)
            need_write = not (os.path.exists(dest_path) and os.path.getsize(dest_path) == info.file_size)
            if need_write:
                with z.open(info) as src, open(dest_path, 'wb') as dst:
                    _shutil_art.copyfileobj(src, dst)

            rel = f'assets/art-works/{safe_award}/{dest_name}'
            try:
                db.execute(
                    'INSERT INTO art_works(award_name, award_level, student_name, work_title, image_path, grade, class_name, uploaded_by) VALUES(?,?,?,?,?,?,?,?)',
                    (award_name, level, student, title, rel, grade, klass, uploaded_by)
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
    db.commit()
    return inserted, skipped, errors, award_name

@app.route('/api/art-works', methods=['GET'])
def list_art_works():
    """全员可见的数字美术馆作品列表"""
    _ensure_art_works_table()
    db = get_db()
    award = request.args.get('award')
    student = request.args.get('student')
    limit = min(int(request.args.get('limit', 500)), 2000)

    where, params = [], []
    if award:
        where.append('award_name = ?'); params.append(award)
    if student:
        where.append('student_name = ?'); params.append(student)

    sql = 'SELECT * FROM art_works'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY award_name, student_name, id LIMIT ?'
    params.append(limit)
    rows = db.execute(sql, params).fetchall()

    # 同时返回所有奖项(用于做筛选条)
    award_rows = db.execute(
        'SELECT award_name, award_level, COUNT(*) as cnt FROM art_works GROUP BY award_name ORDER BY award_name'
    ).fetchall()
    awards = [dict(r) for r in award_rows]
    return jsonify({
        'works': [dict(r) for r in rows],
        'total': len(rows),
        'awards': awards,
    })

# ═══════════════════════════════════════════════════════════
#  互动追踪（点赞/评论服务端持久化 + 数据驾驶舱）
# ═══════════════════════════════════════════════════════════

# ── Nginx 日志分析：实时页面浏览量 ──
import gzip
import glob as _glob

_nginx_cache = {'ts': 0, 'total': 0, 'today': 0}

def _nginx_page_views():
    """从 nginx access log 统计美术馆页面真实浏览量（60s 缓存）"""
    global _nginx_cache
    now = time.time()
    if now - _nginx_cache['ts'] < 60:
        return _nginx_cache['total'], _nginx_cache['today']

    log_dir = '/var/log/nginx'
    today_fmt = datetime.now().strftime('%d/%b/%Y')
    pattern = 'GET /island-art.html'

    total = 0
    today = 0

    # 当前日志
    try:
        with open(f'{log_dir}/access.log', 'r', errors='ignore') as f:
            for line in f:
                if pattern in line:
                    total += 1
                    if today_fmt in line:
                        today += 1
    except Exception:
        pass

    # 归档日志（gzip）
    for gz_file in sorted(_glob.glob(f'{log_dir}/access.log.*.gz')):
        try:
            with gzip.open(gz_file, 'rt', errors='ignore') as f:
                for line in f:
                    if pattern in line:
                        total += 1
        except Exception:
            pass

    _nginx_cache = {'ts': now, 'total': total, 'today': today}
    return total, today


def _ensure_art_interactions_table():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS art_interactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        work_id TEXT NOT NULL,
        kind TEXT NOT NULL,          -- 'like' or 'comment'
        user_name TEXT NOT NULL,
        text TEXT,                   -- comment text (null for likes)
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_ai_work ON art_interactions(work_id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_ai_kind ON art_interactions(kind)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_ai_time ON art_interactions(created_at)')
    db.commit()

@app.route('/api/art-like', methods=['POST'])
def art_like():
    """前端同步点赞到服务端"""
    data = request.get_json(force=True) or {}
    work_id = str(data.get('work_id', '')).strip()
    user_name = str(data.get('user_name', '')).strip()
    action = str(data.get('action', 'add')).strip()  # 'add' or 'remove'
    if not work_id or not user_name:
        return jsonify({'ok': False, 'error': '缺少 work_id 或 user_name'}), 400
    _ensure_art_interactions_table()
    db = get_db()
    if action == 'remove':
        db.execute("DELETE FROM art_interactions WHERE work_id=? AND kind='like' AND user_name=?",
                   (work_id, user_name))
    else:
        # dedup: 同一人对同一作品只保留一条点赞
        exists = db.execute(
            "SELECT id FROM art_interactions WHERE work_id=? AND kind='like' AND user_name=?",
            (work_id, user_name)).fetchone()
        if not exists:
            db.execute("INSERT INTO art_interactions (work_id, kind, user_name) VALUES (?, 'like', ?)",
                       (work_id, user_name))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/art-comment', methods=['POST'])
def art_comment():
    """前端同步评论到服务端"""
    data = request.get_json(force=True) or {}
    work_id = str(data.get('work_id', '')).strip()
    user_name = str(data.get('user_name', '')).strip()
    text = str(data.get('text', '')).strip()
    if not work_id or not user_name or not text:
        return jsonify({'ok': False, 'error': '缺少参数'}), 400
    _ensure_art_interactions_table()
    db = get_db()
    db.execute("INSERT INTO art_interactions (work_id, kind, user_name, text) VALUES (?, 'comment', ?, ?)",
               (work_id, user_name, text))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/dashboard', methods=['GET'])
def api_dashboard():
    """教育专家数据驾驶舱 — 实时数据聚合"""
    _ensure_art_works_table()
    _ensure_art_interactions_table()
    db = get_db()

    # KPI: 作品数
    total_works = db.execute('SELECT COUNT(*) FROM art_works').fetchone()[0]
    # 校区数（从学生表）
    school_cnt = db.execute('SELECT COUNT(DISTINCT school_name) FROM students WHERE school_name IS NOT NULL AND school_name != ""').fetchone()[0] or 3

    likes_total = db.execute("SELECT COUNT(*) FROM art_interactions WHERE kind='like'").fetchone()[0]
    comments_total = db.execute("SELECT COUNT(*) FROM art_interactions WHERE kind='comment'").fetchone()[0]
    views_total = total_works * 540  # rough page-view estimate → 已用 nginx 日志替代

    today_str = datetime.now().strftime('%Y-%m-%d')
    likes_today = db.execute("SELECT COUNT(*) FROM art_interactions WHERE kind='like' AND created_at LIKE ?", (today_str+'%',)).fetchone()[0]
    comments_today = db.execute("SELECT COUNT(*) FROM art_interactions WHERE kind='comment' AND created_at LIKE ?", (today_str+'%',)).fetchone()[0]
    views_total, views_today = _nginx_page_views()

    kpi = {
        'works': total_works, 'likes': likes_total, 'comments': comments_total,
        'views': views_total, 'schools': school_cnt,
        'likesToday': likes_today, 'commentsToday': comments_today, 'viewsToday': views_today
    }

    # 奖项分布
    award_rows = db.execute(
        'SELECT award_name, award_level, COUNT(*) as cnt FROM art_works GROUP BY award_name ORDER BY cnt DESC'
    ).fetchall()
    colors = ['#1f5346','#2BB7C4','#3FE0A0','#8FD17A','#F4C95D','#FF8E72','#7B68EE','#FF69B4','#00CED1','#FFA500']
    awards = []
    for i, r in enumerate(award_rows):
        awards.append({'label': r['award_name'], 'value': r['cnt'], 'color': colors[i % len(colors)]})

    # 组别构成（小学组为主）
    groups = [
        {'label': '小学组', 'value': total_works, 'pct': 100.0, 'color': '#38E1A3'}
    ]

    # 7天趋势（最近7天互动）
    trend_axis = []
    trend_likes = []
    trend_comments = []
    for i in range(6, -1, -1):
        d = datetime.now() - timedelta(days=i)
        ds = d.strftime('%Y-%m-%d')
        trend_axis.append(d.strftime('%m.%d'))
        trend_likes.append(db.execute(
            "SELECT COUNT(*) FROM art_interactions WHERE kind='like' AND created_at LIKE ?", (ds+'%',)).fetchone()[0])
        trend_comments.append(db.execute(
            "SELECT COUNT(*) FROM art_interactions WHERE kind='comment' AND created_at LIKE ?", (ds+'%',)).fetchone()[0])
    trend = {'axis': trend_axis, 'likes': trend_likes, 'comments': trend_comments}

    # 热门作品 TOP5（按点赞+评论总和）
    top_rows = db.execute('''
        SELECT aw.work_title, aw.student_name,
               (SELECT COUNT(*) FROM art_interactions WHERE work_id=CAST(aw.id AS TEXT) AND kind="like") as likes,
               (SELECT COUNT(*) FROM art_interactions WHERE work_id=CAST(aw.id AS TEXT) AND kind="comment") as comments
        FROM art_works aw
        ORDER BY (likes + comments) DESC LIMIT 5
    ''').fetchall()
    topWorks = []
    for r in top_rows:
        topWorks.append({
            'title': r['work_title'] or '无题',
            'author': r['student_name'] or '',
            'school': '宝山实验小学',
            'likes': r['likes'] or 0,
            'comments': r['comments'] or 0
        })

    # 学校/校区热度榜
    sch_rows = db.execute('''
        SELECT school_name as sname, COUNT(*) as cnt
        FROM students GROUP BY school_name ORDER BY cnt DESC LIMIT 8
    ''').fetchall()
    schoolRank = []
    for r in sch_rows:
        schoolRank.append({'name': r['sname'], 'score': r['cnt'] * 10})

    # 热词云：从作品标题、评论中提取
    wordCloud = []
    # 从 top 作品标题提取
    title_rows = db.execute('SELECT work_title FROM art_works ORDER BY id DESC LIMIT 30').fetchall()
    seen = set()
    for r in title_rows:
        t = (r['work_title'] or '')[:8]
        if t and t not in seen:
            seen.add(t)
            wordCloud.append({'text': t, 'weight': 5, 'kind': 'title'})
    # 从评论提取热词
    cmt_rows = db.execute("SELECT text FROM art_interactions WHERE kind='comment' AND text IS NOT NULL ORDER BY id DESC LIMIT 50").fetchall()
    cmt_seen = set()
    for r in cmt_rows:
        t = (r['text'] or '')[:8]
        if t and t not in cmt_seen:
            cmt_seen.add(t)
            wordCloud.append({'text': t, 'weight': 3, 'kind': 'comment'})

    # 实时动态流（最近20条）
    feed_rows = db.execute('''
        SELECT ai.kind, ai.user_name, ai.text, ai.created_at, ai.work_id
        FROM art_interactions ai
        ORDER BY ai.id DESC LIMIT 20
    ''').fetchall()
    feed = []
    for r in feed_rows:
        # Try to get work title
        wt = ''
        try:
            wr = db.execute('SELECT work_title FROM art_works WHERE CAST(id AS TEXT)=?', (r['work_id'],)).fetchone()
            if wr: wt = wr['work_title']
        except: pass
        feed.append({
            'kind': r['kind'],
            'user': r['user_name'],
            'work': wt,
            'note': r['text'] or '',
            'time': r['created_at'] or ''
        })

    return jsonify({
        'kpi': kpi, 'awards': awards, 'groups': groups, 'trend': trend,
        'topWorks': topWorks, 'schoolRank': schoolRank, 'wordCloud': wordCloud, 'feed': feed
    })

@app.route('/api/art-works/upload', methods=['POST'])
def upload_art_works():
    """老师/管理员上传 *奖项名*.zip,后端解压入库"""
    u = _current_user()
    if u['role'] not in ('teacher', 'admin'):
        return jsonify({'error': '仅老师/管理员可上传'}), 403
    if not _rate_check(f'art:{u["identity"]}'):
        return jsonify({'error': f'上传过于频繁(>{UPLOAD_RATE_PER_MIN} 次/分钟),请稍后重试'}), 429
    f = request.files.get('zip') or request.files.get('file')
    if not f:
        return jsonify({'error': '缺少 zip 文件(form-data 字段名: zip)'}), 400
    fname = f.filename or ''
    if not fname.lower().endswith('.zip'):
        return jsonify({'error': '仅支持 .zip'}), 400
    # zip 文件名 = 奖项名(去 .zip)
    award_from_name = _art_safe_segment(os.path.splitext(os.path.basename(fname))[0])
    # 允许 form 字段覆盖奖项名
    override_award = (request.form.get('award_name') or '').strip()
    award_name = override_award or award_from_name
    if not award_name:
        return jsonify({'error': '无法解析奖项名,请检查 zip 文件名或传 award_name'}), 400

    tmp_path = os.path.join(ART_TMP_DIR, f'upload_{int(time.time()*1000)}.zip')
    f.save(tmp_path)
    try:
        inserted, skipped, errors, aw = _art_import_zip(tmp_path, uploaded_by=u['identity'], default_award_name=award_name)
    except zipfile.BadZipFile:
        return jsonify({'error': 'zip 文件已损坏'}), 400
    finally:
        try: os.remove(tmp_path)
        except Exception: pass
    return jsonify({
        'award_name': aw,
        'inserted': inserted,
        'skipped': skipped,
        'errors': errors,
        'message': f'已导入 {inserted} 件作品(跳过 {skipped} 件已存在)'
    })

@app.route('/api/art-works/<int:wid>', methods=['DELETE'])
def delete_art_work(wid):
    """老师/管理员删除单件作品(同时删图)"""
    u = _current_user()
    if u['role'] not in ('teacher', 'admin'):
        return jsonify({'error': '仅老师/管理员可删除'}), 403
    _ensure_art_works_table()
    db = get_db()
    row = db.execute('SELECT image_path FROM art_works WHERE id = ?', (wid,)).fetchone()
    if not row:
        return jsonify({'error': '作品不存在'}), 404
    db.execute('DELETE FROM art_works WHERE id = ?', (wid,))
    db.commit()
    try:
        os.remove(os.path.join(BASE_DIR, row['image_path']))
    except Exception:
        pass
    return jsonify({'message': '已删除'})

# ==================== 周菜单（总务老师上传 / 家长查看） ====================
import shutil
UPLOAD_DIR = os.path.join(BASE_DIR, 'assets', 'menu-uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_IMAGE_EXTS = {'.png','.jpg','.jpeg','.gif','.webp','.bmp'}
ALLOWED_MENU_EXCEL_EXTS = {'.xlsx'}


def _menu_service_days(parsed):
    return [
        {
            'plan_date': day.get('plan_date'),
            'weekday': day.get('weekday'),
            'weekday_label': day.get('weekday_label'),
            'service_status': day.get('service_status', 'normal'),
            'service_note': day.get('service_note', ''),
        }
        for day in (parsed.get('days') or [])
        if day.get('plan_date')
    ]


def _decode_menu_row(row):
    item = dict(row)
    try:
        item['service_days'] = json.loads(item.pop('service_days_json', '') or '[]')
    except (TypeError, json.JSONDecodeError):
        item['service_days'] = []
    return item


def _required_menu_days(row):
    """返回该周真正需要选择的周一至周日；旧菜单保持五天兼容。"""
    try:
        days = json.loads(row['service_days_json'] or '[]')
    except (KeyError, TypeError, json.JSONDecodeError):
        days = []
    if not days:
        return {1, 2, 3, 4, 5}
    return {
        int(day['weekday']) for day in days
        if day.get('service_status') == 'normal'
        and str(day.get('weekday', '')).isdigit()
        and 1 <= int(day['weekday']) <= 7
    }


def _menu_edit_number(value):
    if value in (None, ''):
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _validate_edited_menu(parsed):
    """清洗并重新校验页面编辑后的菜单草稿。"""
    raw_days = parsed.get('days') if isinstance(parsed, dict) else None
    issues = []
    days = []
    if not isinstance(raw_days, list) or not raw_days:
        return {}, [{
            'severity':'error', 'code':'missing_days', 'field':'days',
            'message':'至少需要保留一个菜单日期',
        }]

    seen_dates = set()
    for index, raw_day in enumerate(raw_days[:7]):
        if not isinstance(raw_day, dict):
            issues.append({
                'severity':'error', 'code':'invalid_day', 'field':f'days.{index}',
                'message':f'第 {index + 1} 个日期数据无效',
            })
            continue
        plan_date = str(raw_day.get('plan_date') or '').strip()
        try:
            parsed_date = datetime.strptime(plan_date, '%Y-%m-%d').date()
        except ValueError:
            issues.append({
                'severity':'error', 'code':'invalid_date', 'field':f'days.{index}.plan_date',
                'message':f'第 {index + 1} 个日期格式无效',
            })
            continue
        weekday = parsed_date.weekday() + 1
        if plan_date in seen_dates:
            issues.append({
                'severity':'error', 'code':'duplicate_date', 'field':f'days.{index}.plan_date',
                'plan_date':plan_date, 'message':f'{plan_date} 重复出现',
            })
        seen_dates.add(plan_date)
        service_status = raw_day.get('service_status')
        if service_status not in ('normal', 'no_service'):
            service_status = 'normal'
        day = {
            'plan_date': plan_date,
            'weekday': weekday,
            'weekday_label': f"周{'一二三四五六日'[weekday - 1]}",
            'service_status': service_status,
            'service_note': str(raw_day.get('service_note') or '').strip()[:200],
            'meals': [],
        }
        if service_status == 'no_service':
            day['service_note'] = day['service_note'] or '非供餐日'
            days.append(day)
            continue

        raw_meals = raw_day.get('meals') if isinstance(raw_day.get('meals'), list) else []
        by_type = {
            str(meal.get('plan_type') or '').upper(): meal
            for meal in raw_meals if isinstance(meal, dict)
        }
        for plan_type in ('A', 'B'):
            raw_meal = by_type.get(plan_type, {})
            plan_name = str(raw_meal.get('plan_name') or '').strip()[:500]
            menu_items = raw_meal.get('menu_items')
            if not isinstance(menu_items, list):
                menu_items = re.split(r'[、，,；;\n]+', plan_name)
            menu_items = [str(item).strip()[:100] for item in menu_items if str(item).strip()][:30]
            ingredients = raw_meal.get('ingredients')
            if not isinstance(ingredients, list):
                ingredients = re.split(r'[、，,；;\n]+', str(ingredients or ''))
            ingredients = [str(item).strip()[:100] for item in ingredients if str(item).strip()][:50]
            calories = _menu_edit_number(raw_meal.get('calories_kcal'))
            protein_pct = _menu_edit_number(raw_meal.get('protein_pct'))
            fat_pct = _menu_edit_number(raw_meal.get('fat_pct'))
            vitamin_c = _menu_edit_number(raw_meal.get('vitamin_c_mg'))
            field_prefix = f'days.{index}.meal_{plan_type}'
            if not plan_name or not menu_items:
                issues.append({
                    'severity':'error', 'code':'missing_meal_items', 'field':field_prefix,
                    'plan_date':plan_date, 'message':f'{plan_date} {plan_type}餐必须填写菜品名称',
                })
            if calories is None:
                issues.append({
                    'severity':'warning', 'code':'missing_calories', 'field':f'{field_prefix}.calories_kcal',
                    'plan_date':plan_date, 'message':f'{plan_date} {plan_type}餐缺少热量',
                })
            elif not 200 <= calories <= 1500:
                issues.append({
                    'severity':'warning', 'code':'calories_outlier', 'field':f'{field_prefix}.calories_kcal',
                    'plan_date':plan_date, 'message':f'{plan_date} {plan_type}餐热量 {calories:g} kcal 需要确认',
                })
            for value, field, label in (
                (protein_pct, 'protein_pct', '蛋白质'),
                (fat_pct, 'fat_pct', '脂肪'),
            ):
                if value is not None and not 0 <= value <= 100:
                    issues.append({
                        'severity':'error', 'code':'percentage_outlier', 'field':f'{field_prefix}.{field}',
                        'plan_date':plan_date, 'message':f'{plan_date} {plan_type}餐{label}为 {value:g}%，请输入 0—100',
                    })
            if vitamin_c is not None and vitamin_c < 0:
                issues.append({
                    'severity':'error', 'code':'negative_nutrition', 'field':f'{field_prefix}.vitamin_c_mg',
                    'plan_date':plan_date, 'message':f'{plan_date} {plan_type}餐维生素C不能为负数',
                })
            day['meals'].append({
                'plan_type': plan_type,
                'plan_name': plan_name,
                'menu_items': menu_items,
                'ingredients': ingredients,
                'calories_kcal': calories,
                'protein_pct': protein_pct,
                'fat_pct': fat_pct,
                'vitamin_c_mg': vitamin_c,
            })
        days.append(day)

    days.sort(key=lambda item: item['plan_date'])
    if days:
        span = (datetime.strptime(days[-1]['plan_date'], '%Y-%m-%d').date()
                - datetime.strptime(days[0]['plan_date'], '%Y-%m-%d').date()).days
        if span > 6:
            issues.append({
                'severity':'error', 'code':'multiple_weeks_detected', 'field':'date_range',
                'message':'一个周次只能保留一个自然周，请调整日期',
            })
    normal_count = sum(day['service_status'] == 'normal' for day in days)
    if not normal_count:
        issues.append({
            'severity':'error', 'code':'no_service_days', 'field':'days',
            'message':'至少需要保留一个正常供餐日',
        })
    cleaned = {
        'title': str(parsed.get('title') or '菜单编辑结果').strip()[:200],
        'sheet_name': parsed.get('sheet_name'),
        'date_start': days[0]['plan_date'] if days else None,
        'date_end': days[-1]['plan_date'] if days else None,
        'days': days,
        'issues': issues,
        'service_day_count': normal_count,
        'original_issues': parsed.get('original_issues') or [],
    }
    return cleaned, issues

@app.route('/api/menus', methods=['GET'])
def list_menus():
    """所有人可见：列出最近的周菜单（家长选餐时看，老师管理时看）"""
    _ensure_meal_tables()
    db = get_db()
    week = request.args.get('week', type=int)
    if week:
        cur = db.execute('SELECT * FROM weekly_menus WHERE week_number = ? ORDER BY parity', (week,))
    else:
        cur = db.execute('SELECT * FROM weekly_menus ORDER BY week_number DESC LIMIT 40')
    items = [_decode_menu_row(r) for r in cur.fetchall()]
    return jsonify({'menus': items})

@app.route('/api/menus/upload', methods=['POST'])
def upload_menu():
    """总务老师上传菜单。图片+Excel先生成草稿；旧调用保持直接发布兼容。"""
    u = _current_user()
    if u['role'] not in ('teacher','admin') or (u['role']=='teacher' and u['sub_role'] != 'general'):
        return jsonify({'error': '仅总务老师/管理员可上传'}), 403
    if not _rate_check(f'menu:{u["identity"]}'):
        return jsonify({'error': f'上传过于频繁(>{UPLOAD_RATE_PER_MIN} 次/分钟),请稍后重试'}), 429
    _ensure_meal_tables()
    # 兼容 form-data 与 json
    if request.files.get('image'):
        f = request.files['image']
        ext = os.path.splitext(f.filename or '')[1].lower()
        if ext not in ALLOWED_IMAGE_EXTS:
            return jsonify({'error': '仅支持图片：'+','.join(ALLOWED_IMAGE_EXTS)}), 400
        week = request.form.get('week', type=int)
        parity = request.form.get('parity')
        date_start = request.form.get('dateStart')
        date_end = request.form.get('dateEnd')
        selection_deadline = request.form.get('selectionDeadline')
        notes = request.form.get('notes','')
        excel_file = request.files.get('excel')
    else:
        data = request.get_json() or {}
        week = data.get('week')
        parity = data.get('parity')
        date_start = data.get('dateStart')
        date_end = data.get('dateEnd')
        selection_deadline = data.get('selectionDeadline')
        notes = data.get('notes','')
        f = None
        excel_file = None
    try:
        week = int(week)
    except (TypeError, ValueError):
        return jsonify({'error':'week 必须是正整数'}), 400
    if week < 1 or parity not in ('odd','even'):
        return jsonify({'error':'week 与 parity(odd|even) 必填'}), 400
    expected_parity = 'odd' if week % 2 else 'even'
    if parity != expected_parity:
        return jsonify({
            'error': f'第 {week} 周必须选择{"奇数周" if expected_parity == "odd" else "偶数周"}',
            'expectedParity': expected_parity,
        }), 400
    selection_deadline = (selection_deadline or '').strip()
    if not selection_deadline:
        return jsonify({'error':'selectionDeadline 必填'}), 400
    try:
        datetime.fromisoformat(selection_deadline.replace('Z', '+00:00'))
    except ValueError:
        return jsonify({'error':'selectionDeadline 格式无效'}), 400
    image_path = None
    if excel_file:
        excel_ext = os.path.splitext(excel_file.filename or '')[1].lower()
        if excel_ext not in ALLOWED_MENU_EXCEL_EXTS:
            return jsonify({'error':'菜单数据仅支持 .xlsx 文件'}), 400
        excel_bytes = excel_file.read()
        if not excel_bytes:
            return jsonify({'error':'Excel 文件为空'}), 400
        if len(excel_bytes) > 20 * 1024 * 1024:
            return jsonify({'error':'Excel 文件不能超过 20MB'}), 400
        try:
            parsed = parse_menu_workbook(excel_bytes)
        except MenuWorkbookError as exc:
            return jsonify({'error':str(exc)}), 400

        issues = list(parsed.get('issues') or [])
        parsed_start = parsed.get('date_start')
        parsed_end = parsed.get('date_end')
        if date_start and parsed_start != date_start:
            issues.append({
                'severity':'warning', 'code':'date_start_mismatch', 'field':'date_start',
                'message':f'原开始日期 {date_start} 已按Excel识别结果更新为 {parsed_start}',
            })
        if date_end and parsed_end != date_end:
            issues.append({
                'severity':'warning', 'code':'date_end_mismatch', 'field':'date_end',
                'message':f'原结束日期 {date_end} 已按Excel识别结果更新为 {parsed_end}',
            })
        date_start, date_end = parsed_start, parsed_end
        parsed['original_issues'] = list(issues)

        stamp = int(time.time() * 1000)
        digest = hashlib.sha256(excel_bytes).hexdigest()[:10]
        image_name = f'menu_w{week}_{parity}_{stamp}{ext}'
        excel_name = f'menu_w{week}_{parity}_{stamp}_{digest}.xlsx'
        image_full_path = os.path.join(UPLOAD_DIR, image_name)
        excel_full_path = os.path.join(UPLOAD_DIR, excel_name)
        f.save(image_full_path)
        with open(excel_full_path, 'wb') as output:
            output.write(excel_bytes)
        image_path = f'assets/menu-uploads/{image_name}'
        excel_path = f'assets/menu-uploads/{excel_name}'
        parsed['issues'] = issues

        db = get_db()
        cur = db.execute(
            '''INSERT INTO menu_import_batches
               (week_number, parity, date_start, date_end, selection_deadline,
                image_path, excel_path, parsed_json, issues_json, uploaded_by)
               VALUES(?,?,?,?,?,?,?,?,?,?)''',
            (week, parity, date_start, date_end, selection_deadline,
             image_path, excel_path, json.dumps(parsed, ensure_ascii=False),
             json.dumps(issues, ensure_ascii=False), u['identity'])
        )
        db.commit()
        return jsonify({
            'draftId': cur.lastrowid,
            'imagePath': image_path,
            'preview': parsed,
            'issues': issues,
            'canPublish': not any(issue.get('severity') == 'error' for issue in issues),
            'message':'Excel解析完成，请核对后确认发布',
        })

    if f:
        safe_name = f'menu_w{week}_{parity}_{int(time.time())}{ext}'
        full_path = os.path.join(UPLOAD_DIR, safe_name)
        f.save(full_path)
        image_path = f'assets/menu-uploads/{safe_name}'
    db = get_db()
    # 同周次 + parity 已存在 → 覆盖（保留旧图片清理）
    old = db.execute('SELECT id, image_path FROM weekly_menus WHERE week_number=? AND parity=?', (week, parity)).fetchone()
    if old:
        if image_path and old['image_path']:
            try: os.remove(os.path.join(BASE_DIR, old['image_path']))
            except Exception: pass
        if not image_path: image_path = old['image_path']
        db.execute('''UPDATE weekly_menus
                      SET date_start=?, date_end=?, selection_deadline=?,
                          image_path=?, notes=?, uploaded_by=?
                      WHERE id=?''',
                   (date_start, date_end, selection_deadline, image_path,
                    notes, u['identity'], old['id']))
        new_id = old['id']
    else:
        cur = db.execute(
            '''INSERT INTO weekly_menus
               (week_number, parity, date_start, date_end, selection_deadline,
                image_path, notes, uploaded_by)
               VALUES(?,?,?,?,?,?,?,?)''',
            (week, parity, date_start, date_end, selection_deadline,
             image_path, notes, u['identity'])
        )
        new_id = cur.lastrowid
    db.commit()
    return jsonify({'id': new_id, 'imagePath': image_path, 'message':'已保存'})


@app.route('/api/menu-imports/<int:batch_id>', methods=['PUT'])
def update_menu_import(batch_id):
    """总务老师在不修改原 Excel 的情况下编辑并重新校验菜单草稿。"""
    u = _current_user()
    if u['role'] not in ('teacher','admin') or (u['role']=='teacher' and u['sub_role'] != 'general'):
        return jsonify({'error':'仅总务老师/管理员可编辑菜单草稿'}), 403
    _ensure_meal_tables()
    db = get_db()
    batch = db.execute('SELECT * FROM menu_import_batches WHERE id=?', (batch_id,)).fetchone()
    if not batch:
        return jsonify({'error':'菜单解析草稿不存在'}), 404
    if batch['status'] != 'draft':
        return jsonify({'error':'已发布菜单不能再修改'}), 409
    try:
        stored = json.loads(batch['parsed_json'] or '{}')
    except json.JSONDecodeError:
        return jsonify({'error':'菜单解析草稿已损坏，请重新上传'}), 409
    data = request.get_json(silent=True) or {}
    edited = {
        'title': data.get('title', stored.get('title')),
        'sheet_name': stored.get('sheet_name'),
        'days': data.get('days'),
        'original_issues': stored.get('original_issues') or stored.get('issues') or [],
    }
    cleaned, issues = _validate_edited_menu(edited)
    cleaned['edited_at'] = datetime.now().isoformat(timespec='seconds')
    cleaned['edited_by'] = u['identity']
    selection_deadline = str(data.get('selectionDeadline') or batch['selection_deadline'] or '').strip()
    try:
        datetime.fromisoformat(selection_deadline.replace('Z', '+00:00'))
    except ValueError:
        issues.append({
            'severity':'error', 'code':'invalid_deadline', 'field':'selection_deadline',
            'message':'家长选餐截止时间格式无效',
        })
    cleaned['issues'] = issues
    db.execute(
        '''UPDATE menu_import_batches
           SET date_start=?, date_end=?, selection_deadline=?, parsed_json=?, issues_json=?
           WHERE id=?''',
        (cleaned.get('date_start'), cleaned.get('date_end'), selection_deadline,
         json.dumps(cleaned, ensure_ascii=False), json.dumps(issues, ensure_ascii=False), batch_id)
    )
    db.commit()
    return jsonify({
        'draftId': batch_id,
        'preview': cleaned,
        'issues': issues,
        'canPublish': not any(issue.get('severity') == 'error' for issue in issues),
        'message':'草稿已保存并重新检查',
    })


@app.route('/api/menu-imports/<int:batch_id>/publish', methods=['POST'])
def publish_menu_import(batch_id):
    """总务老师确认解析结果后，原子发布周菜单和每日 A/B 餐。"""
    u = _current_user()
    if u['role'] not in ('teacher','admin') or (u['role']=='teacher' and u['sub_role'] != 'general'):
        return jsonify({'error':'仅总务老师/管理员可发布'}), 403
    _ensure_meal_tables()
    db = get_db()
    batch = db.execute('SELECT * FROM menu_import_batches WHERE id=?', (batch_id,)).fetchone()
    if not batch:
        return jsonify({'error':'菜单解析草稿不存在'}), 404
    if batch['status'] == 'published':
        return jsonify({'error':'该菜单已经发布'}), 409
    expected_parity = 'odd' if batch['week_number'] % 2 else 'even'
    if batch['parity'] != expected_parity:
        return jsonify({
            'error': f'第 {batch["week_number"]} 周的周类型不正确，请重新上传',
            'expectedParity': expected_parity,
        }), 409
    try:
        issues = json.loads(batch['issues_json'] or '[]')
        parsed = json.loads(batch['parsed_json'] or '{}')
    except json.JSONDecodeError:
        return jsonify({'error':'菜单解析草稿已损坏，请重新上传'}), 409
    blocking = [issue for issue in issues if issue.get('severity') == 'error']
    if blocking:
        return jsonify({'error':'菜单草稿仍有必须修正的异常，暂不能发布', 'issues':blocking}), 409
    service_days = _menu_service_days(parsed)
    if not any(day.get('service_status') == 'normal' for day in service_days):
        return jsonify({'error':'Excel中没有可发布的正常供餐日'}), 409

    old = db.execute(
        'SELECT id, image_path FROM weekly_menus WHERE week_number=? AND parity=?',
        (batch['week_number'], batch['parity'])
    ).fetchone()
    try:
        if old:
            menu_id = old['id']
            db.execute(
                '''UPDATE weekly_menus
                   SET date_start=?, date_end=?, selection_deadline=?, image_path=?,
                       notes=?, uploaded_by=?, import_batch_id=?, service_days_json=?
                   WHERE id=?''',
                (batch['date_start'], batch['date_end'], batch['selection_deadline'],
                 batch['image_path'], parsed.get('title', ''), u['identity'], batch_id,
                 json.dumps(service_days, ensure_ascii=False), menu_id)
            )
        else:
            cur = db.execute(
                '''INSERT INTO weekly_menus
                   (week_number, parity, date_start, date_end, selection_deadline,
                    image_path, notes, uploaded_by, import_batch_id, service_days_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (batch['week_number'], batch['parity'], batch['date_start'], batch['date_end'],
                 batch['selection_deadline'], batch['image_path'], parsed.get('title', ''),
                 u['identity'], batch_id, json.dumps(service_days, ensure_ascii=False))
            )
            menu_id = cur.lastrowid

        parsed_dates = [day['plan_date'] for day in parsed.get('days', []) if day.get('plan_date')]
        for plan_date in parsed_dates:
            db.execute('DELETE FROM nutrition_meal_plans WHERE plan_date=?', (plan_date,))
        for day in parsed.get('days', []):
            if day.get('service_status') != 'normal':
                continue
            for meal in day.get('meals', []):
                db.execute(
                    '''INSERT INTO nutrition_meal_plans
                       (plan_date, plan_type, plan_name, ingredients, calories_kcal,
                        protein_g, fat_g, allergens, suitable_tags, weekly_menu_id,
                        service_status, menu_items, protein_pct, fat_pct,
                        vitamin_c_mg, source_raw)
                       VALUES(?,?,?,?,?,NULL,NULL,'[]','[]',?,'normal',?,?,?,?,?)''',
                    (day['plan_date'], meal['plan_type'], meal.get('plan_name'),
                     json.dumps(meal.get('ingredients') or [], ensure_ascii=False),
                     meal.get('calories_kcal'), menu_id,
                     json.dumps(meal.get('menu_items') or [], ensure_ascii=False),
                     meal.get('protein_pct'), meal.get('fat_pct'), meal.get('vitamin_c_mg'),
                     json.dumps(meal, ensure_ascii=False))
                )
        db.execute(
            "UPDATE menu_import_batches SET status='published', published_at=CURRENT_TIMESTAMP WHERE id=?",
            (batch_id,)
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return jsonify({
        'id': menu_id,
        'publishedMeals': sum(
            len(day.get('meals', [])) for day in parsed.get('days', [])
            if day.get('service_status') == 'normal'
        ),
        'message':'菜单与餐食数据已发布',
    })

# ==================== 家长 / 老师批量选餐 ====================

def _meal_student_source(db):
    """返回当前校区的学生主表；精简 demo 数据库可能没有学生表。"""
    table = _students_table(_resolve_campus())
    exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,)
    ).fetchone()
    return table if exists else None


def _authoritative_meal_choice_source(db):
    """返回以当前学生名册为准的选餐查询字段。

    正式环境只统计仍存在于当前校区学生主表中的学生，并从主表读取姓名、
    年级和班级。这样历史选餐快照或 demo 数据不会污染当前统计。精简测试库
    没有学生主表时才兼容回退到 meal_choices 自身字段。
    """
    table = _meal_student_source(db)
    if table:
        return {
            'from': f'FROM meal_choices mc JOIN {table} roster ON roster.id_card = mc.id_card',
            'id_card': 'mc.id_card',
            'name': 'roster.name',
            'grade': 'roster.grade_name',
            'class': 'roster.class_name',
            'week': 'mc.week_number',
            'parity': 'mc.parity',
            'weekday': 'mc.weekday',
            'choice': 'mc.choice',
        }
    return {
        'from': 'FROM meal_choices mc',
        'id_card': 'mc.id_card',
        'name': 'mc.name',
        'grade': 'mc.grade_name',
        'class': 'mc.class_name',
        'week': 'mc.week_number',
        'parity': 'mc.parity',
        'weekday': 'mc.weekday',
        'choice': 'mc.choice',
    }


def _find_meal_student(db, id_card, student_userid=None):
    table = _meal_student_source(db)
    if table:
        if student_userid and 'dingtalk_userid' in _table_columns(db, table):
            return db.execute(
                f'''SELECT id_card, name, grade_name, class_name
                    FROM {table} WHERE dingtalk_userid = ?''',
                (student_userid,),
            ).fetchone()
        return db.execute(
            f'''SELECT id_card, name, grade_name, class_name
                FROM {table} WHERE id_card = ?''',
            (id_card,)
        ).fetchone()
    # 本地演示库没有学生主表，只能从已有选餐身份中恢复最小信息。
    return db.execute(
        '''SELECT id_card, name, grade_name, class_name
           FROM meal_choices WHERE id_card = ? LIMIT 1''',
        (id_card,)
    ).fetchone()


@app.route('/api/meal-choice-students', methods=['GET'])
def list_meal_choice_students():
    """班主任仅获取自己绑定班级的学生最小名单。"""
    u = _current_user()
    if u['role'] != 'teacher' or u.get('sub_role') != 'class':
        return jsonify({'error':'无权限'}), 403
    grade = u.get('bound_grade')
    klass = u.get('bound_class')
    if not grade or not klass:
        return jsonify({'error':'班主任账号尚未绑定年级和班级'}), 403
    _ensure_meal_tables()
    db = get_db()
    students = {}
    table = _meal_student_source(db)
    if table:
        rows = db.execute(
            f'''SELECT id_card, name, grade_name, class_name
                FROM {table}
                WHERE grade_name=? AND class_name=?
                ORDER BY name''',
            (grade, klass),
        ).fetchall()
        for row in rows:
            students[row['id_card']] = {
                'idCard': row['id_card'],
                'name': row['name'],
                'grade': row['grade_name'] or '',
                'class': row['class_name'] or '',
            }
    else:
        for row in db.execute(
            '''SELECT id_card, name, grade_name, class_name
               FROM meal_choices
               WHERE grade_name=? AND class_name=?
               GROUP BY id_card, name, grade_name, class_name'''
            , (grade, klass)
        ).fetchall():
            students[row['id_card']] = {
                'idCard': row['id_card'],
                'name': row['name'],
                'grade': row['grade_name'] or '',
                'class': row['class_name'] or '',
            }
    items = sorted(
        students.values(),
        key=lambda item: (item['grade'], item['class'], item['name'], item['idCard'])
    )
    return jsonify({'students': items, 'total': len(items)})

@app.route('/api/meal-choices', methods=['POST'])
def submit_meal_choices():
    """
    家长为绑定孩子提交或在截止前修改两周（周一~周日）选餐。
    Body: {
      studentIdCard, week_odd, week_even,
      choices: { odd: {1:'A',2:'B',...,7:'B'}, even: {...} }
    }
    """
    u = _current_user()
    if u['role'] != 'parent':
        return jsonify({'error':'仅学生家长可提交选餐'}), 403

    data = request.get_json() or {}
    student_name = data.get('studentName')   # demo 模式下没真实 id_card 时用 name
    id_card = u['bound_id_card']
    student_userid = u.get('bound_student_userid')
    if not id_card and not DISABLE_DEMO:
        return jsonify({'error':'家长账号尚未绑定学生'}), 403
    if not id_card:
        id_card = data.get('studentIdCard')
    if not id_card and not student_name:
        return jsonify({'error':'studentIdCard 或 studentName 必填'}), 400
    week_odd = data.get('week_odd')
    week_even = data.get('week_even')
    choices = data.get('choices') or {}
    if not week_odd or not week_even:
        return jsonify({'error':'week_odd 与 week_even 必填'}), 400
    try:
        week_odd = int(week_odd)
        week_even = int(week_even)
    except (TypeError, ValueError):
        return jsonify({'error':'week_odd 与 week_even 必须是整数'}), 400

    normalized_choices = {}
    allowed_days = {1, 2, 3, 4, 5, 6, 7}
    for parity in ('odd', 'even'):
        normalized_choices[parity] = {}
        for day, choice in (choices.get(parity) or {}).items():
            try:
                day = int(day)
            except (TypeError, ValueError):
                return jsonify({'error':'选餐日期必须为周一至周日'}), 400
            if day not in allowed_days or choice not in ('A', 'B'):
                return jsonify({'error':'选餐内容无效'}), 400
            normalized_choices[parity][day] = choice

    _ensure_meal_tables()
    db = get_db()
    student_table = _meal_student_source(db)
    if (
        DISABLE_DEMO
        and REQUIRE_STUDENT_USERID
        and student_table
        and 'dingtalk_userid' in _table_columns(db, student_table)
        and not student_userid
    ):
        return jsonify({'error':'当前账号尚未匹配到唯一学生UserID，请联系管理员核对身份'}), 409
    menu_rows = db.execute(
        '''SELECT week_number, parity, selection_deadline, service_days_json
           FROM weekly_menus
           WHERE (week_number=? AND parity='odd')
              OR (week_number=? AND parity='even')''',
        (week_odd, week_even)
    ).fetchall()
    menu_by_parity = {row['parity']: row for row in menu_rows}
    if set(menu_by_parity) != {'odd', 'even'}:
        return jsonify({'error':'本轮两周菜单尚未完整发布，暂不能提交选餐'}), 409
    for parity in ('odd', 'even'):
        menu_row = menu_by_parity[parity]
        required_days = _required_menu_days(menu_row)
        if not required_days:
            return jsonify({'error':f'{"奇数周" if parity == "odd" else "偶数周"}没有可选供餐日'}), 409
        if set(normalized_choices[parity]) != required_days:
            return jsonify({
                'error':'请完整选择本轮所有正常供餐日的餐食',
                'parity': parity,
                'requiredDays': sorted(required_days),
            }), 400
        deadline_text = (menu_row['selection_deadline'] or '').strip()
        if not deadline_text:
            return jsonify({'error':'本轮选餐截止时间尚未发布，暂不能提交选餐'}), 409
        try:
            deadline = datetime.fromisoformat(
                deadline_text.replace('Z', '+00:00')
            )
        except ValueError:
            return jsonify({'error':'本轮选餐截止时间配置无效'}), 409
        now = datetime.now(deadline.tzinfo) if deadline.tzinfo else datetime.now()
        if now >= deadline:
            return jsonify({
                'error': '本轮选餐已截止，无法提交或修改',
                'deadline': deadline_text,
            }), 409
    if id_card:
        s = _find_meal_student(db, id_card, student_userid)
        if not s:
            if DISABLE_DEMO:
                return jsonify({'error':'学生不存在'}), 404
            # 没找到真实学生，用前端传的 name + 占位 demo 班级
            s = {'name': student_name or '未知', 'grade_name': data.get('grade') or 'demo', 'class_name': data.get('class') or 'demo'}
    else:
        # demo: 仅按 name 写入
        id_card = 'demo:' + student_name
        s = {'name': student_name, 'grade_name': data.get('grade') or 'demo', 'class_name': data.get('class') or 'demo'}
    # sqlite3.Row 不能 dict 操作；s 可能是 Row 也可能是 dict
    sname = s['name']; sgrade = s['grade_name']; sclass = s['class_name']
    saved = 0
    for parity, week in (('odd', week_odd), ('even', week_even)):
        for wd, c in normalized_choices[parity].items():
            db.execute('''INSERT INTO meal_choices(id_card, name, grade_name, class_name, week_number, parity, weekday, choice, chosen_by)
                          VALUES(?,?,?,?,?,?,?,?,?)''',
                       (id_card, sname, sgrade, sclass, week, parity, wd, c, u['identity']))
            saved += 1
    db.commit()
    return jsonify({'saved': saved, 'message': f'共保存 {saved} 条选餐记录'})

@app.route('/api/meal-choices/student/<id_card>', methods=['GET'])
def get_student_meal_choices(id_card):
    """学生（家长）查自己的选餐历史；id_card 也可以是 demo 模式下的"name:陈思麟"形式"""
    _ensure_meal_tables()
    db = get_db()
    u = _current_user()
    if u['role'] != 'parent':
        return jsonify({'error':'无权限'}), 403
    if id_card.startswith('name:'):
        if DISABLE_DEMO or u['role'] != 'parent' or u.get('bound_id_card'):
            return jsonify({'error':'无权限'}), 403
        # 仅显式 demo 模式可按姓名查；正式账号必须使用绑定学籍号
        name = id_card[5:]
        cur = db.execute('SELECT week_number, parity, weekday, choice, created_at FROM meal_choices WHERE name=? ORDER BY week_number DESC, parity, weekday', (name,))
    else:
        if not _require_can_see(id_card):
            return jsonify({'error':'无权限'}), 403
        cur = db.execute('SELECT week_number, parity, weekday, choice, created_at FROM meal_choices WHERE id_card=? ORDER BY week_number DESC, parity, weekday', (id_card,))
    rows = [dict(r) for r in cur.fetchall()]
    return jsonify({'choices': rows})

@app.route('/api/meal-choices', methods=['GET'])
def list_meal_choices():
    """列出选餐记录。可按 week / grade / class / name 过滤"""
    _ensure_meal_tables()
    db = get_db()
    u = _current_user()
    week = request.args.get('week')
    grade = request.args.get('grade')
    klass = request.args.get('class')
    name = request.args.get('name')
    limit = min(int(request.args.get('limit', 5000)), 10000)

    where = []
    params = []
    if u['role'] == 'parent':
        bound_id = u.get('bound_id_card')
        if bound_id:
            where.append('id_card = ?')
            params.append(bound_id)
        else:
            return jsonify({'choices': [], 'total': 0})
    elif u['role'] == 'teacher' and u.get('sub_role') == 'class':
        if not u.get('bound_grade') or not u.get('bound_class'):
            return jsonify({'error':'班主任账号尚未绑定年级和班级'}), 403
        where.extend(['grade_name = ?', 'class_name = ?'])
        params.extend([u['bound_grade'], u['bound_class']])
        if week:
            where.append('week_number = ?')
            params.append(int(week))
        if name:
            where.append('name = ?')
            params.append(name)
    else:
        return jsonify({'error':'无权限'}), 403

    sql = 'SELECT * FROM meal_choices'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY week_number, parity, weekday, name LIMIT ?'
    params.append(limit)
    rows = [dict(r) for r in db.execute(sql, params).fetchall()]
    return jsonify({'choices': rows, 'total': len(rows)})

# ==================== 老师端：统计 ====================

@app.route('/api/grade-counts', methods=['GET'])
def grade_counts():
    """各年级 / 全校 学生人数"""
    u = _current_user()
    if u['role'] not in ('teacher', 'admin') or (u['role'] == 'teacher' and u['sub_role'] != 'general'):
        return jsonify({'error':'仅总务老师可查看全校年级统计'}), 403
    db = get_db()
    rows = db.execute(f'SELECT grade_name, COUNT(*) AS cnt FROM students GROUP BY grade_name ORDER BY {_grade_sort_sql("grade_name")}').fetchall()
    items = [{'grade': r['grade_name'] or '-', 'count': r['cnt']} for r in rows]
    total = sum(r['cnt'] for r in rows)
    return jsonify({'grades': items, 'total': total})

@app.route('/api/class/vision-stats', methods=['GET'])
def class_vision_stats():
    """全班屈光分布（最近一次测）。老师/管理员 only。
       返回每个学生的最近一次记录 + 分布桶（正常/高危/近视/弱视）"""
    u = _current_user()
    if u['role'] not in ('teacher','admin'):
        return jsonify({'error': '无权限'}), 403
    grade = request.args.get('grade') or u.get('bound_grade')
    klass = request.args.get('class') or u.get('bound_class')
    if not grade or not klass:
        return jsonify({'error': '需要 grade + class 参数'}), 400
    db = get_db()
    # 每生最近一次屈光
    rows = db.execute('''
        SELECT s.id_card, s.name, v.test_date, v.glasses_type,
               v.right_naked_acuity, v.left_naked_acuity,
               v.right_sph, v.left_sph, v.right_cyl, v.left_cyl,
               v.doctor_advice
        FROM students s
        LEFT JOIN vision_tests v ON v.id_card = s.id_card
          AND v.test_date = (SELECT MAX(test_date) FROM vision_tests WHERE id_card = s.id_card)
        WHERE s.grade_name = ? AND s.class_name = ?
        ORDER BY s.name
    ''', (grade, klass)).fetchall()

    students = []
    buckets = {'正常':0, '高危':0, '近视':0, '戴镜':0, '弱视':0, '未测':0}
    for r in rows:
        d = dict(r)
        d['name'] = mask_name(d['name'])
        adv = (r['doctor_advice'] or '')
        rn, ln = r['right_naked_acuity'], r['left_naked_acuity']
        rs, ls = r['right_sph'], r['left_sph']
        if r['test_date'] is None:
            cat = '未测'
        elif adv.startswith('2') or (r['glasses_type'] and '框架' in r['glasses_type']):
            cat = '戴镜'
        elif adv.startswith('5') or adv.startswith('6') or (rs is not None and rs <= -0.75) or (ls is not None and ls <= -0.75):
            cat = '近视'
        elif (rn is not None and rn < 4.7) or (ln is not None and ln < 4.7):
            cat = '弱视'
        elif adv.startswith('3') or adv.startswith('4'):
            cat = '高危'
        else:
            cat = '正常'
        d['category'] = cat
        buckets[cat] = buckets.get(cat, 0) + 1
        students.append(d)
    total = len(students)
    return jsonify({
        'grade': grade, 'class': klass, 'total': total,
        'buckets': [{'cat': k, 'count': v} for k, v in buckets.items()],
        'students': students,
    })

@app.route('/api/class/fitness-stats', methods=['GET'])
def class_fitness_stats():
    """全班体测合格率。返回该班最近一年体测各项目等级分布 + 总分等级 + 全班每个学生总分。"""
    u = _current_user()
    if u['role'] not in ('teacher','admin'):
        return jsonify({'error':'无权限'}), 403
    grade = request.args.get('grade') or u.get('bound_grade')
    klass = request.args.get('class') or u.get('bound_class')
    if not grade or not klass:
        return jsonify({'error':'需要 grade + class 参数'}), 400
    db = get_db()
    rows = db.execute('''
        SELECT s.id_card, s.name, f.test_year,
               f.height, f.weight, f.bmi, f.bmi_level,
               f.vital_capacity, f.vital_level,
               f.run_50m, f.run_50m_level,
               f.sit_reach, f.sit_reach_level,
               f.jump_stand, f.jump_stand_level,
               f.jump_rope, f.jump_rope_level,
               f.sit_up, f.sit_up_level,
               f.total_score, f.total_level
        FROM students s
        LEFT JOIN fitness_tests f ON f.id_card = s.id_card
          AND f.test_year = (SELECT MAX(test_year) FROM fitness_tests WHERE id_card = s.id_card)
        WHERE s.grade_name = ? AND s.class_name = ?
        ORDER BY s.name
    ''', (grade, klass)).fetchall()

    item_keys = [
        ('vital_level','肺活量'), ('run_50m_level','50米跑'),
        ('sit_reach_level','坐位体前屈'), ('jump_stand_level','立定跳远'),
        ('jump_rope_level','一分钟跳绳'), ('sit_up_level','一分钟仰卧起坐'),
        ('total_level','总分等级'),
    ]
    LEVELS = ['优秀','良好','及格','不及格','未测']
    items = []
    for key, label in item_keys:
        cnt = {lv: 0 for lv in LEVELS}
        for r in rows:
            lv = r[key] or '未测'
            if lv not in cnt: cnt['未测'] += 1
            else: cnt[lv] += 1
        items.append({'key': key, 'label': label, 'levels': cnt})

    students = []
    for r in rows:
        d = dict(r)
        d['name'] = mask_name(d['name'])
        students.append(d)

    return jsonify({
        'grade': grade, 'class': klass,
        'test_year': max((r['test_year'] for r in rows if r['test_year']), default=None),
        'total': len(students),
        'items': items, 'levels': LEVELS,
        'students': students,
    })

@app.route('/api/meal-stats/class-summary', methods=['GET'])
def stats_class_summary():
    """班级粒度 A/B 餐人数汇总（按 grade 过滤；不指定则全部）"""
    u = _current_user()
    if u['role'] not in ('teacher','admin') or (u['role'] == 'teacher' and u['sub_role'] != 'general'):
        return jsonify({'error':'仅总务老师可查看全校班级汇总'}), 403
    _ensure_meal_tables()
    db = get_db()
    grade = request.args.get('grade')
    week = request.args.get('week', type=int)
    parity = request.args.get('parity')   # 'odd' | 'even'
    source = _authoritative_meal_choice_source(db)
    base_sql = f'''SELECT {source['grade']} AS grade_name,
                          {source['class']} AS class_name,
                          {source['week']} AS week_number,
                          {source['parity']} AS parity,
                          {source['weekday']} AS weekday,
                          {source['choice']} AS choice,
                          COUNT(DISTINCT {source['id_card']}) AS cnt
                   {source['from']} WHERE {source['weekday']} BETWEEN 1 AND 5'''
    params = []
    if grade:
        base_sql += f" AND {source['grade']} = ?"
        params.append(grade)
    if week:
        base_sql += f" AND {source['week']} = ?"
        params.append(week)
    if parity:
        base_sql += f" AND {source['parity']} = ?"
        params.append(parity)
    base_sql += ' GROUP BY 1, 2, 3, 4, 5, 6'
    base_sql += f" ORDER BY {_grade_sort_sql(source['grade'])}, {source['class']}, {source['week']}, {source['parity']}, {source['weekday']}"
    cur = db.execute(base_sql, params)
    out = {}
    for r in cur.fetchall():
        key = (r['grade_name'] or '-', r['class_name'] or '-', r['week_number'], r['parity'])
        out.setdefault(key, {})
        out[key][f"{r['weekday']}{r['choice']}"] = r['cnt']
    rows = [{'grade': k[0], 'class': k[1], 'week': k[2], 'parity': k[3], **v}
            for k, v in out.items()]
    return jsonify({'rows': rows})

@app.route('/api/meal-stats/grade', methods=['GET'])
def stats_grade():
    """总务老师：全校、年级、班级的周一至周五 A/B 人数。"""
    u = _current_user()
    if u['role'] not in ('teacher','admin') or (u['role'] == 'teacher' and u['sub_role'] != 'general'):
        return jsonify({'error':'仅总务老师可查看年级选餐统计'}), 403
    _ensure_meal_tables()
    db = get_db()
    source = _authoritative_meal_choice_source(db)
    week = request.args.get('week', type=int)
    where = f"WHERE {source['weekday']} BETWEEN 1 AND 5"
    if week:
        where += f" AND {source['week']} = ?"
    params = (week,) if week else ()
    detail_rows = db.execute(f'''
        SELECT {source['grade']} AS grade_name,
               {source['class']} AS class_name,
               {source['week']} AS week_number,
               {source['parity']} AS parity,
               {source['weekday']} AS weekday,
               {source['choice']} AS choice,
               COUNT(DISTINCT {source['id_card']}) AS cnt
        {source['from']}
        {where}
        GROUP BY 1, 2, 3, 4, 5, 6
        ORDER BY {_grade_sort_sql(source['grade'])}, {source['class']},
                 {source['week']}, {source['parity']}, {source['weekday']}
    ''', params).fetchall()

    school = {}
    grades = {}
    classes = {}
    for r in detail_rows:
        week_key = (r['week_number'], r['parity'])
        day_key = f"{r['weekday']}{r['choice']}"
        school.setdefault(week_key, {})[day_key] = (
            school.setdefault(week_key, {}).get(day_key, 0) + r['cnt']
        )
        grade_key = (r['grade_name'] or '-', r['week_number'], r['parity'])
        grades.setdefault(grade_key, {})[day_key] = (
            grades.setdefault(grade_key, {}).get(day_key, 0) + r['cnt']
        )
        class_key = (
            r['grade_name'] or '-', r['class_name'] or '-',
            r['week_number'], r['parity'],
        )
        classes.setdefault(class_key, {})[day_key] = r['cnt']

    participant_count = db.execute(
        f"SELECT COUNT(DISTINCT {source['id_card']}) {source['from']} {where}", params
    ).fetchone()[0]
    school_rows = [
        {'scope': '全校', 'week': key[0], 'parity': key[1], **values}
        for key, values in school.items()
    ]
    grade_rows = [
        {'gradeName': key[0], 'week': key[1], 'parity': key[2], **values}
        for key, values in grades.items()
    ]
    class_rows = [
        {'grade': key[0], 'class': key[1], 'week': key[2], 'parity': key[3], **values}
        for key, values in classes.items()
    ]
    return jsonify({
        'school': school_rows,
        'rows': grade_rows,
        'classes': class_rows,
        'participantCount': participant_count,
    })

@app.route('/api/meal-stats/class', methods=['GET'])
def stats_class():
    """班主任：自己班学生在当前两周实际供餐日的 A/B 选择明细。
       总务老师可指定 grade & class 看任意班。"""
    u = _current_user()
    if u['role'] not in ('teacher','admin'):
        return jsonify({'error':'无权限'}), 403
    if u['role'] == 'teacher' and u.get('sub_role') not in ('general', 'class'):
        return jsonify({'error':'当前老师账号未配置营养配餐权限'}), 403
    _ensure_meal_tables()
    grade = request.args.get('grade') or u['bound_grade']
    klass = request.args.get('class') or u['bound_class']
    if u['role'] == 'teacher' and u['sub_role'] == 'class':
        # 班主任：强制锁定到自己班
        grade = u['bound_grade']
        klass = u['bound_class']
    if not grade or not klass:
        return jsonify({'error':'班主任账号尚未绑定年级和班级'}), 403
    week_odd = request.args.get('week_odd', type=int)
    week_even = request.args.get('week_even', type=int)
    if not week_odd or not week_even:
        return jsonify({'error':'week_odd 与 week_even 必填'}), 400
    if week_even != week_odd + 1:
        return jsonify({'error':'请选择连续的奇数周和偶数周'}), 400
    db = get_db()
    menu_rows = db.execute(
        '''SELECT parity, service_days_json FROM weekly_menus
           WHERE (week_number=? AND parity='odd')
              OR (week_number=? AND parity='even')''',
        (week_odd, week_even),
    ).fetchall()
    required_by_parity = {'odd': {1,2,3,4,5}, 'even': {1,2,3,4,5}}
    for menu_row in menu_rows:
        required_by_parity[menu_row['parity']] = _required_menu_days(menu_row)
    required_keys = {
        f'{parity}_{weekday}'
        for parity, weekdays in required_by_parity.items()
        for weekday in weekdays
    }
    required_count = len(required_keys)
    # 拿到该班所有学生
    student_table = _meal_student_source(db)
    if student_table:
        students = db.execute(
            f'''SELECT id_card, name FROM {student_table}
                WHERE grade_name=? AND class_name=? ORDER BY name''',
            (grade, klass),
        ).fetchall()
    else:
        students = db.execute(
            '''SELECT id_card, name FROM meal_choices
               WHERE grade_name=? AND class_name=?
               GROUP BY id_card, name ORDER BY name''',
            (grade, klass),
        ).fetchall()
    # 选餐记录也按当前权威名册归班，避免历史快照污染班主任统计。
    source = _authoritative_meal_choice_source(db)
    sql = f'''SELECT {source['id_card']} AS id_card,
                     {source['week']} AS week_number,
                     {source['parity']} AS parity,
                     {source['weekday']} AS weekday,
                     {source['choice']} AS choice
              {source['from']}
              WHERE {source['grade']}=? AND {source['class']}=?'''
    params = [grade, klass]
    week_filters = []
    if week_odd:
        week_filters.append("(parity='odd' AND week_number=?)")
        params.append(week_odd)
    if week_even:
        week_filters.append("(parity='even' AND week_number=?)")
        params.append(week_even)
    if week_filters:
        sql += ' AND (' + ' OR '.join(week_filters) + ')'
    cur = db.execute(sql, params)
    by_student = {}
    for r in cur.fetchall():
        by_student.setdefault(r['id_card'], {})[f"{r['parity']}_{r['weekday']}"] = r['choice']
    rows = []
    a_count = 0
    b_count = 0
    complete_count = 0
    for s in students:
        choices = by_student.get(s['id_card'], {})
        required_choices = {key: value for key, value in choices.items() if key in required_keys}
        student_a_count = sum(1 for value in required_choices.values() if value == 'A')
        student_b_count = sum(1 for value in required_choices.values() if value == 'B')
        selected_count = student_a_count + student_b_count
        a_count += student_a_count
        b_count += student_b_count
        if selected_count == required_count:
            complete_count += 1
        row = {
            'idCard': s['id_card'],
            'displayName': s['name'],
            'grade': grade,
            'class': klass,
            'selectedCount': selected_count,
            'missingCount': required_count - selected_count,
            'requiredCount': required_count,
            'isComplete': selected_count == required_count,
        }
        row.update(choices)
        rows.append(row)
    student_count = len(rows)
    return jsonify({
        'students': rows,
        'grade': grade,
        'class': klass,
        'weekOdd': week_odd,
        'weekEven': week_even,
        'requiredDays': {
            parity: sorted(weekdays)
            for parity, weekdays in required_by_parity.items()
        },
        'summary': {
            'studentCount': student_count,
            'completeCount': complete_count,
            'incompleteCount': student_count - complete_count,
            'aCount': a_count,
            'bCount': b_count,
        },
    })

# ==================== Excel 导出（班主任 + 总务）====================
from io import BytesIO
from flask import send_file

def _xlsx_response(wb, filename):
    """把 openpyxl Workbook 包成 Flask 下载响应"""
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    safe = quote(filename)
    resp = send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)
    # 让浏览器拿到正确编码的文件名
    resp.headers['Content-Disposition'] = f"attachment; filename={safe}; filename*=UTF-8''{safe}"
    return resp

def _styled_header(ws, headers, row=1):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    fill = PatternFill('solid', fgColor='0E5E80')
    font = Font(bold=True, color='FFFFFF', size=12)
    align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin = Side(border_style='thin', color='CFD8DD')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=row, column=c, value=h)
        cell.fill = fill; cell.font = font; cell.alignment = align; cell.border = border
    ws.row_dimensions[row].height = 28

def _auto_width(ws, default=14):
    for col_cells in ws.columns:
        col_letter = col_cells[0].column_letter
        max_len = default
        for cell in col_cells:
            v = cell.value
            if v is None: continue
            # 中文按 2 字符宽度估算
            s = str(v)
            length = sum(2 if ord(ch) > 127 else 1 for ch in s) + 2
            if length > max_len: max_len = min(length, 40)
        ws.column_dimensions[col_letter].width = max_len

def _xlsx_simple_table(title, headers, rows):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:31]
    _styled_header(ws, headers)
    for r_idx, row in enumerate(rows, 2):
        for c_idx, val in enumerate(row, 1):
            ws.cell(row=r_idx, column=c_idx, value=val)
    _auto_width(ws)
    return wb

@app.route('/api/export/class-club.xlsx', methods=['GET'])
def export_class_club():
    """班主任：本班学生当前学期社团申请与确认结果。"""
    user = _current_user()
    if user['role'] != 'teacher' or user.get('sub_role') != 'class':
        return jsonify({'error': '仅班主任可下载本班社团名单'}), 403
    grade = user.get('bound_grade')
    klass = user.get('bound_class')
    if not grade or not klass:
        return jsonify({'error': '班主任账号尚未绑定年级和班级'}), 403

    _ensure_club_signups_table()
    db = get_db()
    student_table = _students_table(_resolve_campus())
    if not db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (student_table,),
    ).fetchone():
        rows = []
    else:
        records = db.execute(
            f'''SELECT s.id_card, s.name, cs.status,
                       c.name AS course_name, c.weekday, c.location,
                       c.teacher AS course_teacher
                FROM {student_table} s
                LEFT JOIN club_signups cs
                  ON cs.student_id = s.id_card AND cs.semester = ?
                 AND cs.status != 'rejected'
                LEFT JOIN club_course_catalog c
                  ON c.id = cs.course_id AND c.semester = cs.semester
                WHERE s.grade_name = ? AND s.class_name = ?
                ORDER BY s.name, s.id_card, c.name''',
            (CLUB_SEMESTER, grade, klass),
        ).fetchall()
        status_text = {'pending': '待确认', 'confirmed': '已确认'}
        rows = [[
            row['id_card'], row['name'], grade, klass,
            status_text.get(row['status'], '未提交'),
            row['course_name'] or '', row['weekday'] or '',
            row['location'] or '', row['course_teacher'] or '',
        ] for row in records]

    headers = ['学籍号', '姓名', '年级', '班级', '状态', '社团', '上课时间', '地点', '负责老师']
    wb = _xlsx_simple_table(f'{grade}{klass}社团', headers, rows)
    return _xlsx_response(wb, f'{grade}{klass}_{CLUB_SEMESTER}_社团名单.xlsx')

@app.route('/api/export/class-vision.xlsx', methods=['GET'])
def export_class_vision():
    """班主任 / 总务：全班屈光分布 → Excel"""
    u = _current_user()
    if u['role'] not in ('teacher','admin'):
        return jsonify({'error':'无权限'}), 403
    grade = request.args.get('grade') or u.get('bound_grade')
    klass = request.args.get('class') or u.get('bound_class')
    if not grade or not klass:
        return jsonify({'error':'需要 grade + class'}), 400
    db = get_db()
    rows = db.execute('''
        SELECT s.id_card, s.name, v.test_date, v.glasses_type,
               v.right_naked_acuity, v.left_naked_acuity,
               v.right_corrected_acuity, v.left_corrected_acuity,
               v.right_sph, v.left_sph, v.right_cyl, v.left_cyl,
               v.right_kh, v.left_kh, v.right_kv, v.left_kv,
               v.right_al, v.left_al, v.doctor_advice
        FROM students s
        LEFT JOIN vision_tests v ON v.id_card = s.id_card
          AND v.test_date = (SELECT MAX(test_date) FROM vision_tests WHERE id_card = s.id_card)
        WHERE s.grade_name=? AND s.class_name=?
        ORDER BY s.name
    ''', (grade, klass)).fetchall()
    headers = ['学籍号','姓名','最近测试日','戴镜方式',
               '右眼裸眼','左眼裸眼','右眼戴镜','左眼戴镜',
               '右眼球镜','左眼球镜','右眼柱镜','左眼柱镜',
               '右眼角膜H','左眼角膜H','右眼角膜V','左眼角膜V',
               '右眼眼轴','左眼眼轴','医生建议']
    data = [[r[k] for k in ('id_card','name','test_date','glasses_type',
            'right_naked_acuity','left_naked_acuity','right_corrected_acuity','left_corrected_acuity',
            'right_sph','left_sph','right_cyl','left_cyl',
            'right_kh','left_kh','right_kv','left_kv',
            'right_al','left_al','doctor_advice')] for r in rows]
    wb = _xlsx_simple_table(f'{grade}{klass}屈光', headers, data)
    return _xlsx_response(wb, f'{grade}{klass}_全班屈光.xlsx')

@app.route('/api/export/class-fitness.xlsx', methods=['GET'])
def export_class_fitness():
    """班主任 / 总务：全班体测 → Excel（最近一年）"""
    u = _current_user()
    if u['role'] not in ('teacher','admin'):
        return jsonify({'error':'无权限'}), 403
    grade = request.args.get('grade') or u.get('bound_grade')
    klass = request.args.get('class') or u.get('bound_class')
    if not grade or not klass:
        return jsonify({'error':'需要 grade + class'}), 400
    db = get_db()
    rows = db.execute('''
        SELECT s.id_card, s.name, f.test_year,
               f.height, f.weight, f.bmi, f.bmi_level,
               f.vital_capacity, f.vital_level,
               f.run_50m, f.run_50m_level,
               f.sit_reach, f.sit_reach_level,
               f.jump_stand, f.jump_stand_level,
               f.jump_rope, f.jump_rope_level,
               f.sit_up, f.sit_up_level,
               f.total_score, f.total_level
        FROM students s
        LEFT JOIN fitness_tests f ON f.id_card = s.id_card
          AND f.test_year = (SELECT MAX(test_year) FROM fitness_tests WHERE id_card = s.id_card)
        WHERE s.grade_name=? AND s.class_name=?
        ORDER BY s.name
    ''', (grade, klass)).fetchall()
    headers = ['学籍号','姓名','测试学年',
               '身高(cm)','体重(kg)','BMI','BMI等级',
               '肺活量','肺活量等级','50米跑(s)','50米跑等级',
               '坐位体前屈(cm)','体前屈等级','立定跳远(cm)','跳远等级',
               '一分钟跳绳','跳绳等级','一分钟仰卧起坐','仰卧起坐等级',
               '总分','总分等级']
    data = [[r[k] for k in ('id_card','name','test_year',
            'height','weight','bmi','bmi_level',
            'vital_capacity','vital_level','run_50m','run_50m_level',
            'sit_reach','sit_reach_level','jump_stand','jump_stand_level',
            'jump_rope','jump_rope_level','sit_up','sit_up_level',
            'total_score','total_level')] for r in rows]
    wb = _xlsx_simple_table(f'{grade}{klass}体测', headers, data)
    return _xlsx_response(wb, f'{grade}{klass}_全班体测.xlsx')

@app.route('/api/export/class-meal.xlsx', methods=['GET'])
def export_class_meal():
    """班主任或总务：指定班级当前两周工作日选餐 → Excel。"""
    u = _current_user()
    if u['role'] not in ('teacher', 'admin'):
        return jsonify({'error':'无权限'}), 403
    if u['role'] == 'teacher' and u.get('sub_role') not in ('class', 'general'):
        return jsonify({'error':'无权限'}), 403
    grade = request.args.get('grade') or u.get('bound_grade')
    klass = request.args.get('class') or u.get('bound_class')
    if u['role'] == 'teacher' and u.get('sub_role') == 'class':
        grade = u.get('bound_grade')
        klass = u.get('bound_class')
    show_full_names = (
        u['role'] == 'admin'
        or (u['role'] == 'teacher' and u.get('sub_role') == 'class')
    )
    week_odd = request.args.get('week_odd', type=int)
    week_even = request.args.get('week_even', type=int)
    if not grade or not klass:
        return jsonify({'error':'需要 grade + class'}), 400
    if not week_odd or not week_even or week_even != week_odd + 1:
        return jsonify({'error':'请选择连续的奇数周和偶数周'}), 400
    db = get_db()
    student_table = _meal_student_source(db)
    students = db.execute(
        f'SELECT id_card, name FROM {student_table} WHERE grade_name=? AND class_name=? ORDER BY name',
        (grade, klass),
    ).fetchall() if student_table else []
    source = _authoritative_meal_choice_source(db)
    picks = db.execute(
        f'''SELECT {source['id_card']} AS id_card,
                   {source['week']} AS week_number,
                   {source['parity']} AS parity,
                   {source['weekday']} AS weekday,
                   {source['choice']} AS choice
            {source['from']}
            WHERE {source['grade']}=? AND {source['class']}=?
              AND (({source['week']}=? AND {source['parity']}='odd')
                OR ({source['week']}=? AND {source['parity']}='even'))''',
        (grade, klass, week_odd, week_even),
    ).fetchall()
    menu_rows = db.execute(
        '''SELECT parity, service_days_json FROM weekly_menus
           WHERE (week_number=? AND parity='odd')
              OR (week_number=? AND parity='even')''',
        (week_odd, week_even),
    ).fetchall()
    required_by_parity = {'odd': {1,2,3,4,5}, 'even': {1,2,3,4,5}}
    for menu_row in menu_rows:
        required_by_parity[menu_row['parity']] = _required_menu_days(menu_row) & {1,2,3,4,5}
    required_keys = {
        f'{parity}_{weekday}'
        for parity, weekdays in required_by_parity.items()
        for weekday in weekdays
    }
    by_stu = {}
    for r in picks:
        by_stu.setdefault(r['id_card'], {})[f"{r['parity']}_{r['weekday']}"] = r['choice']
    day_labels = {1:'周一', 2:'周二', 3:'周三', 4:'周四', 5:'周五', 6:'周六', 7:'周日'}
    odd_days = sorted(required_by_parity['odd'])
    even_days = sorted(required_by_parity['even'])
    headers = ['学籍号','姓名'] + [f'奇数周·{day_labels[d]}' for d in odd_days] + [f'偶数周·{day_labels[d]}' for d in even_days] + ['总 A','总 B','未选']
    data = []
    for s in students:
        picks_s = by_stu.get(s['id_card'], {})
        required_picks = {k: v for k, v in picks_s.items() if k in required_keys}
        a_cnt = sum(1 for v in required_picks.values() if v=='A')
        b_cnt = sum(1 for v in required_picks.values() if v=='B')
        unset = len(required_keys) - a_cnt - b_cnt
        # 班主任在自己班级管理范围内需要核对和打印完整名单。
        display_name = s['name'] if show_full_names else mask_name(s['name'])
        row = [s['id_card'], display_name]
        for d in odd_days: row.append(picks_s.get(f'odd_{d}', ''))
        for d in even_days: row.append(picks_s.get(f'even_{d}', ''))
        row += [a_cnt, b_cnt, unset]
        data.append(row)
    wb = _xlsx_simple_table('学生选餐明细', headers, data)
    wb.active.title = '学生选餐明细'
    summary = wb.create_sheet('每日汇总', 0)
    summary_headers = ['周次', '周类型'] + [
        f'{day_labels[day]}{choice}餐'
        for day in range(1, 6)
        for choice in ('A', 'B')
    ] + ['A餐合计', 'B餐合计']
    _styled_header(summary, summary_headers)
    for row_index, (week, parity, parity_label) in enumerate((
        (week_odd, 'odd', '奇数周'),
        (week_even, 'even', '偶数周'),
    ), 2):
        daily_counts = []
        total_a = 0
        total_b = 0
        for day in range(1, 6):
            a_count = sum(
                1 for student_picks in by_stu.values()
                if student_picks.get(f'{parity}_{day}') == 'A'
            )
            b_count = sum(
                1 for student_picks in by_stu.values()
                if student_picks.get(f'{parity}_{day}') == 'B'
            )
            daily_counts.extend([a_count, b_count])
            total_a += a_count
            total_b += b_count
        for column, value in enumerate(
            [week, parity_label, *daily_counts, total_a, total_b], 1
        ):
            summary.cell(row=row_index, column=column, value=value)
    summary.freeze_panes = 'A2'
    _auto_width(summary)
    return _xlsx_response(wb, f'{grade}{klass}_选餐_W{week_odd}-W{week_even}.xlsx')

@app.route('/api/export/school-meal.xlsx', methods=['GET'])
def export_school_meal():
    """总务：两周全校、年级、班级工作日 A/B 人数汇总。"""
    u = _current_user()
    if u['role'] != 'teacher' or u['sub_role'] != 'general':
        if u['role'] != 'admin':
            return jsonify({'error':'仅总务/管理员可下载'}), 403
    week_odd = request.args.get('week_odd', type=int)
    week_even = request.args.get('week_even', type=int)
    if not week_odd or not week_even or week_even != week_odd + 1:
        return jsonify({'error':'请选择连续的奇数周和偶数周'}), 400
    db = get_db()
    import openpyxl
    wb = openpyxl.Workbook(); first_sheet = wb.active; wb.remove(first_sheet)
    DAY = ['周一','周二','周三','周四','周五']
    source = _authoritative_meal_choice_source(db)
    rows = db.execute(f'''
        SELECT {source['grade']} AS grade_name,
               {source['class']} AS class_name,
               {source['week']} AS week_number,
               {source['parity']} AS parity,
               {source['weekday']} AS weekday,
               {source['choice']} AS choice,
               COUNT(DISTINCT {source['id_card']}) AS cnt
        {source['from']}
        WHERE {source['weekday']} BETWEEN 1 AND 5
          AND (({source['week']}=? AND {source['parity']}='odd')
            OR ({source['week']}=? AND {source['parity']}='even'))
        GROUP BY 1, 2, 3, 4, 5, 6
        ORDER BY {_grade_sort_sql(source['grade'])}, {source['class']},
                 {source['week']}, {source['weekday']}
    ''', (week_odd, week_even)).fetchall()

    def add_summary_sheet(name, key_builder, label_headers):
        ws = wb.create_sheet(name)
        headers = label_headers + ['周次', '周类型'] + [f'{day}{choice}' for day in DAY for choice in ('A','B')]
        _styled_header(ws, headers)
        agg = {}
        for row in rows:
            key = key_builder(row) + (row['week_number'], row['parity'])
            day_key = f"{row['weekday']}{row['choice']}"
            agg.setdefault(key, {})[day_key] = agg.setdefault(key, {}).get(day_key, 0) + row['cnt']
        for row_idx, (key, values) in enumerate(agg.items(), 2):
            labels = list(key[:-2])
            for col_idx, value in enumerate(labels, 1):
                ws.cell(row=row_idx, column=col_idx, value=value)
            offset = len(labels)
            ws.cell(row=row_idx, column=offset + 1, value=key[-2])
            ws.cell(row=row_idx, column=offset + 2, value='奇数周' if key[-1] == 'odd' else '偶数周')
            for day in range(1, 6):
                ws.cell(row=row_idx, column=offset + 1 + day * 2, value=values.get(f'{day}A', 0))
                ws.cell(row=row_idx, column=offset + 2 + day * 2, value=values.get(f'{day}B', 0))
        ws.freeze_panes = 'A2'
        _auto_width(ws)

    add_summary_sheet('全校汇总', lambda row: ('全校',), ['范围'])
    add_summary_sheet('年级汇总', lambda row: (row['grade_name'] or '-',), ['年级'])
    add_summary_sheet('班级汇总', lambda row: (row['grade_name'] or '-', row['class_name'] or '-'), ['年级','班级'])

    fname = f'全校选餐_W{week_odd}-W{week_even}.xlsx'
    return _xlsx_response(wb, fname)

# ==================== 前端页面路由 ====================

@app.route('/')
def index():
    """应用入口：密码模式始终先进入登录页。"""
    if PASSWORD_LOGIN_ONLY:
        return redirect('/login.html?campus=benbu')
    return app.send_static_file('island-homepage.html')

# ═══════ 图书馆 API ═══════

@app.route('/api/library/student/<name>', methods=['GET'])
def library_student(name):
    """学生借阅历史（按学生姓名查）"""
    db = get_db()
    try:
        cur = db.execute('''
            SELECT id, title, isbn, barcode, action, operation_time, due_date,
                   borrower_name, borrower_grade, borrower_class
            FROM library_records
            WHERE borrower_name = ?
            ORDER BY operation_time DESC
            LIMIT 200
        ''', (name,))
        records = [dict(r) for r in cur.fetchall()]
        # 当前未还的书（外借但没有对应归还记录）
        borrowed = [r for r in records if r['action'] == '外借']
        # 找哪些书已还：同一书名+同一条码号有归还记录
        returned_barcodes = set()
        for r in records:
            if r['action'] == '归还' and r['barcode']:
                returned_barcodes.add(r['barcode'])
        currently_borrowed = [r for r in borrowed if r['barcode'] not in returned_barcodes]
        # 去重：同一本书只保留最新外借
        seen = set()
        unique_borrowed = []
        for r in currently_borrowed:
            if r['barcode'] not in seen:
                seen.add(r['barcode'])
                unique_borrowed.append(r)
        return jsonify({
            'records': records,
            'currently_borrowed': unique_borrowed,
            'total_borrowed': len(borrowed),
            'unique_titles': len(set(r['title'] for r in borrowed))
        })
    except Exception as e:
        return jsonify({'error': str(e), 'records': [], 'currently_borrowed': []})

@app.route('/api/library/popular', methods=['GET'])
def library_popular():
    """全校热门图书 Top 20"""
    db = get_db()
    try:
        cur = db.execute('''
            SELECT title, COUNT(*) as cnt
            FROM library_records
            WHERE action = '外借'
            GROUP BY title
            ORDER BY cnt DESC
            LIMIT 20
        ''')
        return jsonify({'books': [dict(r) for r in cur.fetchall()]})
    except Exception as e:
        return jsonify({'error': str(e), 'books': []})

@app.route('/api/library/class/<grade>/<class_name>', methods=['GET'])
def library_class(grade, class_name):
    """班级借阅排行"""
    db = get_db()
    try:
        cur = db.execute('''
            SELECT borrower_name, COUNT(*) as cnt, COUNT(DISTINCT title) as titles
            FROM library_records
            WHERE action = '外借' AND borrower_grade = ? AND borrower_class = ?
            GROUP BY borrower_name
            ORDER BY cnt DESC
            LIMIT 20
        ''', (grade, class_name))
        return jsonify({'readers': [dict(r) for r in cur.fetchall()]})
    except Exception as e:
        return jsonify({'error': str(e), 'readers': []})

# ==================== 钉钉奖状分发系统 ====================

def _entry_campus():
    raw = (request.args.get('campus') or '').strip()
    return _valid_campus(raw, 'benbu' if not raw else None)

@app.route('/dingtalk-setup')
def dingtalk_setup_page():
    """部署指引页：显示三校区链接 + 钉钉配置说明"""
    cfg = _load_campus_config()
    host = request.host_url.rstrip('/')
    campuses = []
    for cid in ['benbu', 'baolin', 'luojing']:
        c = cfg.get(cid, {})
        campuses.append({
            'id': cid,
            'name': c.get('name', cid),
            'url': f'{host}/dingtalk-awards.html?campus={cid}',
            'configured': bool(c.get('corpId') and c.get('appKey')),
        })
    # 简单 HTML 响应
    rows = ''.join(f'''
    <tr>
      <td style="padding:12px;border-bottom:1px solid #eee;font-weight:700">{c['name']}</td>
      <td style="padding:12px;border-bottom:1px solid #eee"><code>{c['url']}</code></td>
      <td style="padding:12px;border-bottom:1px solid #eee">{'✅ 已配置' if c['configured'] else '⚠️ 待填写 corpId/AppKey'}</td>
    </tr>''' for c in campuses)
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>钉钉奖状分发 · 部署指引</title>
<style>
  body{{font-family:'PingFang SC','Microsoft YaHei',sans-serif;max-width:800px;margin:40px auto;padding:20px;background:#F7FBFE;color:#1F3A4D}}
  h1{{font-size:24px;letter-spacing:2px}} h2{{font-size:17px;margin-top:24px;color:#0E5E80}}
  table{{width:100%;border-collapse:collapse;background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,.06)}}
  th{{background:#0E5E80;color:#fff;padding:12px;text-align:left;font-size:13px;letter-spacing:1px}}
  code{{background:#F4FAFD;padding:3px 8px;border-radius:6px;font-size:12px;word-break:break-all}}
  .steps{{background:#fff;border-radius:14px;padding:20px;box-shadow:0 4px 16px rgba(0,0,0,.06);line-height:2}}
  .steps li{{margin-bottom:6px;font-size:14px}}
  .note{{background:#FFF8E5;border-left:3px solid #FFC23F;padding:12px 16px;border-radius:0 10px 10px 0;margin-top:16px;font-size:13px}}
</style></head>
<body>
<h1>🏆 钉钉奖状分发 · 三校区部署</h1>

<h2>📋 校区应用链接</h2>
<p style="color:#7BB8DA;font-size:13px">每个校区的负责老师将对应链接填入钉钉开放平台的「应用首页地址」即可。</p>
<table>
  <tr><th>校区</th><th>应用链接</th><th>配置状态</th></tr>
  {rows}
</table>

<h2>🔧 钉钉配置步骤（每个校区各做一次）</h2>
<div class="steps">
<ol>
  <li>登录 <a href="https://open-dev.dingtalk.com/" target="_blank">钉钉开放平台</a>（使用本校区企业管理员账号）</li>
  <li>进入「应用开发」→「企业内部应用」→「创建应用」</li>
  <li>填写应用名称（如「宝山实验奖状」）、描述，选择「H5微应用」</li>
  <li>在「开发管理」中设置：<br>
      • 应用首页地址：填入上表中对应校区的链接<br>
      • 服务器出口IP：填写本服务器IP (203.0.113.10)</li>
  <li>在「权限管理」中开启「通讯录个人信息读取」权限</li>
  <li>发布应用，校区内家长即可在钉钉工作台看到入口</li>
  <li>将得到的 <strong>corpId、AppKey、AppSecret</strong> 发给管理员填入 <code>server/campus_config.json</code></li>
</ol>
</div>

<div class="note">
<strong>⚠️ 重要</strong>：三个校区的钉钉企业是独立的，每个校区需要在各自的钉钉企业后台创建应用。<br>
<strong>📝 配置文件</strong>：<code>server/campus_config.json</code> —— 每个校区填好 corpId / appKey / appSecret 后无需重启服务（热加载）。
</div>

<p style="margin-top:24px;color:#9AB8CA;font-size:12px;text-align:center">宝山实验智慧教育平台 · 奖状分发系统 v1.0</p>
</body></html>'''

@app.route('/dingtalk-awards.html')
def dingtalk_awards_page():
    """钉钉奖状分发入口：直接进入岛屿首页（成就岛已并入首页体系）。"""
    campus_id = _entry_campus()
    if not campus_id:
        return '无效校区', 400
    return redirect(f'/dingtalk-home?campus={campus_id}')


@app.route('/dingtalk-home')
def dingtalk_home_page():
    """钉钉微应用入口：首页。按 campus 参数注入校区专属 corpId。
    钉钉工作台配置微应用首页地址为 https://school.example.com/dingtalk-home?campus=benbu
    """
    if PASSWORD_LOGIN_ONLY:
        campus_id = _entry_campus()
        if not campus_id:
            return '无效校区', 400
        return redirect(f'/login.html?campus={quote(campus_id)}')
    return _inject_campus_page('island-homepage.html')


@app.route('/island-homepage.html')
def legacy_dingtalk_home_page():
    """兼容旧工作台入口：静态页里保留的 corpId 占位符不能直接交给钉钉 JSAPI。"""
    if PASSWORD_LOGIN_ONLY and request.args.get('auth') != '1':
        campus_id = _entry_campus()
        if not campus_id:
            return '无效校区', 400
        return redirect(f'/login.html?campus={quote(campus_id)}')
    return _inject_campus_page('island-homepage.html')


@app.route('/login.html')
def legacy_dingtalk_login_page():
    """兼容旧登录页地址，确保未登录用户也能拿到当前校区 corpId。"""
    return _inject_campus_page('login.html')


@app.route('/dingtalk-health')
def dingtalk_health_page():
    """钉钉微应用入口：健康岛。"""
    if PASSWORD_LOGIN_ONLY:
        campus_id = _entry_campus()
        if not campus_id:
            return '无效校区', 400
        return redirect(f'/login.html?campus={quote(campus_id)}')
    return _inject_campus_page('island-health.html')


@app.route('/island-health.html')
def legacy_dingtalk_health_page():
    """兼容首页及旧收藏中的健康岛静态地址。"""
    return _inject_campus_page('island-health.html')


def _inject_campus_page(page_name):
    """通用钉钉入口注入：把 __INJECT_CORP_ID__/__INJECT_CAMPUS_ID__ 替换为校区配置。"""
    campus_id = _entry_campus()
    if not campus_id:
        return '无效校区', 400
    dt_cfg = _get_campus_dt(campus_id)

    html_path = os.path.join(BASE_DIR, page_name)
    if not os.path.exists(html_path):
        return f'<h2>{page_name} 尚未部署</h2>', 404
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    # 注入校区配置 + 版本标记（强制 WebView 刷新）
    html = html.replace('__INJECT_CORP_ID__', dt_cfg.get('corpId', ''))
    html = html.replace('__INJECT_CAMPUS_ID__', campus_id)
    import hashlib
    ver = hashlib.md5(html.encode()).hexdigest()[:8]
    html = html.replace('window.BS_DINGTALK_CORP_ID', f'window.BS_PAGE_VER = "{ver}";\n    window.BS_DINGTALK_CORP_ID')
    html = re.sub(r'assets/dingtalk-bootstrap\.js\?v=[^"]*', f'assets/dingtalk-bootstrap.js?v={ver}', html)
    response = make_response(html)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/test-v4sYvwo-AzAbnieoVNqu9A.html')
def test_benbu_parent():
    """管理员专用测试页：本部校区家长模式，含解除绑定功能。
    仅通过秘密 URL 访问，不对其他用户暴露。"""
    html_path = os.path.join(BASE_DIR, 'dingtalk-awards.html')
    if not os.path.exists(html_path):
        return '<h2>dingtalk-awards.html 尚未部署</h2>', 404
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    campus_id = 'benbu'
    dt_cfg = _get_campus_dt(campus_id)
    html = html.replace('__CAMPUS_ID__', campus_id)
    html = html.replace('__CAMPUS_NAME__', dt_cfg.get('name', campus_id))
    html = html.replace('__CORP_ID__', dt_cfg.get('corpId', ''))
    html = html.replace('__SCHOOL_NAME__', dt_cfg.get('school_name', ''))
    
    import hashlib
    ver = hashlib.md5(html.encode()).hexdigest()[:8]
    html = html.replace('window.BS_DINGTALK_CORP_ID', f'window.BS_PAGE_VER = "{ver}";\n    window.BS_DINGTALK_CORP_ID')
    html = html.replace(r'assets/dingtalk-bootstrap.js?v=', f'assets/dingtalk-bootstrap.js?v={ver}')
    
    # 注入测试模式：跳过钉钉 SSO，直接以家长身份进入
    test_uid = 'parent_chen_silin'
    test_payload = {'unionId': test_uid, 'nick': '管理员测试', 'campus': 'benbu', 'ts': int(time.time())}
    body = base64.urlsafe_b64encode(json.dumps(test_payload, separators=(',',':')).encode('utf-8')).decode()
    sig = hmac.new(SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    test_token = f'{body}.{sig}'
    test_script = f'''<script>
    // 管理员测试模式：真实签名 token 直连 API，绑定状态由服务端决定
    (function(){{
        sessionStorage.setItem('bs_session_token', '{test_token}');
        sessionStorage.setItem('bs_user_nick', '管理员测试');
        // 预填学生信息（用于绑定面板快速定位）
        sessionStorage.setItem('bs_test_student_info', JSON.stringify({{
            idCard: 'BS_00841',
            name: '陈思麟',
            displayName: '陈思麟',
            grade_name: '三年级',
            class_name: '1班'
        }}));
    }})();
    </script>'''
    html = html.replace('</head>', test_script + '\n</head>')
    
    response = make_response(html)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/campus-info', methods=['GET'])
def campus_info():
    """返回校区信息（名称、学生数等）"""
    campus_id = request.args.get('campus', '').strip()
    dt_cfg = _get_campus_dt(campus_id)
    school_name = dt_cfg.get('school_name', '')
    db = get_db()
    stable = _students_table(campus_id)
    student_count = 0
    if school_name:
        if campus_id == 'luojing':
            row = db.execute(f'SELECT COUNT(*) as cnt FROM {stable}').fetchone()
        else:
            row = db.execute(f'SELECT COUNT(*) as cnt FROM {stable} WHERE school_name = ?', (school_name,)).fetchone()
        student_count = row['cnt'] if row else 0
    grades = []
    if school_name:
        if campus_id == 'luojing':
            rows = db.execute(
                f'SELECT DISTINCT grade_name FROM {stable} ORDER BY {_grade_sort_sql("grade_name")}'
            ).fetchall()
        else:
            rows = db.execute(
                f'SELECT DISTINCT grade_name FROM {stable} WHERE school_name = ? ORDER BY {_grade_sort_sql("grade_name")}',
                (school_name,)
            ).fetchall()
        grades = [r['grade_name'] for r in rows]
    return jsonify({
        'campus': campus_id,
        'name': dt_cfg.get('name', campus_id),
        'school_name': school_name,
        'student_count': student_count,
        'grades': grades,
    })

@app.route('/api/campus-students', methods=['GET'])
def campus_students():
    """按校区 + 年级 + 班级查学生列表（用于家长绑定时的下拉选择）"""
    campus_id = request.args.get('campus', '').strip()
    grade = request.args.get('grade', '').strip()
    klass = request.args.get('class', '').strip()
    search = request.args.get('search', '').strip()
    db = get_db()
    stable = _students_table(campus_id)
    where, params = [], []
    # 罗泾用独立表（无 school_name 列），其他校区用 school_name 过滤
    if campus_id == 'luojing':
        if grade:
            where.append('grade_name = ?'); params.append(grade)
        if klass:
            where.append('class_name = ?'); params.append(klass)
        if search:
            where.append('name LIKE ?'); params.append(f'%{search}%')
    else:
        dt_cfg = _get_campus_dt(campus_id)
        school_name = dt_cfg.get('school_name', '')
        if not school_name:
            return jsonify({'students': [], 'error': '未知校区'})
        where = ['school_name = ?']
        params = [school_name]
        if grade:
            where.append('grade_name = ?'); params.append(grade)
        if klass:
            where.append('class_name = ?'); params.append(klass)
        if search:
            where.append('name LIKE ?'); params.append(f'%{search}%')
    sql = f'SELECT id_card, name, grade_name, class_name, gender FROM {stable}'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += f' ORDER BY {_grade_sort_sql("grade_name")}, class_name, name LIMIT 50'
    rows = db.execute(sql, params).fetchall()
    students = []
    for r in rows:
        students.append({
            'id_card': r['id_card'],
            'name': r['name'],
            'grade_name': r['grade_name'],
            'class_name': r['class_name'],
            'gender': r['gender'],
        })
    return jsonify({'students': students})

@app.route('/api/campus-classes', methods=['GET'])
def campus_classes():
    """按校区 + 年级返回不重复的班级列表"""
    campus_id = request.args.get('campus', '').strip()
    grade = request.args.get('grade', '').strip()
    db = get_db()
    stable = _students_table(campus_id)
    if campus_id == 'luojing':
        rows = db.execute(
            f'SELECT DISTINCT class_name FROM {stable} WHERE grade_name = ? ORDER BY class_name',
            (grade,)
        ).fetchall()
    else:
        dt_cfg = _get_campus_dt(campus_id)
        school_name = dt_cfg.get('school_name', '')
        if not school_name:
            return jsonify({'classes': [], 'error': '未知校区'})
        rows = db.execute(
            f'SELECT DISTINCT class_name FROM {stable} WHERE school_name = ? AND grade_name = ? ORDER BY class_name',
            (school_name, grade)
        ).fetchall()
    classes = [r['class_name'] for r in rows]
    return jsonify({'classes': classes})

@app.route('/api/campus-grades', methods=['GET'])
def campus_grades():
    """按校区返回不重复的年级列表（上传区下拉用）"""
    campus_id = request.args.get('campus', '').strip()
    db = get_db()
    stable = _students_table(campus_id)
    if campus_id == 'luojing':
        rows = db.execute(
            f'SELECT DISTINCT grade_name FROM {stable} ORDER BY {_grade_sort_sql("grade_name")}'
        ).fetchall()
    else:
        dt_cfg = _get_campus_dt(campus_id)
        school_name = dt_cfg.get('school_name', '')
        if not school_name:
            return jsonify({'grades': [], 'error': '未知校区'})
        rows = db.execute(
            f'SELECT DISTINCT grade_name FROM {stable} WHERE school_name = ? ORDER BY {_grade_sort_sql("grade_name")}',
            (school_name,)
        ).fetchall()
    grades = [r['grade_name'] for r in rows]
    return jsonify({'grades': grades})

@app.route('/api/auth/bind-child', methods=['POST'])
def auth_bind_child():
    """家长自助绑定：钉钉登录后选择自己的孩子。
    请求: { campus, idCard, grade, class, studentName }
    通过 session token 识别当前钉钉用户，更新其 bound_id_card。"""
    u = _current_user()
    if u['role'] not in ('parent', 'teacher', 'admin'):
        return jsonify({'error': '请先通过钉钉登录'}), 401
    data = request.get_json() or {}
    id_card = (data.get('idCard') or '').strip()
    student_name = (data.get('studentName') or '').strip()
    grade = (data.get('grade') or '').strip()
    klass = (data.get('class') or '').strip()
    campus_id = (data.get('campus') or '').strip()
    
    if not id_card and not student_name:
        return jsonify({'error': '请选择学生'}), 400
    
    # 验证学生存在（校区隔离）
    db = get_db()
    student = None
    stable = _students_table(campus_id)
    if id_card:
        student = db.execute(f'SELECT * FROM {stable} WHERE id_card = ?', (id_card,)).fetchone()
    if not student and student_name and grade:
        q = f'SELECT * FROM {stable} WHERE name = ?'
        args = [student_name]
        if grade:
            q += ' AND grade_name = ?'; args.append(grade)
        if klass:
            q += ' AND class_name = ?'; args.append(klass)
        student = db.execute(q + ' LIMIT 1', args).fetchone()
    
    if not student:
        return jsonify({'error': '未找到该学生，请检查信息'}), 404
    student_userid = student['dingtalk_userid'] if 'dingtalk_userid' in student.keys() else None
    
    # 更新 user_bindings
    auth = request.headers.get('Authorization', '')
    union_id = None
    if auth.startswith('Bearer '):
        info = _verify_session(auth[7:])
        if info:
            union_id = info.get('unionId')
    
    if not union_id:
        return jsonify({'error': '无法获取钉钉身份'}), 401
    
    _ensure_user_bindings_table()
    # 使用 parent_kids 表（支持多娃）
    _ensure_parent_kids_table()
    
    # 唯一绑定约束：一个学生只能被一个家长绑定
    other_binding = db.execute('SELECT id, union_id FROM parent_kids WHERE kid_id_card = ? AND union_id != ?', (student['id_card'], union_id)).fetchone()
    if other_binding:
        return jsonify({'error': '该学生已被其他家长绑定，无法重复绑定'}), 409
    
    # 检查是否已绑定同一学生
    existing = db.execute('SELECT id FROM parent_kids WHERE union_id = ? AND kid_id_card = ?', (union_id, student['id_card'])).fetchone()
    if existing:
        db.execute('UPDATE parent_kids SET is_active = 0 WHERE union_id = ?', (union_id,))
        db.execute('UPDATE parent_kids SET is_active = 1 WHERE id = ?', (existing['id'],))
    else:
        db.execute('UPDATE parent_kids SET is_active = 0 WHERE union_id = ?', (union_id,))
        db.execute('''INSERT INTO parent_kids(
                          union_id, kid_dingtalk_userid, kid_id_card, kid_name,
                          kid_grade, kid_class, campus, is_active
                      ) VALUES(?,?,?,?,?,?,?,1)''',
            (
                union_id, student_userid, student['id_card'],
                student['name'], student['grade_name'], student['class_name'], campus_id,
            ))
    db.execute(
        '''UPDATE user_bindings
           SET bound_student_userid=?, bound_id_card=?, bound_name=?,
               bound_grade=?, bound_class=? WHERE dingtalk_unionid=?''',
        (
            student_userid, student['id_card'], student['name'],
            student['grade_name'], student['class_name'], union_id,
        ),
    )
    db.commit()
    
    all_kids = db.execute('SELECT kid_dingtalk_userid, kid_id_card, kid_name, kid_grade, kid_class, campus, is_active FROM parent_kids WHERE union_id = ? ORDER BY bound_at', (union_id,)).fetchall()
    kids_list = [_parent_kid_payload(db, kid) for kid in all_kids]
    
    app.logger.info(f'[家长绑定] {union_id} → {student["name"]} ({student["grade_name"]}{student["class_name"]}) | 共 {len(all_kids)} 个孩子')
    return jsonify({
        'success': True,
        'message': f'已绑定学生: {student["name"]}' + (f'（共 {len(all_kids)} 个孩子）' if len(all_kids) > 1 else ''),
        'student': {
            'studentUserId': student_userid,
            'idCard': student['id_card'],
            'name': student['name'],
            'grade': student['grade_name'],
            'class': student['class_name'],
        },
        'kids': kids_list,
    })

@app.route('/api/auth/binding-status', methods=['GET'])
def auth_binding_status():
    """查询当前用户的绑定状态（家长有没有绑定孩子）"""
    u = _current_user()
    # 无真实认证（非 demo、非 Bearer token）→ 返回未认证，前端进登录界面
    auth_ok = u.get('identity', '').startswith(('demo:', 'dt:', 'manual:'))
    resp = {
        'authenticated': auth_ok,
        'role': u['role'] if auth_ok else None,
        'boundStudentUserId': u.get('bound_student_userid') if auth_ok else None,
        'boundIdCard': u.get('bound_id_card') if auth_ok else None,
        'boundGrade': u.get('bound_grade') if auth_ok else None,
        'boundClass': u.get('bound_class') if auth_ok else None,
        'isBound': bool(u.get('bound_id_card')) if auth_ok else False,
    }
    # 双角色信息：教师-家长切换
    av = session.get('available_roles')
    if av:
        resp['availableRoles'] = av
        resp['parentBound'] = True
        # 孩子在 parent 模式下才返回 kids 列表
        if u['role'] == 'parent':
            uid = u['identity'][3:]
            db = get_db()
            kids = db.execute('SELECT kid_dingtalk_userid, kid_id_card, kid_name, kid_grade, kid_class, campus, is_active FROM parent_kids WHERE union_id = ? ORDER BY bound_at', (uid,)).fetchall()
            if kids:
                resp['kids'] = [_parent_kid_payload(db, kid) for kid in kids]
    return jsonify(resp), (200 if auth_ok else 401)

@app.route('/api/auth/switch-kid', methods=['POST'])
def auth_switch_kid():
    """切换当前活跃的孩子（多娃家庭）"""
    u = _current_user()
    if u['role'] != 'parent':
        return jsonify({'error': '仅家长身份可以切换孩子'}), 403
    auth = request.headers.get('Authorization', '')
    union_id = None
    if auth.startswith('Bearer '):
        info = _verify_session(auth[7:])
        if info:
            union_id = info.get('unionId')
    if not union_id:
        return jsonify({'error': '无法获取钉钉身份'}), 401
    data = request.get_json() or {}
    student_userid = (data.get('studentUserId') or '').strip()
    kid_id_card = (data.get('idCard') or '').strip()
    if not student_userid and not kid_id_card:
        return jsonify({'error': '请提供孩子的学生 UserId'}), 400
    db = get_db()
    # 优先使用学生 UserId 验证绑定关系；idCard 仅兼容尚未迁移的旧绑定。
    if student_userid:
        kb = db.execute(
            'SELECT id FROM parent_kids WHERE union_id = ? AND kid_dingtalk_userid = ?',
            (union_id, student_userid),
        ).fetchone()
    else:
        kb = db.execute(
            'SELECT id FROM parent_kids WHERE union_id = ? AND kid_id_card = ?',
            (union_id, kid_id_card),
        ).fetchone()
    if not kb:
        return jsonify({'error': '未找到该孩子的绑定记录'}), 404
    # 切换激活
    db.execute('UPDATE parent_kids SET is_active = 0 WHERE union_id = ?', (union_id,))
    db.execute('UPDATE parent_kids SET is_active = 1 WHERE id = ?', (kb['id'],))
    kid = db.execute(
        'SELECT kid_dingtalk_userid, kid_id_card, kid_name, kid_grade, kid_class, campus, is_active FROM parent_kids WHERE id = ?',
        (kb['id'],),
    ).fetchone()
    current = _authoritative_parent_kid(db, kid)
    # 同步旧的单孩快捷字段，避免它在下次鉴权时覆盖 parent_kids.is_active。
    db.execute(
        '''UPDATE user_bindings
           SET bound_student_userid=?, bound_id_card=?, bound_name=?,
               bound_grade=?, bound_class=? WHERE dingtalk_unionid=?''',
        (
            current.get('kid_dingtalk_userid'), current['kid_id_card'],
            current['kid_name'], current['kid_grade'], current['kid_class'],
            union_id,
        ),
    )
    db.commit()
    return jsonify({
        'success': True,
        'kid': _parent_kid_payload(db, current),
    })

@app.route('/api/auth/unbind-child', methods=['POST'])
def auth_unbind_child():
    """家长解绑孩子：删除 parent_kids 记录。
    请求: { idCard: 'BS_00923' }"""
    u = _current_user()
    if u['role'] not in ('parent', 'teacher', 'admin'):
        return jsonify({'error': '无权限'}), 403
    auth = request.headers.get('Authorization', '')
    union_id = None
    if auth.startswith('Bearer '):
        info = _verify_session(auth[7:])
        if info:
            union_id = info.get('unionId')
    if not union_id:
        return jsonify({'error': '无法获取钉钉身份'}), 401
    data = request.get_json() or {}
    kid_id_card = (data.get('idCard') or '').strip()
    if not kid_id_card:
        return jsonify({'error': '请提供孩子学籍号'}), 400
    db = get_db()
    kb = db.execute('SELECT id, kid_name FROM parent_kids WHERE union_id = ? AND kid_id_card = ?', (union_id, kid_id_card)).fetchone()
    if not kb:
        return jsonify({'error': '未找到该孩子的绑定记录'}), 404
    kid_name = kb['kid_name']
    db.execute('DELETE FROM parent_kids WHERE id = ?', (kb['id'],))
    db.commit()
    app.logger.info(f'[解绑] {union_id} 解绑了 {kid_name} ({kid_id_card})')
    # 返回剩余孩子
    remaining = db.execute('SELECT kid_dingtalk_userid, kid_id_card, kid_name, kid_grade, kid_class, campus, is_active FROM parent_kids WHERE union_id = ? ORDER BY bound_at', (union_id,)).fetchall()
    return jsonify({
        'success': True,
        'message': f'已解绑: {kid_name}',
        'kids': [_parent_kid_payload(db, kid) for kid in remaining],
    })


@app.route('/api/auth/manual-login', methods=['POST'])
def auth_manual_login():
    """SSO 失败兜底：手动输入身份信息登录
    请求: { role: 'teacher'|'parent', name, campus }
    教师: 验证 teacher_roster 表 → 生成 session
    家长: 不在此验证，前端直接进绑定面板"""
    data = request.get_json() or {}
    role = (data.get('role') or '').strip()
    name = (data.get('name') or '').strip()
    campus_id = (data.get('campus') or '').strip()
    
    if role not in ('teacher', 'parent'):
        return jsonify({'error': '请选择教师或家长身份'}), 400
    if not name:
        return jsonify({'error': '请输入姓名'}), 400
    if not campus_id:
        campus_id = 'benbu'
    
    db = get_db()
    
    if role == 'teacher':
        # 查 teacher_roster 验证（校区隔离）
        troster = _teacher_roster_table(campus_id)
        if campus_id == 'luojing':
            row = db.execute(
                f'SELECT * FROM {troster} WHERE name = ? ORDER BY is_admin DESC LIMIT 1',
                (name,)
            ).fetchone()
        else:
            row = db.execute(
                f'SELECT * FROM {troster} WHERE name = ? AND campus = ? ORDER BY is_admin DESC LIMIT 1',
                (name, campus_id)
            ).fetchone()
        if not row:
            return jsonify({'error': f'未找到教师"{name}"，请确认姓名和校区是否正确'}), 404
        manual_id = f'manual:teacher:{row["id"]}'
        nick = row['name']
        is_admin = bool(row['is_admin'])
        actual_role = 'admin' if is_admin else 'teacher'
        
        # 确保 user_bindings 有这条（角色修正）
        _ensure_user_bindings_table()
        existing = db.execute('SELECT role FROM user_bindings WHERE dingtalk_unionid = ?', (manual_id,)).fetchone()
        if existing:
            db.execute('UPDATE user_bindings SET role=? WHERE dingtalk_unionid=?', (actual_role, manual_id))
        else:
            db.execute('INSERT INTO user_bindings(dingtalk_unionid, role, bound_name) VALUES(?,?,?)',
                       (manual_id, actual_role, nick))
        db.commit()
        
        sess_token = _sign_session({'unionId': manual_id, 'nick': nick, 'campus': campus_id, 'ts': int(time.time())})
        app.logger.info(f'[手动登录-教师] {name} campus={campus_id} role={actual_role}')
        return jsonify({
            'sessionToken': sess_token,
            'user': {'unionId': manual_id, 'nick': nick, 'role': actual_role},
            'manualLogin': True
        })
    
    if role == 'parent':
        # 家长：不在此验证，前端进绑定面板 → 绑定 child 后才建 session
        manual_id = f'manual:parent:{name}:{campus_id}'
        sess_token = _sign_session({'unionId': manual_id, 'nick': name, 'campus': campus_id, 'ts': int(time.time())})
        
        _ensure_user_bindings_table()
        db.execute('INSERT OR IGNORE INTO user_bindings(dingtalk_unionid, role, bound_name) VALUES(?,?,?)',
                   (manual_id, 'parent', name))
        db.commit()
        
        app.logger.info(f'[手动登录-家长] {name} campus={campus_id}')
        return jsonify({
            'sessionToken': sess_token,
            'user': {'unionId': manual_id, 'nick': name, 'role': 'parent'},
            'manualLogin': True
        })

# ==================== AI 奖状识别上传 ====================

import base64 as _base64_mod
import tempfile as _tempfile

_CERT_UPLOAD_DIR = os.path.join(BASE_DIR, 'assets', 'award-certs')
os.makedirs(_CERT_UPLOAD_DIR, exist_ok=True)

def _ai_vision_extract(image_base64, prompt):
    """调用百度千帆视觉模型，从奖状图片中提取结构化信息"""
    if not VISION_AI_API_KEY:
        raise RuntimeError('奖状图片识别需要单独配置 BAIDU_AI_KEY')
    body = json.dumps({
        'model': VISION_AI_MODEL,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': prompt},
                {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{image_base64}'}}
            ]
        }],
        'temperature': 0.1,
        'max_completion_tokens': 2048,
    }).encode('utf-8')
    req = Request(VISION_AI_URL, data=body, method='POST', headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {VISION_AI_API_KEY}',
    })
    try:
        for attempt in range(3):
            try:
                with urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                break
            except (ssl.SSLError, OSError, urllib_error.URLError) as net_err:
                if attempt < 2:
                    wait = (attempt + 1) * 3
                    app.logger.warning(f'[AI识别] 网络/SSL重试 {attempt+1}/3: {net_err}')
                    time.sleep(wait)
                else:
                    raise
    except urllib_error.HTTPError as e:
        err_body = e.read().decode('utf-8')[:500]
        app.logger.error(f'[AI识别] API HTTP {e.code}: {err_body}')
        raise
    msg = (data.get('choices') or [{}])[0].get('message') or {}
    content = (msg.get('content') or '').strip()
    if not content:
        content = (msg.get('reasoning_content') or '').strip()
    return content

# ── 钉钉工作通知 ──

_DT_NOTIFY_ACCESS_TOKEN_CACHE = {}  # campus_id → {token, expires_at}

def _dt_get_access_token(campus_id):
    """获取或刷新钉钉企业 access_token（带缓存）。"""
    now = time.time()
    entry = _DT_NOTIFY_ACCESS_TOKEN_CACHE.get(campus_id)
    if entry and entry['expires_at'] > now + 60:
        return entry['token']
    dt_cfg = _get_campus_dt(campus_id)
    app_key = dt_cfg['appKey']
    app_secret = dt_cfg['appSecret']
    if not (app_key and app_secret):
        return None
    try:
        body = json.dumps({'appKey': app_key, 'appSecret': app_secret}).encode('utf-8')
        req = urllib_request.Request(
            'https://api.dingtalk.com/v1.0/oauth2/accessToken',
            data=body,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        resp = urllib_request.urlopen(req, timeout=8)
        data = json.loads(resp.read().decode('utf-8'))
        token = data.get('accessToken')
        expires = data.get('expireIn', 7200)  # 默认 2h
        if token:
            _DT_NOTIFY_ACCESS_TOKEN_CACHE[campus_id] = {'token': token, 'expires_at': now + expires}
            app.logger.info(f'[通知] 获取 {campus_id} access_token 成功, 有效期 {expires}s')
            return token
    except Exception as e:
        app.logger.error(f'[通知] 获取 {campus_id} access_token 失败: {e}')
    return None

def _dt_get_userid_by_unionid(union_id, campus_id):
    """通过 union_id 获取钉钉 user_id（企业内）。"""
    token = _dt_get_access_token(campus_id)
    if not token or not union_id:
        return None
    try:
        body = json.dumps({'unionid': union_id}).encode('utf-8')
        req = urllib_request.Request(
            f'https://oapi.dingtalk.com/topapi/user/getbyunionid?access_token={token}',
            data=body,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        resp = urllib_request.urlopen(req, timeout=8)
        data = json.loads(resp.read().decode('utf-8'))
        errcode = data.get('errcode', -1)
        if errcode == 0:
            userid = data.get('result', {}).get('userid')
            if userid:
                return userid
        else:
            app.logger.warning(f'[通知] getbyunionid 失败: {data.get("errmsg", "?")} union_id={union_id[:20]}')
    except Exception as e:
        app.logger.error(f'[通知] getbyunionid 异常: {e}')
    return None

def _send_dt_work_notification(user_id, title, content, campus_id):
    """发送钉钉工作通知。返回 True/False。"""
    dt_cfg = _get_campus_dt(campus_id)
    agent_id = (dt_cfg.get('agentId') or '').strip()
    if not agent_id:
        app.logger.warning(f'[通知] campus={campus_id} 未配置 agentId，无法发通知')
        return False
    token = _dt_get_access_token(campus_id)
    if not token:
        return False
    try:
        msg = {
            'agent_id': int(agent_id) if agent_id.isdigit() else agent_id,
            'userid_list': user_id,
            'msg': {
                'msgtype': 'markdown',
                'markdown': {
                    'title': title,
                    'text': content
                }
            }
        }
        body = json.dumps(msg, ensure_ascii=False).encode('utf-8')
        req = urllib_request.Request(
            'https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2',
            data=body,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        # 需要带 access_token 查询参数
        req = urllib_request.Request(
            f'https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2?access_token={token}',
            data=body,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        resp = urllib_request.urlopen(req, timeout=8)
        result = json.loads(resp.read().decode('utf-8'))
        errcode = result.get('errcode', -1)
        if errcode == 0:
            task_id = result.get('task_id', '?')
            app.logger.info(f'[通知] 发送成功: user={user_id} task_id={task_id}')
            return True
        else:
            app.logger.error(f'[通知] 发送失败: {result.get("errmsg", "?")} errcode={errcode}')
    except Exception as e:
        app.logger.error(f'[通知] 工作通知异常: {e}')
    return False

def _try_notify_parent(student_id_card, student_name, competition, prize, campus_id):
    """奖状入库后，尝试通知家长（静默失败，不影响主流程）。"""
    if not student_id_card or not campus_id:
        return
    try:
        db = get_db()
        # 1) 查 parent_kids 获取家长 union_id
        pk = db.execute(
            'SELECT union_id, kid_name FROM parent_kids WHERE kid_id_card = ? AND campus = ? AND is_active = 1 LIMIT 1',
            (student_id_card, campus_id)
        ).fetchone()
        if not pk:
            return  # 无人绑定，跳过
        parent_uid = pk['union_id']
        
        # 2) 查 user_bindings 获取家长 user_id
        ub = db.execute(
            'SELECT dingtalk_userid, bound_name FROM user_bindings WHERE dingtalk_unionid = ?',
            (parent_uid,)
        ).fetchone()
        if not ub:
            return
        
        dt_userid = ub['dingtalk_userid']
        if not dt_userid:
            # 没有 user_id，尝试通过 union_id 转换
            dt_userid = _dt_get_userid_by_unionid(parent_uid, campus_id)
            if dt_userid:
                # 回填到 user_bindings
                db.execute('UPDATE user_bindings SET dingtalk_userid=? WHERE dingtalk_unionid=?',
                           (dt_userid, parent_uid))
                db.commit()
            else:
                return  # 转换失败，放弃通知
        
        # 3) 发送工作通知
        title = '📜 孩子有新的奖状'
        prize_text = f' - {prize}' if prize else ''
        campus_name = _get_campus_dt(campus_id).get('name', campus_id)
        text = f'## {title}\n\n'
        text += f'**{student_name}** 在 **{competition}**{prize_text}\n\n'
        text += f'校区: {campus_name}\n\n'
        text += f'请在钉钉工作台进入「成就岛」查看详情。'
        
        _send_dt_work_notification(dt_userid, title, text, campus_id)
    except Exception as e:
        app.logger.warning(f'[通知] 家长通知异常: {e}')

def _recognize_and_save_certs(img_bytes, campus_id, source_filename='', filter_grade='', filter_class=''):
    """对单张奖状图片执行 AI 识别 + 学生匹配 + 入库，返回结果 dict。"""
    img_b64 = _base64_mod.b64encode(img_bytes).decode('utf-8')
    ext = os.path.splitext(source_filename)[1].lower() or '.jpg'
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        ext = '.jpg'
    safe_name = f"upload_{int(time.time())}_{secrets.token_hex(4)}{ext}"
    img_path = os.path.join(_CERT_UPLOAD_DIR, safe_name)
    with open(img_path, 'wb') as f:
        f.write(img_bytes)
    app.logger.info(f'[奖状上传] 保存图片: {safe_name} ({len(img_bytes)} bytes)')
    
    prompt = """你是一名学校教务助理。请仔细查看这张奖状页面图片，识别其中每一份奖状/证书的信息。

对于每一份奖状，请提取以下字段并以 JSON 数组格式返回：
- student_name: 获奖学生姓名（仅姓名，不含"同学"等称呼）
- competition: 比赛/活动/项目名称
- prize: 奖项等级（如"一等奖"、"金奖"等）
- class_name: 班级（如"三(1)班"、"五(3)班"等，如果能看到的话）
- teacher: 指导老师（如果有的话）
- subject: 学科分类（体育/学科/艺术/科技，根据比赛内容判断）

注意：
1. 必须返回纯 JSON 数组格式，不要有任何额外文字说明
2. 如果图片中有多张证书，每张都要单独识别
3. 如果某个字段无法识别，用空字符串 "" 代替
4. 学生姓名必须从奖状内容中准确读取，不要编造

返回格式示例：
[{"student_name":"张三","competition":"校园文化节美术比赛","prize":"一等奖","class_name":"三(2)班","teacher":"李老师","subject":"艺术"}]"""
    
    try:
        ai_result = _ai_vision_extract(img_b64, prompt)
        app.logger.info(f'[AI识别] 原始输出(前500字): {ai_result[:500]}')
    except Exception as e:
        app.logger.error(f'[AI识别] 调用失败: {e}')
        try: os.remove(img_path)
        except: pass
        return {'error': f'AI 识别失败: {str(e)[:200]}', 'image_path': f'assets/award-certs/{safe_name}'}
    
    try:
        # 清洗 AI 输出：去尾逗号、去 markdown 代码块
        ai_clean = ai_result.strip()
        ai_clean = re.sub(r',\s*([}\]])', r'\1', ai_clean)  # 去 trailing comma
        json_match = re.search(r'\[[\s\S]*\]', ai_clean)
        if json_match:
            awards_raw = json.loads(json_match.group())
        else:
            awards_raw = json.loads(ai_clean)
        if not isinstance(awards_raw, list):
            awards_raw = [awards_raw]
    except Exception as e:
        app.logger.error(f'[AI识别] JSON解析失败: {e}, 原始文本: {ai_result[:300]}')
        return {
            'error': f'AI 返回格式不符合预期: {str(e)[:100]}',
            'raw_output': ai_result[:500],
            'image_path': f'assets/award-certs/{safe_name}',
        }
    
    db = get_db()
    _ensure_award_certs_table()
    dt_cfg = _get_campus_dt(campus_id)
    school_name = dt_cfg.get('school_name', '')
    saved = []
    unmatched = []
    dup_count = 0
    
    # 防御：异常场景下 awards_raw 可能为 None（如 AI 返回 null）
    if awards_raw is None:
        awards_raw = []
    for award in awards_raw:
        student_name = (award.get('student_name') or '').strip()
        competition = (award.get('competition') or '').strip()
        prize = (award.get('prize') or '').strip()
        klass = (award.get('class_name') or '').strip()
        teacher = (award.get('teacher') or '').strip()
        subject = (award.get('subject') or '学科').strip()
        
        if not student_name or not competition:
            continue
        
        matched_student = None
        stable = _students_table(campus_id)
        query = f'SELECT * FROM {stable} WHERE name = ?'
        args = [student_name]
        # 罗泾独立表无 school_name 列，跳过此过滤
        if school_name and stable == 'students':
            query += ' AND school_name = ?'; args.append(school_name)
        # 上传区筛选：年级/班级
        if filter_grade:
            query += ' AND grade_name = ?'; args.append(filter_grade)
        if filter_class:
            class_clean = filter_class.replace('(', '').replace(')', '').replace('班', '').strip()
            query += ' AND REPLACE(REPLACE(REPLACE(class_name,"(",""),")",""),"班","") = ?'
            args.append(class_clean)
        if klass and not filter_class:
            # AI 识别出的班级名，只在未手动筛选时使用
            class_clean = klass.replace('(', '').replace(')', '').replace('班', '').strip()
            query += ' AND REPLACE(REPLACE(REPLACE(class_name,"(",""),")",""),"班","") = ?'
            args.append(class_clean)
        
        row = db.execute(query + ' LIMIT 1', args).fetchone()
        if not row and school_name and stable == 'students':
            fq = f'SELECT * FROM {stable} WHERE name = ? AND school_name = ?'
            fa = [student_name, school_name]
            if filter_grade:
                fq += ' AND grade_name = ?'; fa.append(filter_grade)
            if filter_class:
                fc = filter_class.replace('(', '').replace(')', '').replace('班', '').strip()
                fq += ' AND REPLACE(REPLACE(REPLACE(class_name,"(",""),")",""),"班","") = ?'
                fa.append(fc)
            row = db.execute(fq + ' LIMIT 1', fa).fetchone()
        
        if row:
            matched_student = dict(row)
            grade = row['grade_name']
            class_name = row['class_name']
            id_card = row['id_card']
        else:
            grade = ''
            class_name = klass
            id_card = ''
        
        try:
            wuyu = _classify_wuyu(competition, prize, subject)
            # 重复检测：同学生+同比赛+同奖项+同年级+同班级 → 跳过
            dup = db.execute(
                'SELECT id FROM award_certs WHERE student_name=? AND competition=? AND prize=? AND grade=? AND class_name=?',
                (student_name, competition, prize, grade, class_name)
            ).fetchone()
            if dup:
                dup_count += 1
                app.logger.info(f'[AI识别] 重复跳过: {student_name} - {competition} ({prize})')
                saved.append({
                    'student_name': student_name,
                    'competition': competition,
                    'prize': prize,
                    'class_name': class_name,
                    'grade': grade,
                    'teacher': teacher,
                    'subject': subject,
                    'matched': bool(row),
                    'id_card': id_card,
                    'duplicated': True,
                })
                continue
            db.execute('''INSERT INTO award_certs
                (student_name, student_id_card, grade, class_name, campus, wuyu, competition, prize, subject, teacher, image_path, source)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (student_name, id_card, grade, class_name, campus_id, wuyu, competition, prize, subject, teacher,
                 f'assets/award-certs/{safe_name}', 'ai-upload'))
            db.commit()
            # 通知绑定该学生的家长
            try:
                _try_notify_parent(id_card, student_name, competition, prize, campus_id)
            except Exception:
                pass  # 通知失败不影响上传
            saved.append({
                'student_name': student_name,
                'competition': competition,
                'prize': prize,
                'class_name': class_name,
                'grade': grade,
                'teacher': teacher,
                'subject': subject,
                'matched': bool(row),
                'id_card': id_card,
            })
        except Exception as e:
            app.logger.warning(f'[AI识别] 保存失败: {student_name} - {e}')
            unmatched.append({'student_name': student_name, 'competition': competition, 'reason': str(e)[:100]})
    
    return {
        'total_found': len(awards_raw),
        'saved': len(saved),
        'duplicated': dup_count,
        'unmatched': len(unmatched),
        'awards': saved,
        'unmatched_details': unmatched,
        'image_path': f'assets/award-certs/{safe_name}',
    }


@app.route('/api/award-certs/upload-ai', methods=['POST'])
def upload_award_certs_ai():
    """教师上传奖状图片或 ZIP 压缩包，AI 识别并自动分发到对应学生。
    请求: multipart/form-data
      - image: 奖状图片（jpg/png/webp）或 ZIP 压缩包
      - campus: 校区标识
    返回: 识别到的奖状列表，每条包含 student_name / competition / prize / matched 等"""
    u = _current_user()
    if u['role'] not in ('teacher', 'admin'):
        return jsonify({'error': '仅教师和管理员可上传'}), 403
    
    if 'image' not in request.files:
        return jsonify({'error': '请上传奖状图片或 ZIP 压缩包'}), 400
    
    campus_id = (request.form.get('campus') or '').strip()
    filter_grade = (request.form.get('grade') or '').strip()
    filter_class = (request.form.get('class') or '').strip()
    
    # ── 多文件上传分支 ──
    files_list = request.files.getlist('image')
    if len(files_list) > 1:
        all_saved = []
        all_unmatched = []
        errors = []
        total_found = 0
        processed = 0
        fail_count = 0
        single_max_mb = 20
        for f in files_list:
            if not f.filename:
                continue
            inner_bytes = f.read()
            fsize_mb = len(inner_bytes) / (1024*1024)
            if fsize_mb > single_max_mb:
                errors.append(f'{f.filename}: 单张超过 {single_max_mb}MB，已跳过 ({fsize_mb:.1f}MB)')
                continue
            fext = os.path.splitext(f.filename)[1].lower()
            if fext == '.zip':
                errors.append(f'{f.filename}: 多文件模式下不支持 ZIP，请单独上传 ZIP')
                continue
            try:
                app.logger.info(f'[批量上传] 处理: {f.filename} ({len(inner_bytes)} bytes)')
                result = _recognize_and_save_certs(inner_bytes, campus_id, f.filename, filter_grade, filter_class)
                if result.get('error'):
                    fail_count += 1
                    errors.append(f'{f.filename}: {result["error"][:100]}')
                else:
                    processed += 1
                    total_found += result.get('total_found', 0)
                    all_saved.extend(result.get('awards', []))
                    unmatched = result.get('unmatched_details') or []
                    all_unmatched.extend(unmatched)
            except Exception as e:
                fail_count += 1
                errors.append(f'{f.filename}: 处理异常 - {str(e)[:100]}')
        return jsonify({
            'success': True,
            'source': 'multi',
            'files_total': len(files_list),
            'files_processed': processed,
            'files_failed': fail_count,
            'errors': errors if errors else None,
            'total_found': total_found,
            'saved': len(all_saved),
            'unmatched': len(all_unmatched),
            'awards': all_saved,
            'unmatched_details': all_unmatched if all_unmatched else None,
        })
    
    file = files_list[0]
    if not file.filename:
        return jsonify({'error': '文件名为空'}), 400
    
    ext_lower = os.path.splitext(file.filename)[1].lower()
    
    # ── ZIP 分支：先存盘再读（避免大 ZIP 撑爆内存）──
    if ext_lower == '.zip':
        zip_tmp_path = None
        try:
            import tempfile as _tmp
            # 流式写入临时文件
            with _tmp.NamedTemporaryFile(suffix='.zip', delete=False) as _tf:
                file.save(_tf.name)
                zip_tmp_path = _tf.name
            fsize_mb = os.path.getsize(zip_tmp_path) / (1024*1024)
            app.logger.info(f'[ZIP上传] 临时文件: {zip_tmp_path} ({fsize_mb:.1f}MB)')
            
            with zipfile.ZipFile(zip_tmp_path) as z:
                names = [n for n in z.namelist()
                         if not n.startswith('__MACOSX') and not n.startswith('.') and not n.endswith('/')]
                img_names = [n for n in names
                             if os.path.splitext(n)[1].lower() in ('.jpg', '.jpeg', '.png', '.webp')]
                if not img_names:
                    return jsonify({'error': 'ZIP 包内未找到图片文件（支持 jpg/png/webp）'}), 400
                
                all_saved = []
                all_unmatched = []
                errors = []
                total_found = 0
                processed = 0
                fail_count = 0
                
                for fname in img_names:
                    try:
                        inner_bytes = z.read(fname)
                        if len(inner_bytes) > 20 * 1024 * 1024:
                            errors.append(f'{fname}: 单张超过 20MB，已跳过')
                            continue
                        app.logger.info(f'[ZIP上传] 处理: {fname} ({len(inner_bytes)} bytes)')
                        result = _recognize_and_save_certs(inner_bytes, campus_id, fname, filter_grade, filter_class)
                        if result.get('error'):
                            fail_count += 1
                            errors.append(f'{fname}: {result["error"][:100]}')
                        else:
                            processed += 1
                            total_found += result.get('total_found', 0)
                            all_saved.extend(result.get('awards', []))
                            unmatched = result.get('unmatched_details') or []
                            all_unmatched.extend(unmatched)
                    except Exception as e:
                        fail_count += 1
                        errors.append(f'{fname}: 处理异常 - {str(e)[:100]}')
                
                return jsonify({
                    'success': True,
                    'source': 'zip',
                    'zip_files_total': len(img_names),
                    'zip_processed': processed,
                    'zip_failed': fail_count,
                    'zip_errors': errors if errors else None,
                    'total_found': total_found,
                    'saved': len(all_saved),
                    'unmatched': len(all_unmatched),
                    'awards': all_saved,
                    'unmatched_details': all_unmatched if all_unmatched else None,
                })
        except zipfile.BadZipFile:
            return jsonify({'error': '文件不是有效的 ZIP 压缩包'}), 400
        except Exception as e:
            app.logger.error(f'[ZIP上传] 解压失败: {e}')
            return jsonify({'error': f'ZIP 解压失败: {str(e)[:200]}'}), 500
        finally:
            # 清理磁盘临时 ZIP
            if zip_tmp_path and os.path.exists(zip_tmp_path):
                try: os.remove(zip_tmp_path)
                except: pass
    
    # ── 单图分支：大图也先存盘再读 ──
    img_tmp_path = None
    try:
        import tempfile as _tmp2
        with _tmp2.NamedTemporaryFile(suffix=ext_lower or '.jpg', delete=False) as _tf2:
            file.save(_tf2.name)
            img_tmp_path = _tf2.name
        with open(img_tmp_path, 'rb') as _f:
            file_bytes = _f.read()
    except Exception as e:
        app.logger.error(f'[奖状上传] 保存临时文件失败: {e}')
        return jsonify({'error': f'服务器处理异常: {str(e)[:200]}'}), 500
    finally:
        if img_tmp_path and os.path.exists(img_tmp_path):
            try: os.remove(img_tmp_path)
            except: pass
    
    try:
        result = _recognize_and_save_certs(file_bytes, campus_id, file.filename, filter_grade, filter_class)
    except Exception as e:
        app.logger.error(f'[奖状上传] 异常: {e}', exc_info=True)
        return jsonify({'error': f'服务器处理异常: {str(e)[:200]}'}), 500
    if result.get('error'):
        code = 502 if 'AI' in result.get('error', '') else 400
        return jsonify(result), code
    return jsonify(dict(success=True, **result))

@app.route('/api/teacher/awards-summary', methods=['GET'])
def teacher_awards_summary():
    """教师端：查看本校区奖状分发概览（按班级统计）"""
    u = _current_user()
    if u['role'] not in ('teacher', 'admin'):
        return jsonify({'error': '仅教师可查看'}), 403
    campus_id = request.args.get('campus', '').strip()
    dt_cfg = _get_campus_dt(campus_id)
    school_name = dt_cfg.get('school_name', '')
    
    db = get_db()
    _ensure_award_certs_table()
    
    # 按班级统计奖状数
    if school_name:
        stable = _students_table(campus_id)
        # 罗泾独立表无 school_name 列，直接 JOIN
        if campus_id == 'luojing':
            rows = db.execute(f'''
                SELECT ac.grade, ac.class_name, COUNT(*) as cnt, COUNT(DISTINCT ac.student_name) as students
                FROM award_certs ac
                INNER JOIN {stable} s ON (ac.student_id_card = s.id_card OR ac.student_name = s.name)
                GROUP BY ac.grade, ac.class_name
                ORDER BY ac.grade, ac.class_name
            ''').fetchall()
        else:
            rows = db.execute(f'''
                SELECT ac.grade, ac.class_name, COUNT(*) as cnt, COUNT(DISTINCT ac.student_name) as students
                FROM award_certs ac
                INNER JOIN {stable} s ON (ac.student_id_card = s.id_card OR ac.student_name = s.name)
                WHERE s.school_name = ?
                GROUP BY ac.grade, ac.class_name
                ORDER BY ac.grade, ac.class_name
            ''', (school_name,)).fetchall()
    else:
        rows = db.execute('''
            SELECT grade, class_name, COUNT(*) as cnt, COUNT(DISTINCT student_name) as students
            FROM award_certs
            GROUP BY grade, class_name
            ORDER BY grade, class_name
        ''').fetchall()
    
    total = sum(r['cnt'] for r in rows)
    return jsonify({
        'total_awards': total,
        'total_students': len(set(r['students'] for r in rows)),
        'by_class': [dict(r) for r in rows],
    })

# ─────────────────────────────────────────────
# ZIP 投放站 — 独立上传+处理通道，绕过 Gunicorn worker
# ─────────────────────────────────────────────
import subprocess as _sp, glob as _glob, threading as _thr

_ZIP_DROP_DIR = '/srv/baoshan/zip-drop'
_ZIP_UPLOAD_DIR = os.path.join(_ZIP_DROP_DIR, 'uploads')
_ZIP_JOBS_DIR = os.path.join(_ZIP_DROP_DIR, 'jobs')
_PROCESSOR_SCRIPT = os.path.join(_ZIP_DROP_DIR, 'process_zip.py')

os.makedirs(_ZIP_UPLOAD_DIR, exist_ok=True)
os.makedirs(_ZIP_JOBS_DIR, exist_ok=True)


@app.route('/zip-drop/')
@app.route('/zip-drop/index.html')
def zip_drop_page():
    """ZIP 投放站上传页面"""
    return app.send_static_file('zip-drop/index.html')


@app.route('/api/zip-drop/upload', methods=['POST'])
def zip_drop_upload():
    """接收 ZIP 上传，保存到投放目录，触发后台处理。"""
    if 'zip' not in request.files:
        return jsonify({'success': False, 'error': '请上传 ZIP 文件'}), 400
    
    file = request.files['zip']
    if not file.filename or not file.filename.lower().endswith('.zip'):
        return jsonify({'success': False, 'error': '仅支持 .zip 格式'}), 400
    
    campus = (request.form.get('campus') or '').strip()
    if campus not in ('benbu', 'baolin', 'luojing'):
        return jsonify({'success': False, 'error': '无效的校区'}), 400
    
    grade = (request.form.get('grade') or '').strip()
    class_name = (request.form.get('class') or '').strip()
    
    import hashlib as _hl
    job_id = _hl.md5(f'{file.filename}{time.time()}'.encode()).hexdigest()[:12]
    safe_filename = f'{job_id}_{file.filename}'
    zip_path = os.path.join(_ZIP_UPLOAD_DIR, safe_filename)
    
    try:
        file.save(zip_path)
        fsize_mb = os.path.getsize(zip_path) / (1024 * 1024)
        app.logger.info(f'[ZIP投放] {safe_filename} 保存成功 ({fsize_mb:.1f}MB) campus={campus}')
    except Exception as e:
        app.logger.error(f'[ZIP投放] 保存失败: {e}')
        return jsonify({'success': False, 'error': f'文件保存失败: {str(e)[:200]}'}), 500
    
    # 后台线程启动处理（不阻塞 web 请求）
    cmd = [
        '/srv/baoshan/宝山实验/venv/bin/python3', _PROCESSOR_SCRIPT, zip_path,
        '--campus', campus, '--job-id', job_id,
    ]
    if grade:
        cmd += ['--grade', grade]
    if class_name:
        cmd += ['--class', class_name]
    
    def _run_processor():
        try:
            _sp.run(cmd, capture_output=True, text=True, timeout=1800)
        except _sp.TimeoutExpired:
            app.logger.error(f'[ZIP投放] 处理超时: {job_id}')
            job_file = os.path.join(_ZIP_JOBS_DIR, f'{job_id}.json')
            if os.path.exists(job_file):
                import json as _j
                try:
                    with open(job_file) as f:
                        st = _j.load(f)
                    st['status'] = 'failed'
                    st['errors'].append('处理超时(30分钟)')
                    with open(job_file, 'w') as f:
                        _j.dump(st, f, ensure_ascii=False, indent=2)
                except:
                    pass
        except Exception as e:
            app.logger.error(f'[ZIP投放] 处理器异常: {e}')
    
    _thr.Thread(target=_run_processor, daemon=True).start()
    app.logger.info(f'[ZIP投放] 后台处理已启动: job_id={job_id}')
    
    return jsonify({
        'success': True,
        'job_id': job_id,
        'filename': file.filename,
        'size_mb': round(fsize_mb, 1),
        'campus': campus,
    })


@app.route('/api/zip-drop/status/<job_id>', methods=['GET'])
def zip_drop_status(job_id):
    """查询任务状态"""
    job_file = os.path.join(_ZIP_JOBS_DIR, f'{job_id}.json')
    if not os.path.exists(job_file):
        return jsonify({'status': 'not_found', 'error': '任务不存在'}), 404
    try:
        with open(job_file) as f:
            data = json.load(f)
        elapsed = ''
        if data.get('started_at') and data.get('completed_at'):
            elapsed = f"{data['completed_at'] - data['started_at']:.0f}s"
        elif data.get('started_at'):
            elapsed = f"{time.time() - data['started_at']:.0f}s (进行中)"
        return jsonify({
            'status': data.get('status', 'unknown'),
            'files_total': data.get('files_total', 0),
            'files_processed': data.get('files_processed', 0),
            'files_failed': data.get('files_failed', 0),
            'saved': data.get('saved', 0),
            'duplicated': data.get('duplicated', 0),
            'unmatched': data.get('unmatched', 0),
            'errors': (data.get('errors') or [])[:10],
            'elapsed': elapsed,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/zip-drop/jobs', methods=['GET'])
def zip_drop_jobs():
    """列出最近任务"""
    campus_names = {'benbu': '本部', 'baolin': '宝林', 'luojing': '罗泾'}
    jobs = []
    for jf in sorted(_glob.glob(os.path.join(_ZIP_JOBS_DIR, '*.json')),
                     key=os.path.getmtime, reverse=True)[:20]:
        try:
            with open(jf) as f:
                d = json.load(f)
            jobs.append({
                'job_id': d.get('job_id', os.path.basename(jf).replace('.json', '')),
                'campus_name': campus_names.get(d.get('campus', ''), d.get('campus', '')),
                'status': d.get('status', 'unknown'),
                'files_total': d.get('files_total', 0),
                'files_processed': d.get('files_processed', 0),
                'saved': d.get('saved', 0),
            })
        except:
            pass
    return jsonify({'jobs': jobs})


# ==================== 心情管理 API（Phase 2）====================

MOOD_VISIBILITY_MAP = {
    1: '学生本人', 2: '导师+班主任', 3: '心理教师', 4: '校方', 5: '家长'
}

def _check_mood_access(student_id, role, sub_role, bound_id_card=None, bound_grade=None, bound_class=None):
    """检查当前用户是否有权限查看某学生的情绪数据。返回 (allowed, max_severity_viewable)"""
    if role in ('admin',):
        return True, 5
    if role == 'teacher':
        # 教师只能看自己班级
        if sub_role == 'class' and bound_grade and bound_class:
            db = get_db()
            s = db.execute('SELECT grade_name, class_name FROM students WHERE id_card=?', (student_id,)).fetchone()
            if s and s['grade_name'] == bound_grade and s['class_name'] == bound_class:
                return True, 4
        # 总务老师可以看到全校，但 severity 受限
        if sub_role == 'general':
            return True, 3
    if role == 'parent' and bound_id_card == student_id:
        return True, 5  # 家长看自己孩子全部
    return False, 0

def _ensure_mood_tables():
    """确保心情管理相关表存在"""
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS mood_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL, student_name TEXT, grade TEXT, class_name TEXT,
        campus TEXT DEFAULT '',
        source TEXT NOT NULL, type TEXT NOT NULL,
        severity INTEGER NOT NULL CHECK(severity BETWEEN 1 AND 5),
        content TEXT NOT NULL, tags TEXT, recorded_by TEXT,
        visibility TEXT DEFAULT '1,2', status TEXT DEFAULT 'open',
        linked_event_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_mood_student ON mood_events(student_id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_mood_severity ON mood_events(severity, status)')
    db.execute('''CREATE TABLE IF NOT EXISTS mood_escalations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mood_event_id INTEGER NOT NULL, escalated_to TEXT,
        escalated_by TEXT, reason TEXT, action_taken TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS mood_authorizations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL UNIQUE,
        parent_consent INTEGER DEFAULT 0, student_consent INTEGER DEFAULT 0,
        authorized_at TEXT
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS mood_weekly_reports(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campus TEXT, grade TEXT, class_name TEXT,
        report_week TEXT NOT NULL, report_data TEXT,
        ai_generated INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    db.commit()

@app.route('/api/mood/event', methods=['POST'])
def mood_event():
    """学生自助上报情绪（知心姐姐）或教师观察录入"""
    data = request.get_json() or {}
    u = _current_user()
    _ensure_mood_tables()
    db = get_db()
    
    student_id = data.get('student_id', '').strip()
    source = data.get('source', 'zhixin_jiejie')
    severity = int(data.get('severity', 1))
    content = (data.get('content') or '').strip()
    tags = data.get('tags', '')
    
    if not student_id or not content:
        return jsonify({'error': 'student_id 和 content 必填'}), 400
    if severity < 1 or severity > 5:
        severity = max(1, min(5, severity))
    
    # 授权检查
    auth = db.execute('SELECT * FROM mood_authorizations WHERE student_id=?', (student_id,)).fetchone()
    if not auth or not (auth['parent_consent'] or auth['student_consent']):
        return jsonify({'error': '尚未获得情绪管理授权，请联系班主任或家长完成授权'}), 403
    
    # 获取学生信息
    student = db.execute('SELECT * FROM students WHERE id_card=?', (student_id,)).fetchone()
    if not student:
        student = db.execute('SELECT * FROM students_luojing WHERE id_card=?', (student_id,)).fetchone()
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    
    # 去重：24h内相似事件合并
    day_ago = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    similar = db.execute(
        'SELECT id FROM mood_events WHERE student_id=? AND source=? AND created_at > ? ORDER BY created_at DESC LIMIT 1',
        (student_id, source, day_ago)
    ).fetchone()
    
    if similar:
        # 标记为高频
        db.execute('UPDATE mood_events SET tags=COALESCE(tags,"")||",高频" WHERE id=?', (similar['id'],))
        db.commit()
    
    # 可见范围：1=学生 2=导师+班主任 3=+心理教师 4=+校方 5=+家长
    visibility = '1,2'
    if severity >= 3:
        visibility = '1,2,3'
    if severity >= 4:
        visibility = '1,2,3,4'
    if severity >= 5:
        visibility = '1,2,3,4,5'
    
    db.execute('''
        INSERT INTO mood_events (student_id, student_name, grade, class_name, campus,
            source, type, severity, content, tags, recorded_by, visibility)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (
        student_id, student['name'], student['grade_name'], student['class_name'],
        data.get('campus', 'benbu'), source,
        'self_report' if source == 'zhixin_jiejie' else 'teacher_observation',
        severity, content, tags, u.get('identity', ''), visibility
    ))
    db.commit()
    event_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    
    # 严重度≥4 自动触发升级
    escalated = False
    if severity >= 4:
        db.execute('''
            INSERT INTO mood_escalations (mood_event_id, escalated_to, escalated_by, reason)
            VALUES (?,?,?,?)
        ''', (event_id, '班主任+心理教师', 'system', f'自动升级: severity={severity}'))
        db.commit()
        escalated = True
        # 写入 unified_events
        _upsert_unified_event(student_id, student['name'], student['grade_name'],
            student['class_name'], data.get('campus', 'benbu'),
            '体能', '心情管理', 'mood_alert',
            {'severity': severity, 'content': content[:200], 'escalated': True},
            f'情绪预警: severity={severity} (已自动升级)',
            datetime.now().strftime('%Y-%m-%d'))
    
    return jsonify({
        'success': True,
        'event_id': event_id,
        'escalated': escalated,
        'message': '已记录' + ('，已自动升级至班主任+心理教师' if escalated else '')
    })

@app.route('/api/mood/student/<id_card>', methods=['GET'])
def mood_student_timeline(id_card):
    """查看学生情绪时间线（权限分级）"""
    _ensure_mood_tables()
    u = _current_user()
    allowed, max_sev = _check_mood_access(id_card, u['role'], u.get('sub_role'),
        u.get('bound_id_card'), u.get('bound_grade'), u.get('bound_class'))
    if not allowed:
        return jsonify({'error': '无权查看'}), 403
    
    db = get_db()
    limit = min(int(request.args.get('limit', 30)), 100)
    rows = db.execute(
        'SELECT * FROM mood_events WHERE student_id=? AND severity <= ? ORDER BY created_at DESC LIMIT ?',
        (id_card, max_sev, limit)
    ).fetchall()
    
    # 获取升级记录
    event_ids = [r['id'] for r in rows]
    escalations = {}
    if event_ids:
        ph = ','.join('?' * len(event_ids))
        esc_rows = db.execute(
            f'SELECT * FROM mood_escalations WHERE mood_event_id IN ({ph})',
            event_ids
        ).fetchall()
        for e in esc_rows:
            escalations.setdefault(e['mood_event_id'], []).append(dict(e))
    
    events = []
    for r in rows:
        d = dict(r)
        d['escalations'] = escalations.get(d['id'], [])
        # 按权限过滤可见内容
        if u['role'] not in ('admin',) and d['severity'] > max_sev:
            d['content'] = '[权限受限]'
        events.append(d)
    
    return jsonify({'events': events, 'total': len(events)})

@app.route('/api/mood/class/<grade>/<class_name>', methods=['GET'])
def mood_class_dashboard(grade, class_name):
    """班级情绪仪表板（教师端）"""
    _ensure_mood_tables()
    u = _current_user()
    if u['role'] not in ('teacher', 'admin'):
        return jsonify({'error': '仅教师可访问'}), 403
    
    db = get_db()
    campus = request.args.get('campus', 'benbu').strip()
    days = min(int(request.args.get('days', 30)), 90)
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    # 班级情绪概览
    stats = db.execute('''
        SELECT severity, COUNT(*) as cnt
        FROM mood_events
        WHERE grade=? AND class_name=? AND created_at >= ?
        GROUP BY severity
    ''', (grade, class_name, since)).fetchall()
    
    # 严重度分布
    sev_dist = {1:0, 2:0, 3:0, 4:0, 5:0}
    total = 0
    for s in stats:
        sev_dist[s['severity']] = s['cnt']
        total += s['cnt']
    
    # 最近事件
    recent = db.execute('''
        SELECT * FROM mood_events
        WHERE grade=? AND class_name=? AND created_at >= ?
        ORDER BY created_at DESC LIMIT 20
    ''', (grade, class_name, since)).fetchall()
    
    # 风险名单（severity ≥ 3 未解决）
    risk = db.execute('''
        SELECT student_id, student_name, MAX(severity) as max_sev, COUNT(*) as cnt
        FROM mood_events
        WHERE grade=? AND class_name=? AND status != ''resolved'' AND severity >= 3
        GROUP BY student_id, student_name
        ORDER BY max_sev DESC
    ''', (grade, class_name)).fetchall()
    
    return jsonify({
        'grade': grade, 'class_name': class_name,
        'period': f'最近{days}天',
        'total_events': total,
        'severity_distribution': sev_dist,
        'risk_list': [dict(r) for r in risk],
        'recent_events': [dict(r) for r in recent],
    })

@app.route('/api/mood/school', methods=['GET'])
def mood_school_overview():
    """全校心情概览（脱敏，仅出聚合统计）"""
    _ensure_mood_tables()
    db = get_db()
    campus = request.args.get('campus', '').strip()
    days = min(int(request.args.get('days', 30)), 90)
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    cond = 'WHERE created_at >= ?'
    params = [since]
    if campus:
        cond += ' AND campus=?'
        params.append(campus)
    
    # 按校区+年级聚合（脱敏）
    rows = db.execute(f'''
        SELECT campus, grade, COUNT(*) as total,
               SUM(CASE WHEN severity >= 4 THEN 1 ELSE 0 END) as high_risk,
               AVG(severity) as avg_severity
        FROM mood_events {cond}
        GROUP BY campus, grade
        ORDER BY campus, grade
    ''', params).fetchall()
    
    # 趋势（按日聚合）
    trend = db.execute(f'''
        SELECT DATE(created_at) as day, COUNT(*) as cnt,
               AVG(severity) as avg_sev
        FROM mood_events {cond}
        GROUP BY DATE(created_at)
        ORDER BY day DESC LIMIT 30
    ''', params).fetchall()
    
    return jsonify({
        'period': f'最近{days}天',
        'by_grade': [dict(r) for r in rows],
        'daily_trend': [dict(r) for r in trend],
    })

@app.route('/api/mood/weekly-report', methods=['GET'])
def mood_weekly_report():
    """AI 周报：情绪趋势 + 风险名单 + 跟进情况"""
    _ensure_mood_tables()
    campus = request.args.get('campus', 'benbu').strip()
    grade = request.args.get('grade', '').strip()
    class_name = request.args.get('class_name', '').strip()
    
    # 确定报告周
    today = datetime.now()
    week_start = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')
    week_id = f'{week_start}_{campus}_{grade}_{class_name}'
    
    db = get_db()
    
    # 检查缓存
    cached = db.execute(
        'SELECT * FROM mood_weekly_reports WHERE report_week=? AND campus=? AND grade=? AND class_name=? ORDER BY created_at DESC LIMIT 1',
        (week_id, campus, grade, class_name)
    ).fetchone()
    if cached:
        return jsonify({'cached': True, 'report': json.loads(cached['report_data'])})
    
    # 构建查询条件
    cond = 'WHERE created_at >= ?'
    params = [week_start]
    if campus:
        cond += ' AND campus=?'
        params.append(campus)
    if grade:
        cond += ' AND grade=?'
        params.append(grade)
    if class_name:
        cond += ' AND class_name=?'
        params.append(class_name)
    
    # 本周统计
    total = db.execute(f'SELECT COUNT(*) FROM mood_events {cond}', params).fetchone()[0]
    avg_sev = db.execute(f'SELECT AVG(severity) FROM mood_events {cond}', params).fetchone()[0] or 0
    high_risk = db.execute(f'SELECT COUNT(*) FROM mood_events {cond} AND severity >= 4', params).fetchone()[0]
    unresolved = db.execute(f'SELECT COUNT(*) FROM mood_events {cond} AND status != ''resolved''', params).fetchone()[0]
    
    # 风险名单
    risk_list = db.execute(f'''
        SELECT student_id, student_name, grade, class_name, MAX(severity) as max_sev
        FROM mood_events {cond} AND severity >= 3 AND status != ''resolved''
        GROUP BY student_id ORDER BY max_sev DESC LIMIT 10
    ''', params).fetchall()
    
    report = {
        'week': week_start,
        'total_events': total,
        'avg_severity': round(avg_sev, 2),
        'high_risk_count': high_risk,
        'unresolved_count': unresolved,
        'risk_list': [dict(r) for r in risk_list],
        'status': 'ok' if high_risk == 0 else ('warning' if high_risk < 3 else 'critical'),
    }
    
    # 缓存
    db.execute('''
        INSERT INTO mood_weekly_reports (campus, grade, class_name, report_week, report_data)
        VALUES (?,?,?,?,?)
    ''', (campus, grade, class_name, week_id, json.dumps(report, ensure_ascii=False)))
    db.commit()
    
    return jsonify({'cached': False, 'report': report})

@app.route('/api/mood/escalate', methods=['POST'])
def mood_escalate():
    """手动升级或记录跟进措施"""
    _ensure_mood_tables()
    data = request.get_json() or {}
    event_id = data.get('event_id')
    action = data.get('action_taken', '').strip()
    escalated_to = data.get('escalated_to', '').strip()
    
    if not event_id:
        return jsonify({'error': 'event_id 必填'}), 400
    
    db = get_db()
    event = db.execute('SELECT * FROM mood_events WHERE id=?', (event_id,)).fetchone()
    if not event:
        return jsonify({'error': '事件不存在'}), 404
    
    db.execute('''
        INSERT INTO mood_escalations (mood_event_id, escalated_to, escalated_by, reason, action_taken)
        VALUES (?,?,?,?,?)
    ''', (event_id, escalated_to, _current_user().get('identity', ''), data.get('reason', ''), action))
    
    if action:
        db.execute('UPDATE mood_events SET status=? WHERE id=?', ('tracking', event_id))
    db.commit()
    
    return jsonify({'success': True, 'message': '已记录升级/跟进'})

@app.route('/api/mood/authorization', methods=['GET', 'POST'])
def mood_authorization():
    """情绪管理授权（家长+学生双向授权）"""
    _ensure_mood_tables()
    db = get_db()
    
    if request.method == 'GET':
        student_id = request.args.get('student_id', '').strip()
        if not student_id:
            return jsonify({'error': 'student_id 必填'}), 400
        auth = db.execute('SELECT * FROM mood_authorizations WHERE student_id=?', (student_id,)).fetchone()
        return jsonify({
            'authorized': bool(auth and (auth['parent_consent'] or auth['student_consent'])),
            'parent_consent': bool(auth and auth['parent_consent']),
            'student_consent': bool(auth and auth['student_consent']),
        })
    
    # POST: 授权
    data = request.get_json() or {}
    student_id = data.get('student_id', '').strip()
    consent_type = data.get('consent_type', 'parent')  # parent / student
    
    if not student_id:
        return jsonify({'error': 'student_id 必填'}), 400
    
    field = 'parent_consent' if consent_type == 'parent' else 'student_consent'
    db.execute(f'''
        INSERT INTO mood_authorizations (student_id, {field}, authorized_at)
        VALUES (?, 1, ?)
        ON CONFLICT(student_id) DO UPDATE SET {field}=1, authorized_at=?
    ''', (student_id, datetime.now().isoformat(), datetime.now().isoformat()))
    db.commit()
    
    return jsonify({'success': True, 'message': f'{consent_type} 授权已完成'})


# ==================== 奖状系统 API（Phase 3：领取式 + 自传奖状）====================

def _ensure_award_tables():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS claimable_awards(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL, student_name TEXT, grade TEXT, class_name TEXT,
        campus TEXT DEFAULT '',
        award_name TEXT NOT NULL, level TEXT DEFAULT '校',
        issued_by TEXT, issue_date TEXT, description TEXT,
        media TEXT, claim_status TEXT DEFAULT 'pending',
        claim_deadline TEXT, claimed_at TEXT,
        ai_highlight INTEGER DEFAULT 0,
        share_template TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_claim_student ON claimable_awards(student_id)')
    db.execute('''CREATE TABLE IF NOT EXISTS self_reported_awards(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL, student_name TEXT, grade TEXT, class_name TEXT,
        campus TEXT DEFAULT '', uploader TEXT,
        award_name TEXT NOT NULL, type TEXT, level TEXT,
        award_date TEXT, issuing_org TEXT, description TEXT,
        media TEXT, ocr_result TEXT,
        ai_verified INTEGER DEFAULT 0, teacher_verified INTEGER DEFAULT 0,
        duplicate_of INTEGER, status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_selfrep_status ON self_reported_awards(status)')
    db.commit()

# ── 领取式奖状（教师push → 学生claim）──

@app.route('/api/awards/issue', methods=['POST'])
def award_issue():
    """教师/校方批量颁奖"""
    _ensure_award_tables()
    data = request.get_json() or {}
    db = get_db()
    awards = data.get('awards', [])
    campus = data.get('campus', 'benbu')
    deadline_days = int(data.get('deadline_days', 30))
    deadline = (datetime.now() + timedelta(days=deadline_days)).strftime('%Y-%m-%d')
    
    inserted = 0
    for a in awards:
        sid = a.get('student_id', '').strip()
        if not sid:
            continue
        db.execute('''
            INSERT INTO claimable_awards (student_id, student_name, grade, class_name, campus,
                award_name, level, issued_by, description, media, claim_deadline)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ''', (sid, a.get('student_name',''), a.get('grade',''), a.get('class_name',''),
              campus, a.get('award_name',''), a.get('level','校'),
              a.get('issued_by',''), a.get('description',''),
              json.dumps(a.get('media',[])), deadline))
        inserted += 1
    db.commit()
    return jsonify({'success': True, 'inserted': inserted, 'deadline': deadline})

@app.route('/api/awards/issue-batch', methods=['POST'])
def award_issue_batch():
    """名单 → AI匹配花名册 → 批量颁奖"""
    _ensure_award_tables()
    data = request.get_json() or {}
    names_text = (data.get('names') or '').strip()
    award_name = data.get('award_name', '').strip()
    level = data.get('level', '校').strip()
    campus = data.get('campus', 'benbu').strip()
    
    if not names_text or not award_name:
        return jsonify({'error': 'names 和 award_name 必填'}), 400
    
    db = get_db()
    # 解析名单（支持换行、逗号、顿号分隔）
    import re
    names = [n.strip() for n in re.split(r'[\n,，、]+', names_text) if n.strip()]
    
    matches = []
    unmatched = []
    for name in names:
        student = db.execute(
            'SELECT id_card, name, grade_name, class_name FROM students WHERE name=?',
            (name,)
        ).fetchone()
        if student:
            matches.append(dict(student))
        else:
            unmatched.append(name)
    
    # 批量插入
    deadline_days = int(data.get('deadline_days', 30))
    deadline = (datetime.now() + timedelta(days=deadline_days)).strftime('%Y-%m-%d')
    for m in matches:
        db.execute('''
            INSERT INTO claimable_awards (student_id, student_name, grade, class_name, campus,
                award_name, level, issued_by, description, claim_deadline)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        ''', (m['id_card'], m['name'], m['grade_name'], m['class_name'],
              campus, award_name, level, data.get('issued_by',''),
              data.get('description',''), deadline))
    db.commit()
    
    return jsonify({
        'success': True,
        'matched': len(matches),
        'unmatched': len(unmatched),
        'unmatched_names': unmatched,
        'deadline': deadline
    })

@app.route('/api/awards/claim/<int:award_id>', methods=['POST'])
def award_claim(award_id):
    """学生领取奖状"""
    _ensure_award_tables()
    db = get_db()
    award = db.execute('SELECT * FROM claimable_awards WHERE id=?', (award_id,)).fetchone()
    if not award:
        return jsonify({'error': '奖状不存在'}), 404
    if award['claim_status'] == 'claimed':
        return jsonify({'error': '已领取'}), 400
    if award['claim_status'] == 'expired':
        return jsonify({'error': '已过期'}), 400
    
    db.execute('UPDATE claimable_awards SET claim_status=?, claimed_at=? WHERE id=?',
               ('claimed', datetime.now().isoformat(), award_id))
    db.commit()
    
    # 写入统一事件流
    _upsert_unified_event(award['student_id'], award['student_name'],
        award['grade'], award['class_name'], award['campus'],
        '成长', '市区奖状' if award['level'] in ('区','市','省','国家') else '校级奖状',
        'award_claimed',
        {'award_name': award['award_name'], 'level': award['level']},
        f'领取奖状: {award["award_name"]} ({award["level"]}级)',
        datetime.now().strftime('%Y-%m-%d'))
    
    return jsonify({'success': True, 'message': '领取成功！'})

@app.route('/api/awards/student/<id_card>', methods=['GET'])
def award_student_list(id_card):
    """学生奖状列表（领取式 + 自传）"""
    _ensure_award_tables()
    db = get_db()
    claimable = [dict(r) for r in db.execute(
        'SELECT * FROM claimable_awards WHERE student_id=? ORDER BY created_at DESC',
        (id_card,)
    ).fetchall()]
    self_reported = [dict(r) for r in db.execute(
        'SELECT * FROM self_reported_awards WHERE student_id=? ORDER BY created_at DESC',
        (id_card,)
    ).fetchall()]
    return jsonify({
        'claimable': claimable,
        'self_reported': self_reported,
        'total': len(claimable) + len(self_reported),
    })

@app.route('/api/awards/highlights/<id_card>', methods=['GET'])
def award_highlights(id_card):
    """AI精选高光时刻（返回4个）"""
    _ensure_award_tables()
    db = get_db()
    # 优先级：国家级 > 省 > 市 > 区 > 校，已领取优先
    awards = db.execute('''
        SELECT * FROM claimable_awards WHERE student_id=?
        ORDER BY CASE level WHEN '国家' THEN 0 WHEN '省' THEN 1 WHEN '市' THEN 2 WHEN '区' THEN 3 ELSE 4 END,
        CASE claim_status WHEN 'claimed' THEN 0 ELSE 1 END
        LIMIT 4
    ''', (id_card,)).fetchall()
    return jsonify({'highlights': [dict(r) for r in awards]})

@app.route('/api/awards/ai-speech', methods=['POST'])
def award_ai_speech():
    """AI 生成颁奖辞（调用千帆）"""
    data = request.get_json() or {}
    award_name = data.get('award_name', '')
    student_name = data.get('student_name', '')
    if not AI_API_KEY:
        return jsonify({'speech': f'祝贺{student_name}同学获得{award_name}！继续加油！'})
    
    prompt = f'请为一位名叫{student_name}的小学生写一段50字以内的颁奖辞，奖项是"{award_name}"。语气温暖、鼓励性，像老师对学生的寄语。只输出颁奖辞，不要其他。'
    try:
        body = json.dumps({
            'model': AI_MODEL,
            'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': 200, 'temperature': 0.8
        }).encode()
        req = Request(AI_URL, data=body, headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {AI_API_KEY}'
        })
        resp = urlopen(req, timeout=15)
        result = json.loads(resp.read())
        speech = result['choices'][0]['message']['content'].strip()
        return jsonify({'speech': speech})
    except Exception as e:
        return jsonify({'speech': f'祝贺{student_name}同学获得{award_name}！继续加油！'})

# ── 自传奖状（学生/家长上传 → 教师审核）──

@app.route('/api/awards/self-report', methods=['POST'])
def award_self_report():
    """上传校外奖状"""
    _ensure_award_tables()
    db = get_db()
    
    student_id = request.form.get('student_id', '').strip()
    award_name = request.form.get('award_name', '').strip()
    award_type = request.form.get('type', 'other').strip()
    level = request.form.get('level', '市').strip()
    issuing_org = request.form.get('issuing_org', '').strip()
    description = request.form.get('description', '').strip()
    
    if not student_id or not award_name:
        return jsonify({'error': 'student_id 和 award_name 必填'}), 400
    
    # 获取学生信息
    student = db.execute('SELECT * FROM students WHERE id_card=?', (student_id,)).fetchone()
    if not student:
        student = db.execute('SELECT * FROM students_luojing WHERE id_card=?', (student_id,)).fetchone()
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    
    # 处理上传图片
    media_files = []
    for key in request.files:
        f = request.files[key]
        if f and f.filename:
            fname = f"self_report_{student_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{f.filename}"
            fpath = os.path.join(BASE_DIR, 'static', 'self_reported', fname)
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            f.save(fpath)
            media_files.append(f'/static/self_reported/{fname}')
    
    db.execute('''
        INSERT INTO self_reported_awards (student_id, student_name, grade, class_name, campus,
            uploader, award_name, type, level, award_date, issuing_org, description, media)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (student_id, student['name'], student['grade_name'], student['class_name'],
          request.form.get('campus','benbu'), request.form.get('uploader','parent'),
          award_name, award_type, level,
          request.form.get('award_date',''), issuing_org, description,
          json.dumps(media_files)))
    db.commit()
    
    return jsonify({'success': True, 'message': '已提交，等待教师审核', 'media': media_files})

@app.route('/api/awards/pending', methods=['GET'])
def award_pending_review():
    """教师审核列表"""
    _ensure_award_tables()
    db = get_db()
    rows = db.execute(
        'SELECT * FROM self_reported_awards WHERE status=? ORDER BY created_at DESC LIMIT 50',
        ('pending',)
    ).fetchall()
    return jsonify({'pending': [dict(r) for r in rows], 'total': len(rows)})

@app.route('/api/awards/verify/<int:award_id>', methods=['POST'])
def award_verify(award_id):
    """教师审核（通过/驳回）"""
    _ensure_award_tables()
    data = request.get_json() or {}
    action = data.get('action', 'approve')  # approve / reject
    reason = data.get('reason', '')
    
    db = get_db()
    award = db.execute('SELECT * FROM self_reported_awards WHERE id=?', (award_id,)).fetchone()
    if not award:
        return jsonify({'error': '奖状不存在'}), 404
    
    new_status = 'approved' if action == 'approve' else 'rejected'
    db.execute('UPDATE self_reported_awards SET status=?, teacher_verified=? WHERE id=?',
               (new_status, 1 if action == 'approve' else 0, award_id))
    db.commit()
    
    if action == 'approve':
        # 写入统一事件流
        _upsert_unified_event(award['student_id'], award['student_name'],
            award['grade'], award['class_name'], award['campus'],
            '兴趣', '自传奖状', 'self_reported_award',
            {'award_name': award['award_name'], 'type': award['type'],
             'level': award['level'], 'issuing_org': award['issuing_org']},
            f'校外奖状: {award["award_name"]} ({award["level"]}级)',
            award.get('award_date') or datetime.now().strftime('%Y-%m-%d'))
    
    return jsonify({'success': True, 'status': new_status})


# ==================== 阅读推荐 API（Phase 4）====================

def _ensure_reading_tables():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS reading_profiles(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL UNIQUE, student_name TEXT,
        grade TEXT, class_name TEXT,
        chinese_level TEXT, chinese_total_books INTEGER DEFAULT 0, chinese_total_hours REAL DEFAULT 0,
        chinese_genres TEXT,
        english_level TEXT, english_vocabulary INTEGER DEFAULT 0,
        english_reading_speed REAL DEFAULT 0, english_genres TEXT,
        preferences TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS reading_recommendations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL, book_title TEXT NOT NULL,
        author TEXT, reason TEXT, algorithm TEXT,
        difficulty_match REAL, diversity_score REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    db.commit()

@app.route('/api/reading/profile/<id_card>', methods=['GET'])
def reading_profile(id_card):
    """学生阅读画像"""
    _ensure_reading_tables()
    db = get_db()
    
    # 从 library_records 实时计算
    stats = db.execute('''
        SELECT COUNT(*) as total_books, COUNT(DISTINCT title) as unique_titles
        FROM library_records WHERE borrower_name = (
            SELECT name FROM students WHERE id_card=? UNION SELECT name FROM students_luojing WHERE id_card=?
        )
    ''', (id_card, id_card)).fetchone()
    
    # 从 reading_profiles 获取画像
    profile = db.execute('SELECT * FROM reading_profiles WHERE student_id=?', (id_card,)).fetchone()
    
    return jsonify({
        'profile': dict(profile) if profile else None,
        'live_stats': {
            'total_books': stats['total_books'] if stats else 0,
            'unique_titles': stats['unique_titles'] if stats else 0,
        }
    })

@app.route('/api/reading/recommend/<id_card>', methods=['GET'])
def reading_recommend(id_card):
    """AI 推荐书单（基于画像 + 协同过滤）"""
    _ensure_reading_tables()
    db = get_db()
    limit = min(int(request.args.get('limit', 5)), 20)
    
    # 获取学生年级和已读书目
    student = db.execute('SELECT name, grade_name, class_name FROM students WHERE id_card=? UNION SELECT name, grade_name, class_name FROM students_luojing WHERE id_card=?',
                         (id_card, id_card)).fetchone()
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    
    name = student['name']
    grade = student['grade_name']
    
    # 已读标题
    read_titles = set(r[0] for r in db.execute(
        'SELECT DISTINCT title FROM library_records WHERE borrower_name=?', (name,)
    ).fetchall())
    
    # 协同过滤：同年级其他学生借阅的热门书
    suggestions = db.execute('''
        SELECT title, COUNT(*) as popularity
        FROM library_records
        WHERE borrower_grade=? AND title NOT IN ({})
        GROUP BY title ORDER BY popularity DESC LIMIT ?
    '''.format(','.join('?' * len(read_titles)) if read_titles else "''"),
        [grade] + list(read_titles) + [limit]
    ).fetchall() if read_titles else db.execute('''
        SELECT title, COUNT(*) as popularity
        FROM library_records WHERE borrower_grade=?
        GROUP BY title ORDER BY popularity DESC LIMIT ?
    ''', (grade, limit)).fetchall()
    
    recommendations = []
    for s in suggestions:
        recommendations.append({
            'title': s['title'],
            'popularity': s['popularity'],
            'reason': f'{grade}热门借阅 (共{s["popularity"]}次)',
            'algorithm': 'collaborative_filter'
        })
    
    return jsonify({'recommendations': recommendations, 'student_grade': grade})


# ==================== 劳动实践 API（Phase 5a：开放模板架构）====================

def _ensure_labor_tables():
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS activity_templates(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE, type TEXT, cycle TEXT DEFAULT 'annual',
        default_tags TEXT, eval_dimensions TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS activity_instances(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id INTEGER, name TEXT NOT NULL, date TEXT,
        location TEXT, grade TEXT, class_name TEXT, campus TEXT DEFAULT '',
        participants TEXT, media TEXT, tags TEXT, eval TEXT, ai_summary TEXT,
        created_by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS activity_tags(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE, category TEXT
    )""")
    preset_tags = ['丰收','五一','打扫','种植','志愿','运动会','科技节','艺术节','读书','研学','义卖','环保']
    for t in preset_tags:
        try:
            db.execute("INSERT INTO activity_tags (name, category) VALUES (?,'预设')", (t,))
        except:
            pass
    db.commit()

@app.route('/api/activities/templates', methods=['GET', 'POST'])
def activity_templates():
    """活动模板列表 / 创建"""
    _ensure_labor_tables()
    db = get_db()
    if request.method == 'POST':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'error': 'name required'}), 400
        try:
            db.execute(
                'INSERT INTO activity_templates (name, type, cycle, default_tags, eval_dimensions) VALUES (?,?,?,?,?)',
                (name, data.get('type', ''), data.get('cycle', 'annual'),
                 json.dumps(data.get('tags', [])), json.dumps(data.get('eval_dimensions', []))))
            db.commit()
        except:
            return jsonify({'error': 'template name exists'}), 409
        return jsonify({'success': True})
    rows = db.execute('SELECT * FROM activity_templates ORDER BY name').fetchall()
    return jsonify({'templates': [dict(r) for r in rows]})

@app.route('/api/activities', methods=['GET', 'POST'])
def activity_instances():
    """活动实例列表 / 创建"""
    _ensure_labor_tables()
    db = get_db()
    if request.method == 'POST':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'error': 'name required'}), 400
        db.execute(
            'INSERT INTO activity_instances (template_id, name, date, location, grade, class_name, campus, participants, media, tags, eval, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (data.get('template_id'), name, data.get('date', ''), data.get('location', ''),
             data.get('grade', ''), data.get('class_name', ''), data.get('campus', 'benbu'),
             json.dumps(data.get('participants', [])), json.dumps(data.get('media', [])),
             json.dumps(data.get('tags', [])), json.dumps(data.get('eval', {})), data.get('created_by', '')))
        db.commit()
        eid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        for p in (data.get('participants') or [])[:20]:
            if isinstance(p, dict) and p.get('id_card'):
                _upsert_unified_event(p['id_card'], p.get('name', ''),
                    data.get('grade', ''), data.get('class_name', ''),
                    data.get('campus', 'benbu'), '劳动', name, 'activity_participation',
                    {'activity': name, 'tags': data.get('tags', [])},
                    '参加: ' + name, data.get('date', ''))
        return jsonify({'success': True, 'id': eid})
    grade = request.args.get('grade', '').strip()
    class_name = request.args.get('class_name', '').strip()
    campus = request.args.get('campus', 'benbu').strip()
    limit = min(int(request.args.get('limit', 20)), 100)
    conds = ['campus=?']
    params = [campus]
    if grade:
        conds.append('grade=?'); params.append(grade)
    if class_name:
        conds.append('class_name=?'); params.append(class_name)
    rows = db.execute(
        'SELECT * FROM activity_instances WHERE ' + ' AND '.join(conds) + ' ORDER BY date DESC LIMIT ?',
        params + [limit]).fetchall()
    return jsonify({'activities': [dict(r) for r in rows], 'total': len(rows)})

@app.route('/api/activities/ai-summarize/<int:activity_id>', methods=['POST'])
def activity_ai_summarize(activity_id):
    """AI 生成活动总结"""
    _ensure_labor_tables()
    db = get_db()
    act = db.execute('SELECT * FROM activity_instances WHERE id=?', (activity_id,)).fetchone()
    if not act:
        return jsonify({'error': 'activity not found'}), 404
    if not AI_API_KEY:
        return jsonify({'summary': '活动' + act['name'] + '圆满完成！同学们积极参与，收获满满。'})
    try:
        prompt = '为小学生活动"' + act['name'] + '"写一段30-50字的活动总结。语气活泼、正面。只输出总结。'
        body = json.dumps({
            'model': AI_MODEL,
            'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': 150, 'temperature': 0.7
        }).encode()
        req = Request(AI_URL, data=body, headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + AI_API_KEY
        })
        resp = urlopen(req, timeout=15)
        result = json.loads(resp.read())
        summary = result['choices'][0]['message']['content'].strip()
        db.execute('UPDATE activity_instances SET ai_summary=? WHERE id=?', (summary, activity_id))
        db.commit()
        return jsonify({'summary': summary})
    except:
        return jsonify({'summary': '活动' + act['name'] + '圆满完成！'})


# ==================== 数字影音馆 API（Phase 5b）====================

def _ensure_media_tables():
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS media_works(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_name TEXT NOT NULL, work_title TEXT NOT NULL,
        media_type TEXT NOT NULL, media_path TEXT NOT NULL,
        thumbnail_path TEXT, award_name TEXT, award_level TEXT,
        grade TEXT, class_name TEXT, campus TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS media_interactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        work_id INTEGER NOT NULL, kind TEXT NOT NULL,
        user_name TEXT NOT NULL, text TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    db.commit()

@app.route('/api/media-works', methods=['GET'])
def media_works_list():
    _ensure_media_tables()
    db = get_db()
    grade = request.args.get('grade', '').strip()
    class_name = request.args.get('class_name', '').strip()
    media_type = request.args.get('type', '').strip()
    limit = min(int(request.args.get('limit', 20)), 100)
    conds = []; params = []
    if grade:
        conds.append('grade=?'); params.append(grade)
    if class_name:
        conds.append('class_name=?'); params.append(class_name)
    if media_type:
        conds.append('media_type=?'); params.append(media_type)
    where = ('WHERE ' + ' AND '.join(conds)) if conds else ''
    rows = db.execute(
        'SELECT * FROM media_works ' + where + ' ORDER BY created_at DESC LIMIT ?',
        params + [limit]).fetchall()
    return jsonify({'works': [dict(r) for r in rows], 'total': len(rows)})

@app.route('/api/media-works/upload', methods=['POST'])
def media_works_upload():
    _ensure_media_tables()
    db = get_db()
    sn = request.form.get('student_name', '').strip()
    wt = request.form.get('work_title', '').strip()
    mt = request.form.get('media_type', 'video').strip()
    gr = request.form.get('grade', '').strip()
    cn = request.form.get('class_name', '').strip()
    if not sn or not wt:
        return jsonify({'error': 'required fields missing'}), 400
    media_files = []
    for key in request.files:
        f = request.files[key]
        if f and f.filename:
            fname = 'media_' + mt + '_' + datetime.now().strftime('%Y%m%d%H%M%S') + '_' + f.filename
            fpath = os.path.join(BASE_DIR, 'static', 'media_works', fname)
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            f.save(fpath)
            media_files.append('/static/media_works/' + fname)
    if not media_files:
        return jsonify({'error': 'no file uploaded'}), 400
    db.execute(
        'INSERT INTO media_works (student_name, work_title, media_type, media_path, thumbnail_path, award_name, award_level, grade, class_name, campus) VALUES (?,?,?,?,?,?,?,?,?,?)',
        (sn, wt, mt, media_files[0], request.form.get('thumbnail_path', ''),
         request.form.get('award_name', ''), request.form.get('award_level', ''),
         gr, cn, request.form.get('campus', 'benbu')))
    db.commit()
    s = db.execute(
        'SELECT id_card FROM students WHERE name=? AND grade_name=? AND class_name=?',
        (sn, gr, cn)).fetchone()
    if s:
        _upsert_unified_event(s['id_card'], sn, gr, cn,
            request.form.get('campus', 'benbu'), '审美', '数字影音馆', 'media_work',
            {'work_title': wt, 'media_type': mt},
            '影音作品: ' + wt, datetime.now().strftime('%Y-%m-%d'))
    return jsonify({'success': True, 'media_path': media_files[0]})

@app.route('/api/media-like', methods=['POST'])
def media_like():
    _ensure_media_tables()
    data = request.get_json() or {}
    db = get_db()
    db.execute('INSERT INTO media_interactions (work_id, kind, user_name) VALUES (?,?,?)',
               (data.get('work_id'), 'like', data.get('user_name', '匿名')))
    db.commit()
    cnt = db.execute(
        'SELECT COUNT(*) FROM media_interactions WHERE work_id=? AND kind=?',
        (data.get('work_id'), 'like')).fetchone()[0]
    return jsonify({'success': True, 'like_count': cnt})

@app.route('/api/media-comment', methods=['POST'])
def media_comment():
    _ensure_media_tables()
    data = request.get_json() or {}
    db = get_db()
    db.execute('INSERT INTO media_interactions (work_id, kind, user_name, text) VALUES (?,?,?,?)',
               (data.get('work_id'), 'comment', data.get('user_name', '匿名'), data.get('text', '')))
    db.commit()
    return jsonify({'success': True})


# ==================== 语文朗读游戏 API（Phase 5c）====================

@app.route('/api/reading-aloud/poems', methods=['GET'])
def reading_aloud_poems():
    """获取古诗字库（按难度分级）"""
    level = request.args.get('level', 'easy').strip()
    poems = {
        'easy': [
            {'title': '静夜思', 'author': '李白', 'text': '床前明月光，疑是地上霜。举头望明月，低头思故乡。', 'type': '五言'},
            {'title': '春晓', 'author': '孟浩然', 'text': '春眠不觉晓，处处闻啼鸟。夜来风雨声，花落知多少。', 'type': '五言'},
            {'title': '登鹳雀楼', 'author': '王之涣', 'text': '白日依山尽，黄河入海流。欲穷千里目，更上一层楼。', 'type': '五言'},
            {'title': '悯农', 'author': '李绅', 'text': '锄禾日当午，汗滴禾下土。谁知盘中餐，粒粒皆辛苦。', 'type': '五言'},
            {'title': '咏鹅', 'author': '骆宾王', 'text': '鹅鹅鹅，曲项向天歌。白毛浮绿水，红掌拨清波。', 'type': '五言'},
        ],
        'medium': [
            {'title': '望庐山瀑布', 'author': '李白', 'text': '日照香炉生紫烟，遥看瀑布挂前川。飞流直下三千尺，疑是银河落九天。', 'type': '七言'},
            {'title': '绝句', 'author': '杜甫', 'text': '两个黄鹂鸣翠柳，一行白鹭上青天。窗含西岭千秋雪，门泊东吴万里船。', 'type': '七言'},
            {'title': '早发白帝城', 'author': '李白', 'text': '朝辞白帝彩云间，千里江陵一日还。两岸猿声啼不住，轻舟已过万重山。', 'type': '七言'},
            {'title': '山行', 'author': '杜牧', 'text': '远上寒山石径斜，白云生处有人家。停车坐爱枫林晚，霜叶红于二月花。', 'type': '七言'},
            {'title': '清明', 'author': '杜牧', 'text': '清明时节雨纷纷，路上行人欲断魂。借问酒家何处有，牧童遥指杏花村。', 'type': '七言'},
        ],
        'hard': [
            {'title': '长恨歌（节选）', 'author': '白居易', 'text': '汉皇重色思倾国，御宇多年求不得。杨家有女初长成，养在深闺人未识。', 'type': '长篇'},
            {'title': '水调歌头', 'author': '苏轼', 'text': '明月几时有？把酒问青天。不知天上宫阙，今夕是何年。', 'type': '词'},
            {'title': '将进酒', 'author': '李白', 'text': '君不见黄河之水天上来，奔流到海不复回。君不见高堂明镜悲白发，朝如青丝暮成雪。', 'type': '长篇'},
        ]
    }
    return jsonify({'poems': poems.get(level, poems['easy']), 'level': level})

@app.route('/api/reading-aloud/score', methods=['POST'])
def reading_aloud_score():
    """记录朗读成绩"""
    data = request.get_json() or {}
    sid = data.get('student_id', '').strip()
    if not sid:
        return jsonify({'error': 'student_id required'}), 400
    poem = data.get('poem_title', '')
    acc = data.get('accuracy', 0)
    _upsert_unified_event(sid, data.get('student_name', ''),
        data.get('grade', ''), data.get('class_name', ''),
        data.get('campus', 'benbu'), '素养', '语文朗读', 'reading_aloud',
        {'poem': poem, 'accuracy': acc, 'time': data.get('time_seconds', 0)},
        '朗读《' + poem + '》准确率 ' + str(acc) + '%',
        datetime.now().strftime('%Y-%m-%d'))
    return jsonify({'success': True, 'score': acc})

@app.route('/api/reading-aloud/ranking', methods=['GET'])
def reading_aloud_ranking():
    """朗读排行榜"""
    db = get_db()
    grade = request.args.get('grade', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)
    if grade:
        rows = db.execute(
            "SELECT student_name, grade, class_name, COUNT(*) as attempts, MAX(CAST(json_extract(event_data, '$.accuracy') AS REAL)) as best_score FROM unified_events WHERE island='素养' AND branch='语文朗读' AND grade=? GROUP BY student_id ORDER BY best_score DESC, attempts DESC LIMIT ?",
            (grade, limit)).fetchall()
    else:
        rows = db.execute(
            "SELECT student_name, grade, class_name, COUNT(*) as attempts, MAX(CAST(json_extract(event_data, '$.accuracy') AS REAL)) as best_score FROM unified_events WHERE island='素养' AND branch='语文朗读' GROUP BY student_id ORDER BY best_score DESC, attempts DESC LIMIT ?",
            (limit,)).fetchall()
    return jsonify({'ranking': [dict(r) for r in rows]})


# ==================== 统一事件流 API（6岛数字画像数据底座）====================

def _upsert_unified_event(student_id, student_name, grade, class_name, campus,
                          island, branch, event_type, event_data=None,
                          event_summary='', event_date=None, school_year=None):
    """向 unified_events 插入或更新事件。按 (student_id, island, branch, event_type, event_date) 去重。"""
    db = get_db()
    event_date = event_date or datetime.now().strftime('%Y-%m-%d')
    data_json = json.dumps(event_data, ensure_ascii=False) if event_data else '{}'
    existing = db.execute(
        'SELECT id FROM unified_events WHERE student_id=? AND island=? AND branch=? AND event_type=? AND event_date=?',
        (student_id, island, branch, event_type, event_date)
    ).fetchone()
    if existing:
        db.execute(
            'UPDATE unified_events SET event_data=?, event_summary=?, grade=?, class_name=?, campus=? WHERE id=?',
            (data_json, event_summary, grade, class_name, campus, existing['id'])
        )
    else:
        db.execute(
            'INSERT INTO unified_events (student_id, student_name, grade, class_name, campus, island, branch, event_type, event_data, event_summary, event_date, school_year) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (student_id, student_name, grade, class_name, campus, island, branch, event_type, data_json, event_summary, event_date, school_year)
        )
    db.commit()

@app.route('/api/unified-events', methods=['GET'])
def get_unified_events():
    """查询统一事件流。支持 ?student_id= / ?island= / ?branch= / ?campus= / ?limit="""
    db = get_db()
    student_id = request.args.get('student_id', '').strip()
    island = request.args.get('island', '').strip()
    branch = request.args.get('branch', '').strip()
    campus = request.args.get('campus', '').strip()
    limit = min(int(request.args.get('limit', 100)), 500)
    
    conditions = []
    params = []
    if student_id:
        conditions.append('student_id=?')
        params.append(student_id)
    if island:
        conditions.append('island=?')
        params.append(island)
    if branch:
        conditions.append('branch=?')
        params.append(branch)
    if campus:
        conditions.append('campus=?')
        params.append(campus)
    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
    rows = db.execute(
        f'SELECT * FROM unified_events {where} ORDER BY event_date DESC, id DESC LIMIT ?',
        params + [limit]
    ).fetchall()
    return jsonify({
        'events': [dict(r) for r in rows],
        'total': len(rows)
    })

@app.route('/api/portrait/student/<id_card>', methods=['GET'])
def portrait_student(id_card):
    """学生数字画像：聚合6岛数据"""
    db = get_db()
    student = db.execute('SELECT * FROM students WHERE id_card=?', (id_card,)).fetchone()
    if not student:
        # 尝试罗泾表
        student = db.execute('SELECT * FROM students_luojing WHERE id_card=?', (id_card,)).fetchone()
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    
    s = dict(student)
    campus = s.get('school_name', '')
    grade = s.get('grade_name', '')
    class_name = s.get('class_name', '')
    
    # 聚合 unified_events
    events = db.execute(
        'SELECT * FROM unified_events WHERE student_id=? ORDER BY event_date DESC',
        (id_card,)
    ).fetchall()
    
    # 按岛分组
    islands = {
        'growth': {'name': '🩷 成长经历', 'branches': {}, 'events': []},
        'interest': {'name': '❤️ 兴趣特长', 'branches': {}, 'events': []},
        'fitness': {'name': '💚 体能强健', 'branches': {}, 'events': []},
        'labor': {'name': '🧡 劳动实践', 'branches': {}, 'events': []},
        'literacy': {'name': '💙 素养跃进', 'branches': {}, 'events': []},
        'aesthetic': {'name': '💜 审美素养', 'branches': {}, 'events': []},
    }
    island_map = {
        '成长': 'growth', '兴趣': 'interest', '体能': 'fitness',
        '劳动': 'labor', '素养': 'literacy', '审美': 'aesthetic',
        'growth': 'growth', 'interest': 'interest', 'fitness': 'fitness',
        'labor': 'labor', 'literacy': 'literacy', 'aesthetic': 'aesthetic',
    }
    
    for e in events:
        ev = dict(e)
        island_key = island_map.get(ev.get('island', ''), '')
        if island_key and island_key in islands:
            islands[island_key]['events'].append(ev)
            branch = ev.get('branch', 'other')
            if branch not in islands[island_key]['branches']:
                islands[island_key]['branches'][branch] = []
            islands[island_key]['branches'][branch].append(ev)
    
    # 统计
    total_events = len(events)
    active_islands = sum(1 for v in islands.values() if v['events'])
    
    # 体能专项数据（直接从原表取最新）
    latest_fitness = db.execute(
        'SELECT * FROM fitness_tests WHERE id_card=? ORDER BY test_year DESC LIMIT 1',
        (id_card,)
    ).fetchone()
    latest_vision = db.execute(
        'SELECT * FROM vision_tests WHERE id_card=? ORDER BY test_date DESC LIMIT 1',
        (id_card,)
    ).fetchone()
    latest_physical = db.execute(
        'SELECT * FROM physical_exams WHERE id_card=? ORDER BY exam_year DESC LIMIT 1',
        (id_card,)
    ).fetchone()
    
    # 奖状统计
    award_count = db.execute(
        'SELECT COUNT(*) as cnt FROM award_certs WHERE student_id_card=?',
        (id_card,)
    ).fetchone()
    
    # 社团
    clubs = db.execute(
        'SELECT * FROM clubs WHERE student_name=?',
        (s.get('name', ''),)
    ).fetchall()
    
    # 阅读统计
    reading_count = db.execute(
        'SELECT COUNT(*) as cnt FROM library_records WHERE borrower_name=?',
        (s.get('name', ''),)
    ).fetchone()
    
    # 美术馆作品
    art_count = db.execute(
        'SELECT COUNT(*) as cnt FROM art_works WHERE student_name=?',
        (s.get('name', ''),)
    ).fetchone()
    
    return jsonify({
        'student': {
            'name': s.get('name'),
            'grade': grade,
            'class_name': class_name,
            'campus': campus,
        },
        'summary': {
            'total_events': total_events,
            'active_islands': active_islands,
            'total_islands': 6,
            'award_count': award_count['cnt'] if award_count else 0,
            'club_count': len(clubs),
            'reading_count': reading_count['cnt'] if reading_count else 0,
            'art_count': art_count['cnt'] if art_count else 0,
        },
        'islands': {k: {
            'name': v['name'],
            'event_count': len(v['events']),
            'branches': list(v['branches'].keys()),
            'recent_events': v['events'][:5]
        } for k, v in islands.items()},
        'fitness_latest': {
            'fitness': dict(latest_fitness) if latest_fitness else None,
            'vision': dict(latest_vision) if latest_vision else None,
            'physical': dict(latest_physical) if latest_physical else None,
        },
        'clubs': [dict(c) for c in clubs],
    })

@app.route('/api/portrait/class/<grade>/<class_name>', methods=['GET'])
def portrait_class(grade, class_name):
    """班级画像：班级整体素质概览"""
    db = get_db()
    campus = request.args.get('campus', 'benbu').strip()
    table = _students_table(campus)
    
    students = db.execute(
        f'SELECT id_card, name FROM {table} WHERE grade_name=? AND class_name=?',
        (grade, class_name)
    ).fetchall()
    
    if not students:
        return jsonify({'error': '班级不存在或无学生'}), 404
    
    student_ids = [s['id_card'] for s in students]
    placeholders = ','.join('?' * len(student_ids))
    
    # 聚合该班所有事件
    events = db.execute(
        f'SELECT island, branch, COUNT(*) as cnt FROM unified_events WHERE student_id IN ({placeholders}) GROUP BY island, branch',
        student_ids
    ).fetchall()
    
    # 按岛汇总
    island_counts = {}
    for e in events:
        island = e['island']
        if island not in island_counts:
            island_counts[island] = {'total': 0, 'branches': {}}
        island_counts[island]['total'] += e['cnt']
        island_counts[island]['branches'][e['branch']] = e['cnt']
    
    return jsonify({
        'grade': grade,
        'class_name': class_name,
        'campus': campus,
        'student_count': len(students),
        'island_distribution': island_counts,
        'total_events': sum(v['total'] for v in island_counts.values()),
    })

@app.route('/api/portrait/school', methods=['GET'])
def portrait_school():
    """学校画像：三校区概览（脱敏统计）"""
    db = get_db()
    campus = request.args.get('campus', '').strip()
    
    # 按校区聚合
    rows = db.execute(
        'SELECT campus, island, branch, COUNT(*) as cnt FROM unified_events GROUP BY campus, island, branch'
    ).fetchall()
    
    campuses = {}
    for r in rows:
        c = r['campus'] or 'unknown'
        if campus and c != campus:
            continue
        if c not in campuses:
            campuses[c] = {'islands': {}, 'total': 0}
        island = r['island']
        if island not in campuses[c]['islands']:
            campuses[c]['islands'][island] = {'total': 0, 'branches': {}}
        campuses[c]['islands'][island]['total'] += r['cnt']
        campuses[c]['islands'][island]['branches'][r['branch']] = r['cnt']
        campuses[c]['total'] += r['cnt']
    
    return jsonify({
        'campuses': campuses,
        'generated_at': datetime.now().isoformat(),
    })


if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print(f"警告: 数据库文件不存在 {DB_PATH}")
        print("请先运行 database_builder.py 构建数据库")

    PORT = int(os.environ.get('PORT', 5050))
    print("================ 宝山学习群岛 API ================")
    print(f" 数据库:    {DB_PATH}")
    print(f" AI:        {'✓ 已配置 ('+AI_PROVIDER+'/'+AI_MODEL+')' if AI_API_KEY else '✗ 未配置 AI API Key'}")
    print(f" 钉钉 SSO:  {'✓ 已配置' if (DINGTALK_APP_KEY and DINGTALK_APP_SECRET) else '✗ 未配置'}")
    print(f" 模式:      {'DEBUG' if DEBUG else 'PROD'}")
    print(f" CORS:      {','.join(CORS_ORIGINS) or '(同源)'}")
    print(f" 上传上限:   {MAX_UPLOAD_MB} MB / 文件, {UPLOAD_RATE_PER_MIN} 次/分钟")
    print(f" 日志:      {_LOG_DIR}")
    print(f" 监听:      http://0.0.0.0:{PORT}")
    print("==================================================")
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
