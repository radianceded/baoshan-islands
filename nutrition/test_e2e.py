"""
自测脚本 — 通过 API 完整走一遍推荐流程

用法:
    1. 先启动服务器: /tmp/nutrition-venv/bin/python test_app.py
    2. 再开另一个终端运行: /tmp/nutrition-venv/bin/python test_e2e.py

或者直接独立运行（不走 Web）：
    /tmp/nutrition-venv/bin/python test_e2e.py --standalone
"""

import sys, os, json, urllib.request, urllib.error, urllib
from datetime import date, timedelta

API = "http://localhost:5000/api/nutrition"
TODAY = date.today().isoformat()
PASS = 0
FAIL = 0


def api(method, path, body=None):
    """调用 API"""
    url = API + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-User-Role", "admin")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        try:
            return e.code, json.loads(body_text)
        except:
            return e.code, {"error": body_text}
    except Exception as e:
        return 0, {"error": str(e)}


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  {detail}")


# ============================================================
# 独立引擎测试（不走 Web）
# ============================================================
def standalone_tests():
    print("\n" + "=" * 60)
    print("🧪 引擎单元测试（独立运行）")
    print("=" * 60)
    from engine import recommend, batch_recommend, validate_child_data, validate_meal_data, calculate_bmi

    # 1. 过敏排除
    print("\n📋 场景1: A餐含牛奶过敏原 → 推荐B餐")
    child = {"child_code": "T01", "age": 9, "gender": "男", "height_cm": 135,
             "weight_kg": 30, "allergies": ["牛奶"], "dietary_restrictions": [], "special_needs": []}
    meal_a = {"plan_type": "A", "calories_kcal": 650, "protein_g": 28, "fat_g": 18,
              "carbs_g": 80, "sugar_g": 8, "sodium_mg": 600, "fiber_g": 5,
              "allergens": ["牛奶", "鸡蛋"], "ingredients": ["米饭", "鸡肉", "牛奶"],
              "suitable_tags": [], "unsuitable_notes": ""}
    meal_b = {"plan_type": "B", "calories_kcal": 580, "protein_g": 32, "fat_g": 14,
              "carbs_g": 75, "sugar_g": 5, "sodium_mg": 450, "fiber_g": 6,
              "allergens": ["鸡蛋"], "ingredients": ["米饭", "鱼肉", "西兰花"],
              "suitable_tags": [], "unsuitable_notes": ""}
    rule = {"version": "v1.0-demo", "weight_calorie": 0.25, "weight_protein": 0.20,
            "weight_sugar": 0.15, "weight_sodium": 0.15, "weight_fat": 0.10,
            "weight_fiber": 0.10, "weight_special": 0.05,
            "calorie_range_config": '{"7-10":[1600,2000]}',
            "protein_min_config": '{"7-10":30}',
            "sugar_max_config": '{"7-10":30}',
            "sodium_max_config": '{"7-10":1500}',
            "fat_range_config": '{"7-10":[40,65]}',
            "fiber_min_config": '{"7-10":14}'}

    r = recommend(child, meal_a, meal_b, rule)
    check("推荐B餐", r["recommended_plan"] == "B")
    check("A餐得分为0", r["score_a"] == 0.0)
    check("B餐得分>0", r["score_b"] > 0)
    check("原因包含「牛奶」", "牛奶" in r["reason"])

    # 2. 两餐都排除
    print("\n📋 场景2: A含牛奶 B含花生，儿童两种都过敏 → 人工处理")
    child["allergies"] = ["牛奶", "花生"]
    meal_b["allergens"] = ["花生"]
    r = recommend(child, meal_a, meal_b, rule)
    check("推荐MANUAL", r["recommended_plan"] == "MANUAL")
    check("原因包含「人工处理」", "人工处理" in r["reason"])

    # 3. 素食忌口
    print("\n📋 场景3: 素食儿童，A含牛肉 → 排除A，推荐B")
    child["allergies"] = []
    child["dietary_restrictions"] = ["素食"]
    meal_a["ingredients"] = ["米饭", "牛肉", "青菜"]
    meal_a["allergens"] = []
    meal_b["allergens"] = []
    meal_b["ingredients"] = ["米饭", "豆腐", "青菜"]
    r = recommend(child, meal_a, meal_b, rule)
    check("推荐B餐", r["recommended_plan"] == "B")
    check("排除原因含「素食」", "素食" in (r["exclusion_reason"] + r["reason"]))

    # 4. 数据缺失
    print("\n📋 场景4: 儿童年龄/身高缺失 → 不自动推荐")
    child2 = {"child_code": "T04", "age": None, "gender": "男", "height_cm": None,
              "weight_kg": 30, "allergies": [], "dietary_restrictions": [], "special_needs": []}
    valid, issues = validate_child_data(child2)
    check("验证不通过", not valid)
    check("提示缺失信息", "年龄" in issues)

    # 5. BMI计算
    print("\n📋 场景5: BMI自动计算")
    bmi = calculate_bmi(135, 30)
    check("BMI=16.46", abs(bmi - 16.46) < 0.1, f"got {bmi}")
    check("空身高返回None", calculate_bmi(None, 50) is None)

    # 6. 异常检测
    print("\n📋 场景6: 异常数据检测")
    from engine import check_anomalies
    warnings = check_anomalies({"bmi": 11.0, "height_cm": 135, "age": 9})
    check("检测到BMI偏低", len(warnings) > 0)
    warnings = check_anomalies({"bmi": 18.0, "height_cm": 135, "age": 9})
    check("正常BMI无警告", len(warnings) == 0)

    # 7. 批量推荐（使用独立的 fresh meal 对象，因为前面的场景修改了 meal_a/allergens）
    print("\n📋 场景7: 批量推荐（3个儿童，不同情况）")
    fresh_a = {"plan_type": "A", "calories_kcal": 650, "protein_g": 28, "fat_g": 18,
               "carbs_g": 80, "sugar_g": 8, "sodium_mg": 600, "fiber_g": 5,
               "allergens": ["牛奶", "鸡蛋"], "ingredients": ["米饭", "鸡肉", "牛奶"],
               "suitable_tags": [], "unsuitable_notes": ""}
    fresh_b = {"plan_type": "B", "calories_kcal": 580, "protein_g": 32, "fat_g": 14,
               "carbs_g": 75, "sugar_g": 5, "sodium_mg": 450, "fiber_g": 6,
               "allergens": [], "ingredients": ["米饭", "鱼肉", "西兰花"],
               "suitable_tags": [], "unsuitable_notes": ""}
    children = [
        {"id": 1, "child_code": "T01", "age": 8, "gender": "男", "height_cm": 130,
         "weight_kg": 28, "allergies": ["牛奶"], "dietary_restrictions": [], "special_needs": []},
        {"id": 2, "child_code": "T02", "age": 10, "gender": "女", "height_cm": 140,
         "weight_kg": 32, "allergies": [], "dietary_restrictions": ["清真"], "special_needs": []},
        {"id": 3, "child_code": "T03", "age": None, "gender": "", "height_cm": None,
         "weight_kg": None, "allergies": [], "dietary_restrictions": [], "special_needs": []},
    ]
    results = batch_recommend(children, fresh_a, fresh_b, rule)
    check("返回3条结果", len(results) == 3)
    # T01: 牛奶过敏，A含牛奶→B
    check("T01推荐B", results[0]["recommended_plan"] == "B")
    # T03: 数据缺失→MANUAL
    check("T03需人工处理", results[2]["recommended_plan"] == "MANUAL")


# ============================================================
# Web API 端到端测试
# ============================================================
def web_tests():
    print("\n" + "=" * 60)
    print("🌐 API 端到端测试（需先启动服务器）")
    print("=" * 60)

    # 健康检查
    print("\n📋 1. 健康检查")
    status, data = api("GET", "/health")
    check("健康检查成功", status == 200 and data.get("status") in ("ok", "degraded"))

    # 获取活跃规则
    print("\n📋 2. 获取活跃规则")
    status, data = api("GET", "/rules")
    check("规则列表返回", status == 200)
    rule = next((r for r in data.get("rules", []) if r.get("is_active")), None)
    check("有活跃规则", rule is not None)

    # 添加测试儿童
    print("\n📋 3. 添加测试儿童")
    test_children = [
        {"display_name": "测试生A", "age": 8, "gender": "男", "height_cm": 130,
         "weight_kg": 28, "allergies": ["牛奶"], "campus": "本部"},
        {"display_name": "测试生B", "age": 10, "gender": "女", "height_cm": 140,
         "weight_kg": 35, "allergies": ["花生"], "dietary_restrictions": ["清真"],
         "campus": "宝林"},
        {"display_name": "测试生C", "age": 7, "gender": "男", "height_cm": 122,
         "weight_kg": 24, "allergies": [], "special_needs": ["低糖", "低盐"],
         "campus": "本部"},
        {"display_name": "测试生D", "age": 12, "gender": "女", "height_cm": 155,
         "weight_kg": 48, "allergies": ["虾", "蟹"], "campus": "罗泾"},
    ]
    created_ids = []
    for c in test_children:
        status, data = api("POST", "/children", c)
        if status == 201:
            created_ids.append(data["id"])
            print(f"  ✅ 创建: {data['child_code']} (BMI={data.get('bmi')})")
        else:
            print(f"  ⚠️  {c['display_name']}: {data.get('error', status)}")

    check("至少创建1个儿童", len(created_ids) > 0)

    # 查看儿童列表
    print("\n📋 4. 查看儿童列表")
    status, data = api("GET", "/children?page=1&page_size=20")
    check("列表查询成功", status == 200)
    check("total>0", data.get("total", 0) > 0)

    # 异常检查
    print("\n📋 5. 异常数据检查")
    status, data = api("GET", "/children/anomalies")
    check("异常检查接口正常", status == 200)
    print(f"  📊 共 {data.get('anomaly_count', 0)} 条异常记录")

    # 录入当日套餐
    print("\n📋 6. 录入当日 A+B 套餐")
    batch_data = {
        "plan_date": TODAY,
        "meal_a": {
            "plan_name": "A餐-番茄炒蛋",
            "ingredients": ["米饭", "鸡蛋", "番茄", "牛奶"],
            "calories_kcal": 620, "protein_g": 25, "fat_g": 20,
            "carbs_g": 78, "sugar_g": 12, "sodium_mg": 550,
            "fiber_g": 4, "allergens": ["牛奶", "鸡蛋"],
            "suitable_tags": ["低盐"], "unsuitable_notes": ""
        },
        "meal_b": {
            "plan_name": "B餐-香菇鸡块",
            "ingredients": ["米饭", "鸡肉", "香菇", "青菜", "豆腐"],
            "calories_kcal": 580, "protein_g": 30, "fat_g": 15,
            "carbs_g": 73, "sugar_g": 5, "sodium_mg": 480,
            "fiber_g": 8, "allergens": ["大豆"],
            "suitable_tags": ["低糖", "低盐", "清真"], "unsuitable_notes": ""
        }
    }
    status, data = api("POST", "/meal-plans/batch", batch_data)
    check("A+B餐录入成功", status == 201, f"status={status}")

    # 执行推荐
    print("\n📋 7. 执行推荐 ← 核心流程")
    status, data = api("POST", "/recommend", {"plan_date": TODAY})
    check("推荐执行成功", status == 200, f"status={status} msg={data}")
    if status == 200:
        stats = data.get("stats", {})
        print(f"  📊 A餐={stats.get('a_count',0)} B餐={stats.get('b_count',0)} 人工={stats.get('manual_count',0)}")
        check("有推荐结果", stats.get("total", 0) > 0)

    # 查看推荐结果
    print("\n📋 8. 查看推荐结果")
    status, data = api("GET", f"/recommendations?plan_date={TODAY}")
    check("推荐结果查询成功", status == 200)
    if data.get("items"):
        for item in data["items"][:5]:
            plan_badge = {"A": "🅰️", "B": "🅱️", "MANUAL": "⚠️"}.get(item["recommended_plan"], "?")
            confirmed = "✅" if item.get("confirmed") else "⏳"
            print(f"  {plan_badge} {item['child_code']} → {item['recommended_plan']} (A={item['score_a']:.3f} B={item['score_b']:.3f}) {confirmed}")

    # 人工确认
    print("\n📋 9. 人工确认")
    if data.get("items"):
        to_confirm = [r for r in data["items"] if not r.get("confirmed")][:2]
        for rec in to_confirm:
            status, _ = api("POST", f"/recommendations/{rec['id']}/confirm",
                            {"operator": "admin"})
            check(f"确认 {rec['child_code']}", status == 200)
    else:
        print("  ⚠️  无可确认的记录")

    # 导出
    print("\n📋 10. 导出配餐名单")
    # CSV 导出返回 text/csv，不是 JSON，用 urllib 直接请求并检查状态码
    req = urllib.request.Request(
        f"{API}/recommendations/export?plan_date={TODAY}&format=csv")
    req.add_header("X-User-Role", "admin")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()[:500]
            check("CSV导出成功", resp.status == 200 and "儿童编号" in body)
    except Exception as e:
        check("CSV导出成功", False, str(e))

    # 审计日志
    print("\n📋 11. 审计日志")
    status, data = api("GET", "/audit-logs?page=1&page_size=10")
    check("审计日志查询成功", status == 200)
    print(f"  📊 共 {data.get('total', 0)} 条日志")


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    print("🍱 儿童营养餐智能分配系统 — 自动化测试")
    print("=" * 60)

    if "--standalone" in sys.argv:
        standalone_tests()
        print(f"\n{'=' * 60}")
        print(f"🏁 结果: {PASS} 通过, {FAIL} 失败, {PASS + FAIL} 总计")
    else:
        standalone_tests()
        web_tests()
        print(f"\n{'=' * 60}")
        print(f"🏁 结果: {PASS} 通过, {FAIL} 失败, {PASS + FAIL} 总计")
        if FAIL > 0:
            print("\n💡 提示: 如果 API 测试失败，请确认服务器已启动:")
            print("   /tmp/nutrition-venv/bin/python test_app.py")
