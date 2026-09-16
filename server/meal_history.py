"""Per-campus meal archives. Reads never finalize choices or mutate live menus."""
import hashlib
import io
import json
import os
import posixpath
import re
import secrets
import sqlite3
import warnings
import threading
from functools import wraps
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import abort, jsonify, request, send_file

_image_lock = threading.Lock()


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def semester_for(value):
    d = date.fromisoformat(value)
    return f'{d.year if d.month >= 9 else d.year - 1}s{1 if d.month >= 9 or d.month == 1 else 2}'


def migrate(db, semester):
    if not re.fullmatch(r'20\d{2}s[12]', semester):
        raise ValueError('学期格式应为 2026s1')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS meal_history_settings(
        key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS meal_week_archives(
        id INTEGER PRIMARY KEY, semester TEXT NOT NULL, week INTEGER NOT NULL,
        version INTEGER NOT NULL, menu_json TEXT NOT NULL, fingerprint TEXT NOT NULL,
        source TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', operator TEXT NOT NULL,
        archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(semester, week, version));
    CREATE TABLE IF NOT EXISTS meal_week_archive_choices(
        archive_id INTEGER NOT NULL REFERENCES meal_week_archives(id),
        student_key TEXT NOT NULL, student_uid TEXT, name TEXT, grade TEXT, class_name TEXT,
        plan_date TEXT NOT NULL, choice TEXT NOT NULL CHECK(choice IN ('A','B')),
        chosen_by TEXT, UNIQUE(archive_id, student_key, plan_date));
    CREATE INDEX IF NOT EXISTS idx_meal_archive_uid
        ON meal_week_archive_choices(archive_id, student_uid);
    CREATE TABLE IF NOT EXISTS meal_week_photos(
        id TEXT PRIMARY KEY, semester TEXT NOT NULL, week INTEGER NOT NULL,
        version INTEGER NOT NULL, original_path TEXT NOT NULL, preview_path TEXT NOT NULL,
        width INTEGER NOT NULL, height INTEGER NOT NULL, bytes INTEGER NOT NULL,
        operator TEXT NOT NULL, published_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(semester, week, version));
    ''')
    db.execute('INSERT OR IGNORE INTO meal_history_settings VALUES (?,?)', ('semester', semester))
    db.commit()


def configured(db):
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='meal_history_settings'").fetchone()
    if not exists:
        return None
    row = db.execute("SELECT value FROM meal_history_settings WHERE key='semester'").fetchone()
    return row[0] if row else None


def menu_data(db, row):
    menu = dict(row)
    days = json.loads(menu.get('service_days_json') or '[]')
    if not days:
        start = date.fromisoformat(menu['date_start'])
        end = date.fromisoformat(menu['date_end'])
        days = [{'plan_date': (start + timedelta(days=i)).isoformat(),
                 'weekday': (start + timedelta(days=i)).isoweekday(),
                 'service_status': 'normal', 'service_note': ''}
                for i in range(min((end-start).days + 1, 7))
                if (start + timedelta(days=i)).isoweekday() <= 5]
    if not days:
        raise ValueError('菜单没有可确认的日期')
    menu['service_days'] = days
    menu.pop('service_days_json', None)
    # Upload/operator metadata and finalization flags do not change menu content.
    for key in ('uploaded_by', 'created_at', 'default_a_finalized_at'):
        menu.pop(key, None)
    menu['meal_plans'] = []
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='nutrition_meal_plans'").fetchone():
        columns = {r[1] for r in db.execute('PRAGMA table_info(nutrition_meal_plans)')}
        fields = [f for f in ('plan_date','plan_type','plan_name','ingredients','calories_kcal',
                  'protein_g','fat_g','protein_pct','fat_pct','vitamin_c_mg','menu_items','source_raw') if f in columns]
        for day in days:
            menu['meal_plans'].extend(dict(r) for r in db.execute(
                'SELECT '+','.join(fields)+' FROM nutrition_meal_plans WHERE plan_date=? ORDER BY plan_type',
                (day['plan_date'],)))
    menu['warnings'] = [f"{d['plan_date']}备注与正常供餐状态可能冲突，请总务核对"
                        for d in days if d.get('service_status') == 'normal'
                        and any(w in d.get('service_note', '') for w in ('放假', '停餐', '不供餐'))]
    return menu


def live_menu(db, semester, week):
    if configured(db) != semester:
        return None
    row = db.execute('SELECT * FROM weekly_menus WHERE week_number=? AND parity=?',
                     (week, 'odd' if week % 2 else 'even')).fetchone()
    if not row or not row['date_start'] or semester_for(row['date_start']) != semester:
        return None
    return menu_data(db, row)


def raw_choices(db, menu):
    return [dict(r) for r in db.execute('''SELECT id_card,name,grade_name,class_name,
        weekday,choice,chosen_by FROM meal_choices WHERE week_number=? AND parity=?
        ORDER BY id_card,weekday''', (menu['week_number'], menu['parity']))]


def fingerprint(menu, rows):
    return hashlib.sha256(pack([menu, rows]).encode()).hexdigest()


def latest(db, semester, week):
    return db.execute('SELECT * FROM meal_week_archives WHERE semester=? AND week=? '
                      'ORDER BY version DESC LIMIT 1', (semester, week)).fetchone()


def closed(menu):
    try:
        deadline = datetime.fromisoformat(menu['selection_deadline'].replace('Z', '+00:00'))
        return datetime.now(deadline.tzinfo) >= deadline
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def snapshot(db, campus, menu_row, source='deadline', operator='system', reason='', expected=None):
    """Caller owns transaction; serializes with writers before invoking this function."""
    semester = configured(db)
    if not semester or not menu_row['date_start'] or semester_for(menu_row['date_start']) != semester:
        return None
    menu = menu_data(db, menu_row)
    if not closed(menu):
        raise ValueError('选餐尚未截止，不能归档')
    previous = latest(db, semester, menu['week_number'])
    if expected is None and previous:
        return previous['id']
    if expected is not None and expected != (previous['version'] if previous else 0):
        raise ValueError('归档版本已变化，请刷新后重试')
    rows = raw_choices(db, menu)
    digest = fingerprint(menu, rows)
    if previous and previous['fingerprint'] == digest:
        return previous['id']
    table = {'benbu':'students_benbu','baolin':'students_baolin','luojing':'students_luojing'}[campus]
    roster = {}
    if db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
        columns = {r[1] for r in db.execute(f'PRAGMA table_info({table})')}
        uid = 'dingtalk_userid' if 'dingtalk_userid' in columns else 'NULL'
        roster = {r['id_card']: dict(r) for r in db.execute(
            f'SELECT id_card,{uid} AS uid,name,grade_name,class_name FROM {table}')}
    archive_id = db.execute('''INSERT INTO meal_week_archives
        (semester,week,version,menu_json,fingerprint,source,reason,operator)
        VALUES (?,?,?,?,?,?,?,?)''', (semester, menu['week_number'],
        (previous['version'] if previous else 0)+1, pack(menu), digest, source, reason, operator)).lastrowid
    days = {int(d['weekday']): d['plan_date'] for d in menu['service_days']
            if d.get('service_status') == 'normal'}
    for r in rows:
        if r['weekday'] not in days:
            continue
        stu = roster.get(r['id_card'])
        same_person = stu and str(stu['name'] or '').strip() == str(r['name'] or '').strip()
        if source == 'deadline' and not same_person:
            continue
        # A revision keeps prior identities even when a child has since left school.
        prior = db.execute('SELECT * FROM meal_week_archive_choices WHERE archive_id=? '
                           'AND student_key=? LIMIT 1',
                           (previous['id'], r['id_card'])).fetchone() if previous else None
        uid = prior['student_uid'] if prior else (stu.get('uid') if same_person else None)
        name = prior['name'] if prior else (stu['name'] if stu and source == 'deadline' else r['name'])
        grade = prior['grade'] if prior else (stu['grade_name'] if stu and source == 'deadline' else r['grade_name'])
        klass = prior['class_name'] if prior else (stu['class_name'] if stu and source == 'deadline' else r['class_name'])
        db.execute('''INSERT INTO meal_week_archive_choices VALUES (?,?,?,?,?,?,?,?,?)''',
                   (archive_id, r['id_card'], uid, name, grade, klass,
                    days[r['weekday']], r['choice'], r['chosen_by']))
    return archive_id


def register(host):
    app = host.app

    def one_image_at_a_time(view):
        # 2GB production host: serialize image decoding across Gunicorn processes.
        @wraps(view)
        def wrapped(*args, **kwargs):
            context(True)
            root = Path(app.config.get('MEAL_PHOTO_ROOT',Path(host.BASE_DIR)/'uploads'/'meal-photos'))
            root.mkdir(parents=True, exist_ok=True)
            if not _image_lock.acquire(blocking=False):
                return jsonify(error='另一张照片正在处理中，请稍后重试'),429
            try:
                with (root/'.upload.lock').open('a+b') as lock:
                    if os.name == 'posix':
                        import fcntl
                        try:
                            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            return jsonify(error='另一张照片正在处理中，请稍后重试'),429
                    return view(*args, **kwargs)
            finally:
                _image_lock.release()
        return wrapped

    @app.before_request
    def protect_meal_photo_storage():
        if posixpath.normpath(request.path).startswith('/uploads/meal-photos/'):
            abort(404)

    @app.after_request
    def private_meal_history(response):
        if request.path.startswith(('/api/meal-history', '/api/meal-photos')):
            response.headers['Cache-Control'] = 'private, no-store'
            response.headers['Vary'] = 'Authorization, Cookie'
        return response

    @app.get('/meal-history.html')
    def meal_history_page():
        return host._inject_campus_page('meal-history.html')

    def context(write=False):
        user = host._current_user()
        manager = user['role'] == 'admin' or (user['role'] == 'teacher' and user.get('sub_role') == 'general')
        allowed = manager or user['role'] == 'parent' or (user['role'] == 'teacher' and user.get('sub_role') == 'class')
        if not allowed or (write and not manager):
            abort(403)
        campus = user.get('campus') or host._resolve_campus()
        db = host.get_db(campus)
        if not configured(db):
            abort(503, description='餐食历史正在准备中')
        return user, campus, db, manager

    def key(semester, week):
        if not re.fullmatch(r'20\d{2}s[12]', semester) or not 1 <= week <= 53:
            abort(400)

    def photo(db, semester, week):
        row = db.execute('SELECT id,version,width,height,published_at FROM meal_week_photos '
                         'WHERE semester=? AND week=? ORDER BY version DESC LIMIT 1', (semester,week)).fetchone()
        return dict(row) if row else None

    def allowed_choices(db, archive, user, semester, manager):
        sql = 'SELECT student_key,student_uid,name,grade,class_name,plan_date,choice FROM meal_week_archive_choices WHERE archive_id=?'
        params = [archive['id']]
        if user['role'] == 'parent':
            # Stable student UserID only: legacy BS_* numbers have been reused.
            sql += ' AND student_uid=?'
            params.append(user.get('bound_student_userid') or '__unbound__')
        elif not manager:
            if semester != configured(db):
                return []
            sql += ' AND grade=? AND class_name=?'
            params.extend([user.get('bound_grade'),user.get('bound_class')])
        return [dict(r) for r in db.execute(sql+' ORDER BY grade,class_name,name,plan_date', params)]

    @app.get('/api/meal-history')
    def meal_history_list():
        user, campus, db, manager = context()
        current = configured(db)
        semesters = {r[0] for r in db.execute('SELECT DISTINCT semester FROM meal_week_archives')}
        semesters.add(current)
        selected = request.args.get('semester', current)
        key(selected, 1)
        weeks = {r[0] for r in db.execute('SELECT DISTINCT week FROM meal_week_archives WHERE semester=?', (selected,))}
        if selected == current:
            for r in db.execute('SELECT week_number,date_start FROM weekly_menus'):
                try:
                    if semester_for(r['date_start']) == current:
                        weeks.add(r['week_number'])
                except (ValueError,TypeError):
                    continue
        items = []
        for week in sorted(weeks, reverse=True):
            a = latest(db, selected, week)
            menu = json.loads(a['menu_json']) if a else live_menu(db, selected, week)
            if menu:
                items.append({'week':week, 'dateStart':menu.get('date_start'), 'dateEnd':menu.get('date_end'),
                              'archived':bool(a), 'photo':photo(db, selected, week)})
        return jsonify(semester=selected, currentSemester=current, semesters=sorted(semesters,reverse=True),
                       campus=campus, canManage=manager, role=user['role'], weeks=items)

    def detail(semester, week):
        key(semester, week)
        user,campus,db,manager = context()
        archive = latest(db, semester, week)
        menu = json.loads(archive['menu_json']) if archive else live_menu(db, semester, week)
        if not menu:
            abort(404)
        picks = allowed_choices(db, archive, user, semester, manager) if archive else []
        days = []
        for day in menu['service_days']:
            current = [p for p in picks if p['plan_date'] == day['plan_date']]
            days.append({**day,'A':sum(p['choice']=='A' for p in current), 'B':sum(p['choice']=='B' for p in current)})
        live = live_menu(db, semester, week)
        changed = bool(archive and live and archive['fingerprint'] != fingerprint(live, raw_choices(db,live)))
        can_view_details = manager or user['role']=='parent' or semester==configured(db)
        # No public static paths: menus are rendered from their archived structured content.
        result = {'semester':semester,'week':week,'days':days,'mealPlans':menu.get('meal_plans',[]),
                  'notes':menu.get('notes',''),'warnings':menu.get('warnings',[]),
                  'photo':photo(db,semester,week),'version':archive['version'] if archive else 0,
                  'source':archive['source'] if archive else None,
                  'archivedAt':archive['archived_at'] if archive else None,
                  'reason':archive['reason'] if archive else '', 'changed':changed,
                  'canRearchive':bool(manager and live and closed(live)),
                  'canExport':bool(archive and user['role']!='parent' and can_view_details),
                  'scope': '本校区' if manager else ('自己的孩子' if user['role']=='parent' else '本班'),
                  'detailRestricted':not can_view_details,
                  'choices':[{k:v for k,v in p.items() if k!='student_uid'} for p in picks]}
        return result

    @app.get('/api/meal-history/<semester>/<int:week>')
    def meal_history_detail(semester, week):
        return jsonify(detail(semester, week))

    @app.post('/api/meal-history/<semester>/<int:week>/rearchive')
    def meal_history_rearchive(semester, week):
        key(semester,week)
        user,campus,db,manager = context(True)
        body = request.get_json(silent=True) or {}
        reason = str(body.get('reason') or '').strip()
        if not reason or len(reason)>300 or type(body.get('version')) is not int:
            return jsonify(error='请填写修正原因并刷新版本'),400
        try:
            db.execute('BEGIN IMMEDIATE')
            menu = live_menu(db,semester,week)
            if not menu:
                raise ValueError('此周已不在当前菜单中，不能重新归档')
            row = db.execute('SELECT * FROM weekly_menus WHERE id=?',(menu['id'],)).fetchone()
            snapshot(db,campus,row,'revision' if latest(db,semester,week) else 'backfill',
                     user['identity'],reason,body['version'])
            db.commit()
        except ValueError as exc:
            db.rollback()
            return jsonify(error=str(exc)),409
        return jsonify(success=True)

    @app.post('/api/meal-history/<semester>/<int:week>/photos')
    @one_image_at_a_time
    def meal_history_upload(semester, week):
        key(semester,week)
        user,campus,db,manager = context(True)
        if not latest(db,semester,week) and not live_menu(db,semester,week):
            return jsonify(error='请先发布对应周次的菜单'),409
        if (request.content_length or 0)>21*1024*1024:
            return jsonify(error='图片不能超过20MB'),413
        f = request.files.get('image')
        try:
            expected = int(request.form['version'])
        except (KeyError,ValueError):
            return jsonify(error='请刷新图片版本后重试'),400
        if not f:
            return jsonify(error='请选择图片'),400
        content = f.stream.read(20*1024*1024+1)
        if len(content)>20*1024*1024:
            return jsonify(error='图片不能超过20MB'),413
        from PIL import Image, ImageOps, UnidentifiedImageError
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as im:
                    if im.format not in ('JPEG','PNG','WEBP') or im.width*im.height>24_000_000:
                        raise ValueError('支持JPEG、PNG、WebP，图片最多2400万像素')
                    im.load()
                    clean = ImageOps.exif_transpose(im).convert('RGB')
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
            return jsonify(error='图片无效或尺寸过大，请重新选择JPEG、PNG、WebP图片'),400
        root = Path(app.config.get('MEAL_PHOTO_ROOT',Path(host.BASE_DIR)/'uploads'/'meal-photos'))
        folder = root/campus/semester/f'week{week:02}'
        folder.mkdir(parents=True,exist_ok=True)
        ident = secrets.token_hex(16)
        original,preview = folder/f'{ident}.jpg',folder/f'{ident}-preview.jpg'
        try:
            clean.save(original,format='JPEG',quality=95)
            width,height=clean.size
            clean.thumbnail((1400,2200))
            clean.save(preview,format='JPEG',quality=85)
            db.execute('BEGIN IMMEDIATE')
            previous=photo(db,semester,week)
            if expected != (previous['version'] if previous else 0):
                raise ValueError('其他老师已更新照片，请刷新后确认替换')
            db.execute('''INSERT INTO meal_week_photos
                (id,semester,week,version,original_path,preview_path,width,height,bytes,operator)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (ident,semester,week,expected+1,str(original.relative_to(root)),str(preview.relative_to(root)),
                 width,height,original.stat().st_size,user['identity']))
            db.commit()
        except Exception as exc:
            db.rollback()
            original.unlink(missing_ok=True);preview.unlink(missing_ok=True)
            if isinstance(exc,ValueError):
                return jsonify(error=str(exc)),409
            raise
        return jsonify(success=True,photo=photo(db,semester,week))

    @app.get('/api/meal-photos/<ident>/file')
    def meal_photo_file(ident):
        user,campus,db,manager=context()
        r=db.execute('SELECT * FROM meal_week_photos WHERE id=?',(ident,)).fetchone()
        if not r or (not manager and photo(db,r['semester'],r['week'])['id'] != ident):
            abort(404)
        root=Path(app.config.get('MEAL_PHOTO_ROOT',Path(host.BASE_DIR)/'uploads'/'meal-photos')).resolve()
        relative=r['preview_path'] if request.args.get('preview')=='1' else r['original_path']
        path=(root/relative).resolve()
        if not path.is_relative_to(root/campus) or not path.is_file():
            abort(404)
        nginx_delivery = (request.remote_addr in ('127.0.0.1','::1')
                          and request.headers.get('X-Meal-Photo-Delivery') == 'nginx')
        if app.config.get('MEAL_PHOTO_X_ACCEL') or nginx_delivery:
            response=app.response_class(mimetype='image/jpeg')
            response.headers['X-Accel-Redirect']='/_meal_photos/'+path.relative_to(root).as_posix()
        else:
            response=send_file(path,mimetype='image/jpeg',max_age=0)
        response.headers['Cache-Control']='private, no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @app.get('/api/meal-history/<semester>/<int:week>/export.xlsx')
    def meal_history_export(semester,week):
        data=detail(semester,week)
        if not data['canExport']:
            abort(403)
        def safe(value):
            return "'"+value if isinstance(value,str) and value[:1] in ('=','+','-','@') else value
        rows=[[safe(p[k]) for k in ('grade','class_name','name','student_key','plan_date','choice')] for p in data['choices']]
        wb=host._xlsx_simple_table('历史选餐明细',['年级','班级','姓名','学生标识','日期','选择'],rows)
        ws=wb.create_sheet('每日汇总',0)
        ws.append(['日期','供餐状态','A餐','B餐'])
        for d in data['days']:
            ws.append([d['plan_date'],'供餐' if d['service_status']=='normal' else '不供餐',d['A'],d['B']])
        ws.append(['统计口径：归档选餐结果，非实际到校用餐人数'])
        ws.append(['来源',data['source'],'版本',data['version']])
        ws.append(['归档时间',data['archivedAt']])
        if data['changed']:
            ws.append(['注意：归档后实时数据发生变化，待总务核对'])
        return host._xlsx_response(wb,f'餐食历史_{semester}_W{week}_V{data["version"]}.xlsx')
