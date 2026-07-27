"""
独立测试服务器 + 权限集成测试 — 儿童营养餐智能分配系统
运行: python3 test_app.py --test   (仅运行测试)
      python3 test_app.py          (启动开发服务器)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, send_from_directory

try:
    from .routes import init_app as init_nutrition
except ImportError:
    from routes import init_app as init_nutrition

app = Flask(__name__, static_folder="static", static_url_path="/static")

# 注册营养餐模块
init_nutrition(app)

# 静态文件路由
@app.route("/nutrition/<path:filename>")
def serve_nutrition_static(filename):
    return send_from_directory("static", filename)

@app.route("/")
def index():
    return '<meta http-equiv="refresh" content="0;url=/nutrition/children.html">'


# ============================================================
# 权限集成测试
# ============================================================

def run_permission_tests():
    """使用 Flask test client 测试角色权限"""
    passed = 0
    failed = 0

    def t(client, role_headers, method, path, expect_status=200, label="", req_headers=None):
        nonlocal passed, failed
        import json as _json
        h = dict(role_headers)
        if req_headers:
            h.update(req_headers)
        fn = getattr(client, method.lower())
        resp = fn(path, headers=h)
        ok = resp.status_code == expect_status
        if ok:
            print(f"  ✅ {label or f'{method} {path}'}: {resp.status_code}")
            passed += 1
        else:
            print(f"  ❌ {label or f'{method} {path}'}: expected {expect_status}, got {resp.status_code}")
            try:
                print(f"     body: {_json.loads(resp.data)[:200]}")
            except:
                pass
            failed += 1
        return resp

    with app.test_client() as client:
        print("\n🔒 权限测试 — 角色访问控制")
        print("=" * 50)

        # ---- parent 角色 ----
        print("\n📋 parent 角色 (仅 recommend:read_own):")
        parent_headers = {"X-User-Role": "parent"}

        t(client, parent_headers, "GET", "/api/nutrition/children?page_size=1", 403,
          "parent GET /children → 403")
        t(client, parent_headers, "POST", "/api/nutrition/children",
          403, "parent POST /children → 403",
          req_headers={"Content-Type": "application/json"})
        t(client, parent_headers, "GET", "/api/nutrition/children/export",
          403, "parent GET /children/export → 403")
        t(client, parent_headers, "GET", "/api/nutrition/meal-plans",
          403, "parent GET /meal-plans → 403")
        t(client, parent_headers, "GET", "/api/nutrition/rules",
          403, "parent GET /rules → 403")
        t(client, parent_headers, "POST", "/api/nutrition/recommend",
          403, "parent POST /recommend → 403",
          req_headers={"Content-Type": "application/json"})
        t(client, parent_headers, "GET", "/api/nutrition/recommendations/export",
          403, "parent GET /recommendations/export → 403")
        t(client, parent_headers, "GET", "/api/nutrition/audit-logs",
          403, "parent GET /audit-logs → 403")

        # ---- teacher 角色 ----
        print("\n📋 teacher 角色:")
        teacher_headers = {"X-User-Role": "teacher"}

        t(client, teacher_headers, "GET", "/api/nutrition/children?page_size=1", 200,
          "teacher GET /children → 200")
        t(client, teacher_headers, "GET", "/api/nutrition/meal-plans", 200,
          "teacher GET /meal-plans → 200")
        t(client, teacher_headers, "GET", "/api/nutrition/healthy-check", 404,
          "teacher GET /health (404=wrong path, actual is /api/nutrition/health)")
        t(client, teacher_headers, "GET", "/api/nutrition/health", 200,
          "teacher GET /health → 200")
        # teacher 有导出权限
        t(client, teacher_headers, "GET", "/api/nutrition/children/export", 200,
          "teacher GET /children/export → 200")
        # teacher 不能写套餐
        t(client, teacher_headers, "POST", "/api/nutrition/meal-plans",
          403, "teacher POST /meal-plans → 403",
          req_headers={"Content-Type": "application/json"})
        # teacher 不能写规则
        t(client, teacher_headers, "POST", "/api/nutrition/rules",
          403, "teacher POST /rules → 403",
          req_headers={"Content-Type": "application/json"})
        # teacher 不能删除儿童
        t(client, teacher_headers, "DELETE", "/api/nutrition/children/9999",
          403, "teacher DELETE /children/9999 → 403")

        # ---- admin 角色 ----
        print("\n📋 admin 角色 (全权限):")
        admin_headers = {"X-User-Role": "admin"}

        t(client, admin_headers, "GET", "/api/nutrition/children?page_size=1", 200,
          "admin GET /children → 200")
        t(client, admin_headers, "GET", "/api/nutrition/meal-plans", 200,
          "admin GET /meal-plans → 200")
        t(client, admin_headers, "GET", "/api/nutrition/rules", 200,
          "admin GET /rules → 200")
        t(client, admin_headers, "GET", "/api/nutrition/audit-logs", 200,
          "admin GET /audit-logs → 200")
        t(client, admin_headers, "GET", "/api/nutrition/health", 200,
          "admin GET /health → 200")
        t(client, admin_headers, "DELETE", "/api/nutrition/children/9999",
          404, "admin DELETE /children/9999 → 404 (不存在，非 403)")

        # ---- nutritionist 角色 ----
        print("\n📋 nutritionist 角色:")
        nutr_headers = {"X-User-Role": "nutritionist"}

        t(client, nutr_headers, "GET", "/api/nutrition/children?page_size=1", 200,
          "nutritionist GET /children → 200")
        t(client, nutr_headers, "GET", "/api/nutrition/meal-plans", 200,
          "nutritionist GET /meal-plans → 200")
        t(client, nutr_headers, "GET", "/api/nutrition/rules", 200,
          "nutritionist GET /rules → 200")
        # nutritionist 不能执行推荐
        t(client, nutr_headers, "POST", "/api/nutrition/recommend",
          403, "nutritionist POST /recommend → 403",
          req_headers={"Content-Type": "application/json"})
        # nutritionist 不能导出
        t(client, nutr_headers, "GET", "/api/nutrition/recommendations/export",
          403, "nutritionist GET /recommendations/export → 403")
        # nutritionist 不能写/删儿童
        t(client, nutr_headers, "POST", "/api/nutrition/children",
          403, "nutritionist POST /children → 403",
          req_headers={"Content-Type": "application/json"})

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed+failed} total")
    if failed == 0:
        print("🎉 ALL PERMISSION TESTS PASSED!")
    else:
        print(f"⚠️  {failed} test(s) failed")
    return failed == 0


def fix_permission_test_header():
    """修复：Flask test client 的 headers 不传给 POST 的子调用"""
    pass


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    if "--test" in sys.argv:
        ok = run_permission_tests()
        sys.exit(0 if ok else 1)
    else:
        print("\n🍱 儿童营养餐智能分配系统 — 测试服务器")
        print("=" * 52)
        print("访问地址: http://localhost:5000")
        print("儿童管理: http://localhost:5000/nutrition/children.html")
        print("套餐管理: http://localhost:5000/nutrition/meal-plans.html")
        print("规则配置: http://localhost:5000/nutrition/rules.html")
        print("智能推荐: http://localhost:5000/nutrition/recommendations.html")
        print("人工复核: http://localhost:5000/nutrition/review.html")
        print("历史记录: http://localhost:5000/nutrition/history.html")
        print("审计日志: http://localhost:5000/nutrition/audit-logs.html")
        print("=" * 52 + "\n")
        app.run(host="0.0.0.0", port=5000, debug=True)
