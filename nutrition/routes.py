"""
Flask API 路由 — 儿童营养餐智能分配系统
挂载到现有宝山实验 Flask 应用的路由蓝图
"""

import json
import traceback
from datetime import date, datetime
from flask import Blueprint, request, jsonify, g, Response, current_app

try:
    from . import models
    from . import engine
    from . import security as sec
    from .import_export import parse_import_data, export_to_csv, export_to_json, generate_import_template
except ImportError:
    import models
    import engine
    import security as sec
    from import_export import parse_import_data, export_to_csv, export_to_json, generate_import_template

nutrition_bp = Blueprint("nutrition", __name__, url_prefix="/api/nutrition")

# ============================================================
# 权限辅助
# ============================================================

def _get_role():
    """从请求上下文获取当前用户角色（复用现有认证）"""
    role = getattr(g, "user_role", None)
    if role:
        return role
    if current_app.config.get("NUTRITION_ALLOW_DEMO_HEADERS", False):
        return request.headers.get("X-User-Role", "none")
    return "none"


def _get_bound_child_code():
    """读取服务端认证绑定的孩子；独立 demo 可显式允许旧测试头。"""
    child_code = (getattr(g, "nutrition_child_code", None) or "").strip()
    if child_code:
        return child_code
    if current_app.config.get("NUTRITION_ALLOW_DEMO_HEADERS", False):
        return (request.headers.get("X-Nutrition-Child-Code") or "").strip()
    return ""


def _check_perm(permission: str):
    """检查权限，无权限返回 403"""
    role = _get_role()
    ok, msg = sec.require_permission(role, permission)
    if not ok:
        return jsonify({"error": msg, "code": "FORBIDDEN"}), 403
    return None


def _check_recommend_read():
    """家长仅可读取自己孩子的推荐；其他角色沿用完整推荐读取权限。"""
    role = _get_role()
    permission = "recommend:read_own" if role == "parent" else "recommend:read"
    return _check_perm(permission)


def _log(action: str, target_type: str, target_id: str, summary: str):
    """记录审计日志"""
    try:
        models.add_audit_log(
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            operator=_get_role(),
            summary=summary,
            ip_address=request.remote_addr or "",
        )
    except Exception:
        pass  # 日志失败不影响业务


# ============================================================
# 儿童信息管理
# ============================================================

@nutrition_bp.route("/children", methods=["GET"])
def list_children():
    err = _check_perm("children:read")
    if err:
        return err

    campus = request.args.get("campus")
    search = request.args.get("search")
    status = request.args.get("status")
    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 50)), 200)

    result = models.list_children(campus=campus, search=search, status=status,
                                   page=page, page_size=page_size)
    return jsonify(result)


@nutrition_bp.route("/children/<int:child_id>", methods=["GET"])
def get_child(child_id):
    err = _check_perm("children:read")
    if err:
        return err

    child = models.get_child(child_id)
    if not child:
        return jsonify({"error": "儿童记录不存在"}), 404

    _log("READ", "child", child_id, f"查看儿童 {child.get('child_code')}")
    return jsonify(child)


@nutrition_bp.route("/children", methods=["POST"])
def create_child():
    err = _check_perm("children:write")
    if err:
        return err

    data = request.get_json(silent=True) or {}
    try:
        child = models.create_child(data)
        _log("CREATE", "child", child["id"], f"创建儿童 {child['child_code']}")
        return jsonify(child), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@nutrition_bp.route("/children/<int:child_id>", methods=["PUT"])
def update_child(child_id):
    err = _check_perm("children:write")
    if err:
        return err

    data = request.get_json(silent=True) or {}
    child = models.update_child(child_id, data)
    if not child:
        return jsonify({"error": "儿童记录不存在"}), 404
    _log("UPDATE", "child", child_id, f"更新儿童 {child.get('child_code')}")
    return jsonify(child)


@nutrition_bp.route("/children/<int:child_id>", methods=["DELETE"])
def delete_child(child_id):
    err = _check_perm("children:delete")
    if err:
        return err

    ok = models.delete_child(child_id)
    if not ok:
        return jsonify({"error": "儿童记录不存在"}), 404
    _log("DELETE", "child", child_id, "删除儿童记录")
    return jsonify({"message": "已删除"}), 200


@nutrition_bp.route("/children/import", methods=["POST"])
def import_children():
    err = _check_perm("children:write")
    if err:
        return err

    if "file" not in request.files:
        return jsonify({"error": "请上传文件"}), 400

    file = request.files["file"]
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "csv"

    content = file.read()
    children_data, errors = parse_import_data(content, ext)

    imported = 0
    skipped = 0
    import_errors = errors[:]

    for child_data in children_data:
        try:
            # 检查重复
            code = child_data.get("child_code")
            if code:
                existing = models.get_child_by_code(code)
                if existing:
                    skipped += 1
                    import_errors.append(f"编号 {code} 已存在，跳过")
                    continue
            models.create_child(child_data)
            imported += 1
        except Exception as e:
            import_errors.append(f"导入 {child_data.get('display_name', child_data.get('child_code', 'unknown'))} 失败: {e}")

    _log("CREATE", "child", "batch", f"批量导入：成功 {imported}，跳过 {skipped}，错误 {len(import_errors)}")

    return jsonify({
        "imported": imported,
        "skipped": skipped,
        "errors": import_errors,
    }), 200


@nutrition_bp.route("/children/export", methods=["GET"])
def export_children():
    err = _check_perm("children:export")
    if err:
        return err

    result = models.list_children(page=1, page_size=10000)
    csv_data = _children_to_csv(result["items"])
    _log("EXPORT", "child", "batch", f"导出 {len(result['items'])} 条儿童记录")

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=children_{date.today().isoformat()}.csv"}
    )


@nutrition_bp.route("/children/anomalies", methods=["GET"])
def check_anomalies():
    err = _check_perm("children:read")
    if err:
        return err

    result = models.list_children(page=1, page_size=10000)
    anomalies = []
    for child in result["items"]:
        warnings = engine.check_anomalies(child)
        data_valid, data_issues = engine.validate_child_data(child)
        all_issues = warnings[:]
        if not data_valid:
            all_issues.append(f"数据不完整: {data_issues}")
        if all_issues:
            anomalies.append({
                "child_code": child["child_code"],
                "display_name": child.get("display_name", ""),
                "issues": all_issues,
            })

    return jsonify({
        "total_children": result["total"],
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    })


@nutrition_bp.route("/children/template", methods=["GET"])
def download_template():
    csv_data = generate_import_template()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=import_template.csv"}
    )


# ============================================================
# 套餐管理
# ============================================================

@nutrition_bp.route("/meal-plans", methods=["GET"])
def list_meal_plans():
    err = _check_perm("meal_plans:read")
    if err:
        return err

    plan_date = request.args.get("plan_date")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))

    result = models.list_meal_plans(plan_date=plan_date, page=page, page_size=page_size)
    return jsonify(result)


@nutrition_bp.route("/meal-plans/<int:plan_id>", methods=["GET"])
def get_meal_plan(plan_id):
    err = _check_perm("meal_plans:read")
    if err:
        return err

    plan = models.get_meal_plan(plan_id)
    if not plan:
        return jsonify({"error": "套餐不存在"}), 404
    return jsonify(plan)


@nutrition_bp.route("/meal-plans", methods=["POST"])
def create_meal_plan():
    err = _check_perm("meal_plans:write")
    if err:
        return err

    data = request.get_json(silent=True) or {}
    try:
        plan = models.upsert_meal_plan(data)
        _log("CREATE", "meal_plan", plan.get("id", ""),
             f"录入 {data.get('plan_date')} {data.get('plan_type')}餐")
        return jsonify(plan), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@nutrition_bp.route("/meal-plans/<int:plan_id>", methods=["DELETE"])
def delete_meal_plan(plan_id):
    err = _check_perm("meal_plans:write")
    if err:
        return err

    ok = models.delete_meal_plan(plan_id)
    if not ok:
        return jsonify({"error": "套餐不存在"}), 404
    return jsonify({"message": "已删除"})


@nutrition_bp.route("/meal-plans/batch", methods=["POST"])
def batch_create_meal_plans():
    """批量录入 A+B 餐"""
    err = _check_perm("meal_plans:write")
    if err:
        return err

    data = request.get_json(silent=True) or {}
    plan_date = data.get("plan_date")
    meal_a = data.get("meal_a", {})
    meal_b = data.get("meal_b", {})

    if not plan_date:
        return jsonify({"error": "缺少日期"}), 400

    results = []
    for meal_data, plan_type in [(meal_a, "A"), (meal_b, "B")]:
        meal_data["plan_date"] = plan_date
        meal_data["plan_type"] = plan_type
        # 将逗号分隔的字符串转为列表
        for field in ["ingredients", "allergens", "suitable_tags"]:
            val = meal_data.get(field)
            if isinstance(val, str):
                meal_data[field] = [s.strip() for s in val.split(",") if s.strip()] if val else []
        try:
            plan = models.upsert_meal_plan(meal_data)
            results.append(plan)
        except Exception as e:
            return jsonify({"error": f"{plan_type}餐录入失败: {e}"}), 400

    _log("CREATE", "meal_plan", "batch", f"批量录入 {plan_date} A+B餐")
    return jsonify({"plan_date": plan_date, "meals": results}), 201


@nutrition_bp.route("/meal-plans/by-date/<plan_date>", methods=["GET"])
def get_meals_by_date(plan_date):
    err = _check_perm("meal_plans:read")
    if err:
        return err

    meals = models.get_meals_by_date(plan_date)
    return jsonify({"plan_date": plan_date, "meals": meals})


# ============================================================
# 营养规则
# ============================================================

@nutrition_bp.route("/rules", methods=["GET"])
def list_rules():
    err = _check_perm("rules:read")
    if err:
        return err

    rules = models.list_rules()
    return jsonify({"rules": rules, "active_rule_id": next((r["id"] for r in rules if r.get("is_active")), None)})


@nutrition_bp.route("/rules", methods=["POST"])
def create_rule():
    err = _check_perm("rules:write")
    if err:
        return err

    data = request.get_json(silent=True) or {}
    try:
        rule = models.create_rule(data)
        _log("CREATE", "rule", rule["id"], f"创建规则 {rule['version']}")
        return jsonify(rule), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@nutrition_bp.route("/rules/<int:rule_id>/activate", methods=["POST"])
def activate_rule(rule_id):
    err = _check_perm("rules:write")
    if err:
        return err

    rule = models.activate_rule(rule_id)
    if not rule:
        return jsonify({"error": "规则不存在"}), 404
    _log("UPDATE", "rule", rule_id, f"激活规则 {rule['version']}")
    return jsonify(rule)


# ============================================================
# 推荐引擎
# ============================================================

@nutrition_bp.route("/recommend", methods=["POST"])
def run_recommendation():
    """对指定日期执行全量推荐"""
    err = _check_perm("recommend:execute")
    if err:
        return err

    data = request.get_json(silent=True) or {}
    plan_date = data.get("plan_date", date.today().isoformat())

    # 获取当日套餐
    meals = models.get_meals_by_date(plan_date)
    if len(meals) < 2:
        return jsonify({
            "error": f"{plan_date} 的A/B套餐未配置完整（当前有 {len(meals)} 个套餐，需要2个）",
            "code": "MEALS_INCOMPLETE"
        }), 400

    meal_a = next((m for m in meals if m["plan_type"] == "A"), None)
    meal_b = next((m for m in meals if m["plan_type"] == "B"), None)
    if not meal_a or not meal_b:
        return jsonify({"error": "A/B餐不完整"}), 400

    # 校验套餐数据
    for meal, label in [(meal_a, "A"), (meal_b, "B")]:
        valid, msg = engine.validate_meal_data(meal)
        if not valid:
            return jsonify({"error": f"{label}餐数据不完整: {msg}"}), 400

    # 获取活跃规则
    rule = models.get_active_rule()
    if not rule:
        return jsonify({"error": "没有激活的营养规则", "code": "NO_ACTIVE_RULE"}), 400

    # 获取所有儿童
    children_result = models.list_children(page=1, page_size=10000)
    children = children_result["items"]

    if not children:
        return jsonify({"error": "没有儿童数据"}), 400

    # 执行批量推荐
    try:
        results = engine.batch_recommend(children, meal_a, meal_b, rule)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"推荐引擎异常: {e}"}), 500

    # 保存结果
    saved_count = 0
    save_errors = []
    for r in results:
        if r.get("child_id"):
            try:
                models.save_recommendations([{
                    "child_id": r["child_id"],
                    "plan_date": plan_date,
                    "rule_version": r.get("rule_version", rule.get("version", "")),
                    "score_a": r.get("score_a", 0),
                    "score_b": r.get("score_b", 0),
                    "recommended_plan": r.get("recommended_plan", "MANUAL"),
                    "reason": r.get("reason", ""),
                    "exclusion_reason": r.get("exclusion_reason", ""),
                    "risk_notes": r.get("risk_notes", ""),
                }])
                saved_count += 1
            except Exception as e:
                save_errors.append(f"{r.get('child_code')}: {e}")

    # 统计
    stats = models.get_recommendation_stats(plan_date)
    _log("EXECUTE", "recommend", "batch",
         f"{plan_date} 推荐完成：{saved_count}条，A={stats['a_count']} B={stats['b_count']} MANUAL={stats['manual_count']}")

    return jsonify({
        "plan_date": plan_date,
        "rule_version": rule.get("version", "unknown"),
        "stats": stats,
        "saved": saved_count,
        "save_errors": save_errors,
    }), 200


@nutrition_bp.route("/recommendations", methods=["GET"])
def list_recommendations():
    err = _check_recommend_read()
    if err:
        return err

    plan_date = request.args.get("plan_date")
    confirmed = request.args.get("confirmed")
    recommended_plan = request.args.get("recommended_plan")
    campus = request.args.get("campus")
    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 50)), 200)

    child_code = _get_bound_child_code() if _get_role() == "parent" else None
    result = models.list_recommendations(
        plan_date=plan_date, confirmed=confirmed,
        recommended_plan=recommended_plan, campus=campus,
        child_code=child_code or None,
        page=page, page_size=page_size
    )
    if _get_role() == "parent" and not child_code:
        return jsonify({"total": 0, "page": page, "page_size": page_size, "items": []})
    return jsonify(result)


@nutrition_bp.route("/recommendations/<int:rec_id>", methods=["GET"])
def get_recommendation(rec_id):
    err = _check_recommend_read()
    if err:
        return err

    conn = models.get_db()
    params = {"id": rec_id}
    own_scope = ""
    if _get_role() == "parent":
        child_code = _get_bound_child_code()
        if not child_code:
            conn.close()
            return jsonify({"error": "推荐记录不存在"}), 404
        own_scope = " AND nc.child_code = :child_code"
        params["child_code"] = child_code
    row = conn.execute(
        f"""SELECT nr.*, nc.child_code, nc.display_name, nc.age, nc.gender,
                  nc.height_cm, nc.weight_kg, nc.bmi, nc.data_status, nc.campus
           FROM nutrition_recommendations nr
           JOIN nutrition_children nc ON nr.child_id = nc.id
           WHERE nr.id = :id{own_scope}""",
        params
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "推荐记录不存在"}), 404
    return jsonify(models._row_to_dict(row))


@nutrition_bp.route("/recommendations/<int:rec_id>/confirm", methods=["POST"])
def confirm_recommendation(rec_id):
    err = _check_perm("recommend:confirm")
    if err:
        return err

    data = request.get_json(silent=True) or {}
    operator = data.get("operator", _get_role())
    result = models.confirm_recommendation(rec_id, operator)
    if not result:
        return jsonify({"error": "推荐记录不存在"}), 404

    _log("UPDATE", "recommend", rec_id, f"确认推荐 {result.get('recommended_plan')} 餐")
    return jsonify(result)


@nutrition_bp.route("/recommendations/export", methods=["GET"])
def export_recommendations():
    err = _check_perm("recommend:export")
    if err:
        return err

    plan_date = request.args.get("plan_date")
    format_type = request.args.get("format", "csv")

    result = models.list_recommendations(plan_date=plan_date, page=1, page_size=10000)

    _log("EXPORT", "recommend", "batch", f"导出 {plan_date} 推荐结果")

    if format_type == "json":
        data = export_to_json(result["items"])
        return Response(data, mimetype="application/json",
                        headers={"Content-Disposition": f"attachment; filename=recommendations_{plan_date}.json"})
    else:
        data = export_to_csv(result["items"], include_sensitive=True)
        return Response(data, mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=recommendations_{plan_date}.csv"})


@nutrition_bp.route("/recommendations/stats", methods=["GET"])
def recommendation_stats():
    err = _check_recommend_read()
    if err:
        return err

    plan_date = request.args.get("plan_date", date.today().isoformat())
    if _get_role() == "parent":
        child_code = _get_bound_child_code()
        own = models.list_recommendations(
            plan_date=plan_date, child_code=child_code or None,
            page=1, page_size=10000
        )["items"] if child_code else []
        return jsonify({
            "plan_date": plan_date,
            "total": len(own),
            "a_count": sum(item.get("recommended_plan") == "A" for item in own),
            "b_count": sum(item.get("recommended_plan") == "B" for item in own),
            "manual_count": sum(item.get("recommended_plan") == "MANUAL" for item in own),
            "confirmed_count": sum(bool(item.get("confirmed")) for item in own),
        })
    stats = models.get_recommendation_stats(plan_date)
    return jsonify(stats)


# ============================================================
# 审计日志
# ============================================================

@nutrition_bp.route("/audit-logs", methods=["GET"])
def list_audit_logs():
    err = _check_perm("audit:read")
    if err:
        return err

    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 50)), 200)
    target_type = request.args.get("target_type")
    action = request.args.get("action")
    operator = request.args.get("operator")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    result = models.list_audit_logs(
        page=page, page_size=page_size,
        target_type=target_type, action=action,
        operator=operator, date_from=date_from, date_to=date_to
    )
    return jsonify(result)


# ============================================================
# 健康检查
# ============================================================

@nutrition_bp.route("/health", methods=["GET"])
def health_check():
    try:
        conn = models.get_db()
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False

    active_rule = models.get_active_rule()
    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "active_rule": active_rule["version"] if active_rule else None,
    })


# ============================================================
# 辅助函数
# ============================================================

def _children_to_csv(children: list) -> str:
    import io, csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["儿童编号", "姓名", "年龄", "性别", "身高(cm)", "体重(kg)", "BMI", "过敏信息", "忌口", "特殊需求", "医生备注", "校区", "数据状态"])
    for c in children:
        allergies = c.get("allergies", "[]")
        if isinstance(allergies, str) and allergies.startswith("["):
            try:
                allergies = ", ".join(json.loads(allergies))
            except:
                pass
        restrictions = c.get("dietary_restrictions", "[]")
        if isinstance(restrictions, str) and restrictions.startswith("["):
            try:
                restrictions = ", ".join(json.loads(restrictions))
            except:
                pass
        special = c.get("special_needs", "[]")
        if isinstance(special, str) and special.startswith("["):
            try:
                special = ", ".join(json.loads(special))
            except:
                pass
        writer.writerow([
            c.get("child_code", ""), c.get("display_name", ""),
            c.get("age", ""), c.get("gender", ""),
            c.get("height_cm", ""), c.get("weight_kg", ""), c.get("bmi", ""),
            allergies, restrictions, special,
            c.get("doctor_notes", ""), c.get("campus", ""), c.get("data_status", ""),
        ])
    return output.getvalue()


# ============================================================
# Flask 应用工厂
# ============================================================

def init_app(app):
    """将蓝图注册到现有 Flask 应用"""
    models.init_db()
    app.register_blueprint(nutrition_bp)
    return app
