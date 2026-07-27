"""
数据模型 — 数据库操作层
兼容现有宝山实验 SQLite 数据库架构
"""

import sqlite3
import json
import os
from datetime import datetime, date

try:
    from . import security as sec
except ImportError:
    import security as sec

DB_PATH = os.environ.get("NUTRITION_DB_PATH", os.path.join(os.path.dirname(__file__), "nutrition.db"))


def get_db() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS nutrition_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL,
            name TEXT NOT NULL,
            weight_calorie REAL DEFAULT 0.25,
            weight_protein REAL DEFAULT 0.20,
            weight_sugar REAL DEFAULT 0.15,
            weight_sodium REAL DEFAULT 0.15,
            weight_fat REAL DEFAULT 0.10,
            weight_fiber REAL DEFAULT 0.10,
            weight_special REAL DEFAULT 0.05,
            calorie_range_config TEXT,
            protein_min_config TEXT,
            sugar_max_config TEXT,
            sodium_max_config TEXT,
            fat_range_config TEXT,
            fiber_min_config TEXT,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT
        );

        CREATE TABLE IF NOT EXISTS nutrition_children (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_code TEXT UNIQUE NOT NULL,
            display_name TEXT,
            real_name_encrypted TEXT,
            age INTEGER,
            gender TEXT CHECK(gender IN ('男','女','其他')),
            height_cm REAL,
            weight_kg REAL,
            bmi REAL,
            allergies TEXT DEFAULT '[]',
            dietary_restrictions TEXT DEFAULT '[]',
            special_needs TEXT DEFAULT '[]',
            doctor_notes TEXT,
            data_status TEXT DEFAULT 'incomplete',
            data_updated_at TIMESTAMP,
            campus TEXT DEFAULT '本部',
            is_deleted INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS nutrition_meal_plans (
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
        );

        CREATE TABLE IF NOT EXISTS nutrition_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL REFERENCES nutrition_children(id),
            plan_date DATE NOT NULL,
            rule_version TEXT NOT NULL,
            score_a REAL,
            score_b REAL,
            recommended_plan TEXT CHECK(recommended_plan IN ('A','B','MANUAL')),
            reason TEXT,
            exclusion_reason TEXT,
            risk_notes TEXT,
            confirmed INTEGER DEFAULT 0,
            confirmed_by TEXT,
            confirmed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(child_id, plan_date)
        );

        CREATE TABLE IF NOT EXISTS nutrition_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT,
            operator TEXT NOT NULL,
            summary TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_children_code ON nutrition_children(child_code);
        CREATE INDEX IF NOT EXISTS idx_children_campus ON nutrition_children(campus);
        CREATE INDEX IF NOT EXISTS idx_meal_plans_date ON nutrition_meal_plans(plan_date);
        CREATE INDEX IF NOT EXISTS idx_recommendations_date ON nutrition_recommendations(plan_date);
        CREATE INDEX IF NOT EXISTS idx_recommendations_child ON nutrition_recommendations(child_id);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_type ON nutrition_audit_logs(target_type);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON nutrition_audit_logs(created_at);
    """)
    conn.commit()

    # 插入默认规则（如果不存在）
    existing = conn.execute("SELECT COUNT(*) as cnt FROM nutrition_rules").fetchone()
    if existing["cnt"] == 0:
        default_rule = {
            "version": "v1.0-demo",
            "name": "默认演示规则（⚠️ 非医学标准，仅供演示）",
            "weight_calorie": 0.25, "weight_protein": 0.20,
            "weight_sugar": 0.15, "weight_sodium": 0.15,
            "weight_fat": 0.10, "weight_fiber": 0.10, "weight_special": 0.05,
            "calorie_range_config": json.dumps({
                "3-6": [1200, 1600], "7-10": [1600, 2000],
                "11-13": [2000, 2400], "14-17": [2200, 2800]
            }),
            "protein_min_config": json.dumps({
                "3-6": 20, "7-10": 30, "11-13": 40, "14-17": 55
            }),
            "sugar_max_config": json.dumps({
                "3-6": 25, "7-10": 30, "11-13": 35, "14-17": 40
            }),
            "sodium_max_config": json.dumps({
                "3-6": 1200, "7-10": 1500, "11-13": 1800, "14-17": 2000
            }),
            "fat_range_config": json.dumps({
                "3-6": [30, 50], "7-10": [40, 65],
                "11-13": [50, 75], "14-17": [60, 90]
            }),
            "fiber_min_config": json.dumps({
                "3-6": 10, "7-10": 14, "11-13": 18, "14-17": 22
            }),
            "is_active": 1,
        }
        conn.execute("""
            INSERT INTO nutrition_rules (version, name, weight_calorie, weight_protein,
                weight_sugar, weight_sodium, weight_fat, weight_fiber, weight_special,
                calorie_range_config, protein_min_config, sugar_max_config,
                sodium_max_config, fat_range_config, fiber_min_config, is_active, created_by)
            VALUES (:version, :name, :weight_calorie, :weight_protein,
                :weight_sugar, :weight_sodium, :weight_fat, :weight_fiber, :weight_special,
                :calorie_range_config, :protein_min_config, :sugar_max_config,
                :sodium_max_config, :fat_range_config, :fiber_min_config, :is_active, 'system')
        """, default_rule)
        conn.commit()

    conn.close()


# ============================================================
# Children CRUD
# ============================================================

def list_children(campus=None, search=None, status=None, page=1, page_size=50) -> dict:
    """列出儿童（分页，不含加密的真实姓名）"""
    conn = get_db()
    conditions = ["is_deleted = 0"]
    params = {}

    if campus:
        conditions.append("campus = :campus")
        params["campus"] = campus
    if search:
        conditions.append("(child_code LIKE :search OR display_name LIKE :search2)")
        params["search"] = f"%{search}%"
        params["search2"] = f"%{search}%"
    if status:
        conditions.append("data_status = :status")
        params["status"] = status

    where = " AND ".join(conditions)

    # Count
    count_row = conn.execute(f"SELECT COUNT(*) as cnt FROM nutrition_children WHERE {where}", params).fetchone()
    total = count_row["cnt"] if count_row else 0

    # Fetch
    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset
    rows = conn.execute(
        f"""SELECT id, child_code, display_name, age, gender, height_cm, weight_kg, bmi,
                   allergies, dietary_restrictions, special_needs, doctor_notes,
                   data_status, data_updated_at, campus, created_at, updated_at
            FROM nutrition_children
            WHERE {where}
            ORDER BY child_code
            LIMIT :limit OFFSET :offset""",
        params
    ).fetchall()

    conn.close()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_row_to_dict(r) for r in rows],
    }


def get_child(child_id: int) -> dict | None:
    """获取单个儿童详情"""
    conn = get_db()
    row = conn.execute(
        """SELECT id, child_code, display_name, real_name_encrypted, age, gender,
                  height_cm, weight_kg, bmi, allergies, dietary_restrictions,
                  special_needs, doctor_notes, data_status, data_updated_at,
                  campus, created_at, updated_at
           FROM nutrition_children WHERE id = :id AND is_deleted = 0""",
        {"id": child_id}
    ).fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_dict(row, include_encrypted=True)


def create_child(data: dict) -> dict:
    """创建儿童记录"""
    conn = get_db()
    # 自动生成编号
    if not data.get("child_code"):
        max_code = conn.execute(
            "SELECT MAX(child_code) as mc FROM nutrition_children"
        ).fetchone()["mc"]
        if max_code and max_code.startswith("NC_"):
            next_num = int(max_code[3:]) + 1
        else:
            next_num = 1
        data["child_code"] = f"NC_{next_num:04d}"

    # 自动计算BMI
    h = data.get("height_cm")
    w = data.get("weight_kg")
    data["bmi"] = round(w / ((h / 100) ** 2), 2) if h and w and h > 0 else None

    # 判断数据完整性
    required = ["age", "gender", "height_cm", "weight_kg"]
    missing = [f for f in required if data.get(f) is None or data.get(f) == ""]
    data["data_status"] = "complete" if not missing else "incomplete"

    # JSON 序列化
    for field in ["allergies", "dietary_restrictions", "special_needs"]:
        val = data.get(field, [])
        if isinstance(val, list):
            data[field] = json.dumps(val, ensure_ascii=False)
        elif isinstance(val, str) and val.startswith("["):
            pass  # already JSON
        else:
            data[field] = "[]"

    data["data_updated_at"] = datetime.now().isoformat()

    # 加密真实姓名（如果提供）
    real_name = data.get("real_name") or data.get("display_name", "")
    data.setdefault("real_name_encrypted", sec.encrypt_real_name(real_name) if real_name else "")

    # 为可选字段提供默认值
    defaults = {
        "display_name": None, "real_name_encrypted": "", "doctor_notes": None,
        "campus": "本部", "age": None, "gender": None,
        "height_cm": None, "weight_kg": None, "bmi": None,
    }
    for key, default in defaults.items():
        data.setdefault(key, default)

    cursor = conn.execute("""
        INSERT INTO nutrition_children
            (child_code, display_name, real_name_encrypted, age, gender,
             height_cm, weight_kg, bmi, allergies, dietary_restrictions,
             special_needs, doctor_notes, data_status, data_updated_at, campus)
        VALUES (:child_code, :display_name, :real_name_encrypted, :age, :gender,
                :height_cm, :weight_kg, :bmi, :allergies, :dietary_restrictions,
                :special_needs, :doctor_notes, :data_status, :data_updated_at, :campus)
    """, data)
    conn.commit()
    child_id = cursor.lastrowid
    conn.close()
    return get_child(child_id)


def update_child(child_id: int, data: dict) -> dict | None:
    """更新儿童记录"""
    conn = get_db()
    existing = conn.execute(
        "SELECT * FROM nutrition_children WHERE id = :id AND is_deleted = 0",
        {"id": child_id}
    ).fetchone()
    if not existing:
        conn.close()
        return None

    # 重新计算BMI
    h = data.get("height_cm", existing["height_cm"])
    w = data.get("weight_kg", existing["weight_kg"])
    data["bmi"] = round(w / ((h / 100) ** 2), 2) if h and w and h > 0 else None

    # 判断完整性
    required = ["age", "gender", "height_cm", "weight_kg"]
    merged = dict(existing)
    merged.update(data)
    missing = [f for f in required if merged.get(f) is None or merged.get(f) == ""]
    data["data_status"] = "complete" if not missing else "incomplete"

    # JSON
    for field in ["allergies", "dietary_restrictions", "special_needs"]:
        if field in data and isinstance(data[field], list):
            data[field] = json.dumps(data[field], ensure_ascii=False)

    data["data_updated_at"] = datetime.now().isoformat()

    set_clause = ", ".join(f"{k} = :{k}" for k in data.keys())
    data["id"] = child_id
    conn.execute(f"UPDATE nutrition_children SET {set_clause} WHERE id = :id", data)
    conn.commit()
    conn.close()
    return get_child(child_id)


def delete_child(child_id: int) -> bool:
    """软删除儿童记录"""
    conn = get_db()
    conn.execute(
        "UPDATE nutrition_children SET is_deleted = 1, updated_at = :now WHERE id = :id",
        {"id": child_id, "now": datetime.now().isoformat()}
    )
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def get_child_by_code(code: str) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM nutrition_children WHERE child_code = :code AND is_deleted = 0",
        {"code": code}
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ============================================================
# Meal Plans CRUD
# ============================================================

def list_meal_plans(plan_date=None, page=1, page_size=50) -> dict:
    conn = get_db()
    conditions = []
    params = {}
    if plan_date:
        conditions.append("plan_date = :plan_date")
        params["plan_date"] = plan_date

    where = " AND ".join(conditions) if conditions else "1=1"
    count = conn.execute(f"SELECT COUNT(*) as cnt FROM nutrition_meal_plans WHERE {where}", params).fetchone()["cnt"]

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = conn.execute(
        f"SELECT * FROM nutrition_meal_plans WHERE {where} ORDER BY plan_date DESC, plan_type LIMIT :limit OFFSET :offset",
        params
    ).fetchall()
    conn.close()
    return {
        "total": count, "page": page, "page_size": page_size,
        "items": [_row_to_dict(r) for r in rows],
    }


def get_meal_plan(plan_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM nutrition_meal_plans WHERE id = :id", {"id": plan_id}).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def get_meals_by_date(plan_date: str) -> list:
    """获取指定日期的 A+B 餐"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM nutrition_meal_plans WHERE plan_date = :d ORDER BY plan_type",
        {"d": plan_date}
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def upsert_meal_plan(data: dict) -> dict:
    """创建或更新套餐"""
    conn = get_db()
    for field in ["ingredients", "allergens", "suitable_tags"]:
        if field in data and isinstance(data[field], list):
            data[field] = json.dumps(data[field], ensure_ascii=False)

    # 为可选字段提供默认值
    defaults = {
        "plan_name": None, "ingredients": "[]", "unsuitable_notes": None,
    }
    for key, default in defaults.items():
        data.setdefault(key, default)

    existing = conn.execute(
        "SELECT id FROM nutrition_meal_plans WHERE plan_date = :plan_date AND plan_type = :plan_type",
        {"plan_date": data["plan_date"], "plan_type": data["plan_type"]}
    ).fetchone()

    if existing:
        set_clause = ", ".join(f"{k} = :{k}" for k in data.keys())
        data["id"] = existing["id"]
        conn.execute(f"UPDATE nutrition_meal_plans SET {set_clause} WHERE id = :id", data)
    else:
        conn.execute("""
            INSERT INTO nutrition_meal_plans
                (plan_date, plan_type, plan_name, ingredients, calories_kcal,
                 protein_g, fat_g, carbs_g, sugar_g, sodium_mg, fiber_g,
                 allergens, suitable_tags, unsuitable_notes)
            VALUES (:plan_date, :plan_type, :plan_name, :ingredients, :calories_kcal,
                    :protein_g, :fat_g, :carbs_g, :sugar_g, :sodium_mg, :fiber_g,
                    :allergens, :suitable_tags, :unsuitable_notes)
        """, data)

    conn.commit()
    conn.close()
    meals = get_meals_by_date(data["plan_date"])
    return [m for m in meals if m["plan_type"] == data["plan_type"]][0]


def delete_meal_plan(plan_id: int) -> bool:
    conn = get_db()
    conn.execute("DELETE FROM nutrition_meal_plans WHERE id = :id", {"id": plan_id})
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


# ============================================================
# Rules CRUD
# ============================================================

def list_rules() -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM nutrition_rules ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_active_rule() -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM nutrition_rules WHERE is_active = 1 ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def create_rule(data: dict) -> dict:
    conn = get_db()
    # Deactivate all others
    if data.get("is_active"):
        conn.execute("UPDATE nutrition_rules SET is_active = 0")

    cursor = conn.execute("""
        INSERT INTO nutrition_rules
            (version, name, weight_calorie, weight_protein, weight_sugar,
             weight_sodium, weight_fat, weight_fiber, weight_special,
             calorie_range_config, protein_min_config, sugar_max_config,
             sodium_max_config, fat_range_config, fiber_min_config,
             is_active, created_by)
        VALUES (:version, :name, :weight_calorie, :weight_protein, :weight_sugar,
                :weight_sodium, :weight_fat, :weight_fiber, :weight_special,
                :calorie_range_config, :protein_min_config, :sugar_max_config,
                :sodium_max_config, :fat_range_config, :fiber_min_config,
                :is_active, :created_by)
    """, data)
    conn.commit()
    rule_id = cursor.lastrowid
    conn.close()

    conn2 = get_db()
    row = conn2.execute("SELECT * FROM nutrition_rules WHERE id = :id", {"id": rule_id}).fetchone()
    conn2.close()
    return _row_to_dict(row)


def activate_rule(rule_id: int) -> dict | None:
    conn = get_db()
    conn.execute("UPDATE nutrition_rules SET is_active = 0")
    conn.execute("UPDATE nutrition_rules SET is_active = 1, updated_at = :now WHERE id = :id",
                 {"id": rule_id, "now": datetime.now().isoformat()})
    conn.commit()
    row = conn.execute("SELECT * FROM nutrition_rules WHERE id = :id", {"id": rule_id}).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


# ============================================================
# Recommendations
# ============================================================

def save_recommendations(results: list) -> int:
    """批量保存推荐结果（UPSERT）"""
    conn = get_db()
    count = 0
    for r in results:
        conn.execute("""
            INSERT INTO nutrition_recommendations
                (child_id, plan_date, rule_version, score_a, score_b,
                 recommended_plan, reason, exclusion_reason, risk_notes, confirmed)
            VALUES (:child_id, :plan_date, :rule_version, :score_a, :score_b,
                    :recommended_plan, :reason, :exclusion_reason, :risk_notes, 0)
            ON CONFLICT(child_id, plan_date) DO UPDATE SET
                rule_version = excluded.rule_version,
                score_a = excluded.score_a,
                score_b = excluded.score_b,
                recommended_plan = excluded.recommended_plan,
                reason = excluded.reason,
                exclusion_reason = excluded.exclusion_reason,
                risk_notes = excluded.risk_notes,
                confirmed = 0
        """, r)
        count += 1
    conn.commit()
    conn.close()
    return count


def list_recommendations(plan_date=None, confirmed=None, recommended_plan=None,
                          campus=None, page=1, page_size=50) -> dict:
    conn = get_db()
    conditions = ["nc.is_deleted = 0"]
    params = {}

    if plan_date:
        conditions.append("nr.plan_date = :plan_date")
        params["plan_date"] = plan_date
    if confirmed is not None:
        conditions.append("nr.confirmed = :confirmed")
        params["confirmed"] = int(confirmed)
    if recommended_plan:
        conditions.append("nr.recommended_plan = :plan")
        params["plan"] = recommended_plan
    if campus:
        conditions.append("nc.campus = :campus")
        params["campus"] = campus

    where = " AND ".join(conditions)

    count = conn.execute(f"""
        SELECT COUNT(*) as cnt
        FROM nutrition_recommendations nr
        JOIN nutrition_children nc ON nr.child_id = nc.id
        WHERE {where}
    """, params).fetchone()["cnt"]

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = conn.execute(f"""
        SELECT nr.*, nc.child_code, nc.display_name, nc.age, nc.gender,
               nc.data_status, nc.campus
        FROM nutrition_recommendations nr
        JOIN nutrition_children nc ON nr.child_id = nc.id
        WHERE {where}
        ORDER BY nr.recommended_plan, nc.child_code
        LIMIT :limit OFFSET :offset
    """, params).fetchall()
    conn.close()
    return {
        "total": count, "page": page, "page_size": page_size,
        "items": [_row_to_dict(r) for r in rows],
    }


def confirm_recommendation(rec_id: int, operator: str) -> dict | None:
    conn = get_db()
    conn.execute("""
        UPDATE nutrition_recommendations
        SET confirmed = 1, confirmed_by = :op, confirmed_at = :now
        WHERE id = :id
    """, {"id": rec_id, "op": operator, "now": datetime.now().isoformat()})
    conn.commit()
    row = conn.execute(
        """SELECT nr.*, nc.child_code, nc.display_name
           FROM nutrition_recommendations nr
           JOIN nutrition_children nc ON nr.child_id = nc.id
           WHERE nr.id = :id""",
        {"id": rec_id}
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def get_recommendation_stats(plan_date: str) -> dict:
    """获取推荐统计"""
    conn = get_db()
    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM nutrition_recommendations WHERE plan_date = :d",
        {"d": plan_date}
    ).fetchone()["cnt"]
    a_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM nutrition_recommendations WHERE plan_date = :d AND recommended_plan = 'A'",
        {"d": plan_date}
    ).fetchone()["cnt"]
    b_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM nutrition_recommendations WHERE plan_date = :d AND recommended_plan = 'B'",
        {"d": plan_date}
    ).fetchone()["cnt"]
    manual_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM nutrition_recommendations WHERE plan_date = :d AND recommended_plan = 'MANUAL'",
        {"d": plan_date}
    ).fetchone()["cnt"]
    confirmed_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM nutrition_recommendations WHERE plan_date = :d AND confirmed = 1",
        {"d": plan_date}
    ).fetchone()["cnt"]
    conn.close()
    return {
        "plan_date": plan_date,
        "total": total,
        "a_count": a_count,
        "b_count": b_count,
        "manual_count": manual_count,
        "confirmed_count": confirmed_count,
    }


# ============================================================
# Audit Logs
# ============================================================

def add_audit_log(action: str, target_type: str, target_id: str,
                   operator: str, summary: str, ip_address: str = "") -> int:
    conn = get_db()
    # 禁止在日志中输出完整身体数据
    safe_summary = _sanitize_summary(summary)
    cursor = conn.execute("""
        INSERT INTO nutrition_audit_logs (action, target_type, target_id, operator, summary, ip_address)
        VALUES (:action, :target_type, :target_id, :operator, :summary, :ip)
    """, {
        "action": action, "target_type": target_type, "target_id": str(target_id),
        "operator": operator, "summary": safe_summary, "ip": ip_address
    })
    conn.commit()
    log_id = cursor.lastrowid
    conn.close()
    return log_id


def list_audit_logs(page=1, page_size=50, target_type=None, action=None,
                     operator=None, date_from=None, date_to=None) -> dict:
    conn = get_db()
    conditions = []
    params = {}
    if target_type:
        conditions.append("target_type = :tt")
        params["tt"] = target_type
    if action:
        conditions.append("action = :act")
        params["act"] = action
    if operator:
        conditions.append("operator LIKE :op")
        params["op"] = f"%{operator}%"
    if date_from:
        conditions.append("created_at >= :df")
        params["df"] = date_from
    if date_to:
        conditions.append("created_at <= :dt")
        params["dt"] = date_to + " 23:59:59"

    where = " AND ".join(conditions) if conditions else "1=1"
    count = conn.execute(f"SELECT COUNT(*) as cnt FROM nutrition_audit_logs WHERE {where}", params).fetchone()["cnt"]

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = conn.execute(
        f"SELECT * FROM nutrition_audit_logs WHERE {where} ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
        params
    ).fetchall()
    conn.close()
    return {
        "total": count, "page": page, "page_size": page_size,
        "items": [_row_to_dict(r) for r in rows],
    }


# ============================================================
# Helper
# ============================================================

def _row_to_dict(row, include_encrypted=False) -> dict:
    if not row:
        return {}
    d = dict(row)
    # 不返回加密字段给前端（除非指定）
    if not include_encrypted:
        d.pop("real_name_encrypted", None)
    # 过滤内部字段
    d.pop("is_deleted", None)
    return d


def _sanitize_summary(summary: str) -> str:
    """移除日志摘要中可能的敏感身体数据"""
    import re
    # 移除类似 "身高135" "体重30kg" 等
    summary = re.sub(r'身高\s*\d+\.?\d*', '身高**', summary)
    summary = re.sub(r'体重\s*\d+\.?\d*', '体重**', summary)
    summary = re.sub(r'BMI\s*\d+\.?\d*', 'BMI**', summary)
    return summary
