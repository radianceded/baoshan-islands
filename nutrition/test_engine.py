"""
推荐引擎单元测试
"""

import json
import sys
import os

# 添加父目录到 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import (
    recommend, batch_recommend, validate_child_data, validate_meal_data,
    check_anomalies, calculate_bmi, check_allergen_exclusion,
    check_dietary_restriction_conflict, check_special_needs_compatibility,
    calculate_meal_score, _get_age_group, _normalize_allergen, _normalize_allergens
)


# ============================================================
# 测试数据准备
# ============================================================

def make_child(**overrides):
    """创建测试用儿童数据"""
    base = {
        "id": 1,
        "child_code": "NC_0001",
        "display_name": "测试儿童01",
        "age": 9,
        "gender": "男",
        "height_cm": 135.0,
        "weight_kg": 30.0,
        "bmi": 16.46,
        "allergies": [],
        "dietary_restrictions": [],
        "special_needs": [],
        "doctor_notes": "",
    }
    base.update(overrides)
    return base


def make_meal(plan_type="A", **overrides):
    """创建测试用套餐数据"""
    base = {
        "plan_type": plan_type,
        "plan_name": f"{plan_type}餐",
        "ingredients": ["米饭", "鸡肉", "青菜", "豆腐"],
        "calories_kcal": 650.0,
        "protein_g": 28.0,
        "fat_g": 18.0,
        "carbs_g": 80.0,
        "sugar_g": 8.0,
        "sodium_mg": 600.0,
        "fiber_g": 5.0,
        "allergens": [],
        "suitable_tags": ["低糖", "低盐"],
        "unsuitable_notes": "",
    }
    base.update(overrides)
    return base


def make_rule(**overrides):
    """创建测试用营养规则"""
    base = {
        "version": "test-v1.0",
        "name": "测试规则",
        "weight_calorie": 0.25,
        "weight_protein": 0.20,
        "weight_sugar": 0.15,
        "weight_sodium": 0.15,
        "weight_fat": 0.10,
        "weight_fiber": 0.10,
        "weight_special": 0.05,
        "calorie_range_config": json.dumps({
            "3-6": [1200, 1600],
            "7-10": [1600, 2000],
            "11-13": [2000, 2400],
            "14-17": [2200, 2800],
        }),
        "protein_min_config": json.dumps({
            "3-6": 20, "7-10": 30, "11-13": 40, "14-17": 55,
        }),
        "sugar_max_config": json.dumps({
            "3-6": 25, "7-10": 30, "11-13": 35, "14-17": 40,
        }),
        "sodium_max_config": json.dumps({
            "3-6": 1200, "7-10": 1500, "11-13": 1800, "14-17": 2000,
        }),
        "fat_range_config": json.dumps({
            "3-6": [30, 50], "7-10": [40, 65], "11-13": [50, 75], "14-17": [60, 90],
        }),
        "fiber_min_config": json.dumps({
            "3-6": 10, "7-10": 14, "11-13": 18, "14-17": 22,
        }),
    }
    base.update(overrides)
    return base


# ============================================================
# 测试用例
# ============================================================

def test_a_has_allergen_choose_b():
    """A餐含过敏原时选择B餐"""
    child = make_child(allergies=["牛奶", "花生"])
    meal_a = make_meal("A", allergens=["牛奶", "鸡蛋"])
    meal_b = make_meal("B", allergens=["鸡蛋"])
    rule = make_rule()

    result = recommend(child, meal_a, meal_b, rule)

    assert result["recommended_plan"] == "B", f"Expected B, got {result['recommended_plan']}"
    assert result["score_a"] == 0.0, "A score should be 0 (excluded)"
    assert result["score_b"] > 0, "B should have a score"
    assert "牛奶" in result["reason"], f"Reason should mention milk: {result['reason']}"
    print("✅ test_a_has_allergen_choose_b PASSED")


def test_b_has_allergen_choose_a():
    """B餐含过敏原时选择A餐"""
    child = make_child(allergies=["虾"])
    meal_a = make_meal("A", allergens=["鸡蛋"])
    meal_b = make_meal("B", allergens=["虾", "蟹"])

    result = recommend(child, meal_a, meal_b, make_rule())

    assert result["recommended_plan"] == "A", f"Expected A, got {result['recommended_plan']}"
    assert result["score_b"] == 0.0
    assert result["score_a"] > 0
    print("✅ test_b_has_allergen_choose_a PASSED")


def test_both_have_allergen_manual():
    """两餐都含过敏原时转人工处理"""
    child = make_child(allergies=["牛奶", "花生"])
    meal_a = make_meal("A", allergens=["牛奶"])
    meal_b = make_meal("B", allergens=["花生"])

    result = recommend(child, meal_a, meal_b, make_rule())

    assert result["recommended_plan"] == "MANUAL", f"Expected MANUAL, got {result['recommended_plan']}"
    assert "人工处理" in result["reason"]
    print("✅ test_both_have_allergen_manual PASSED")


def test_missing_data_no_recommend():
    """身体数据缺失时不自动推荐"""
    child = make_child(age=None, height_cm=None)
    meal_a = make_meal("A")
    meal_b = make_meal("B")

    valid, issues = validate_child_data(child)
    assert not valid, "Should be invalid with missing age/height"
    print("✅ test_missing_data_no_recommend PASSED")


def test_equal_scores_tiebreaker():
    """两餐得分相同时执行预设规则"""
    child = make_child()
    # 创建两个完全相同的套餐
    meal_a = make_meal("A", calories_kcal=650, protein_g=28, fat_g=18,
                       sugar_g=8, sodium_mg=600, fiber_g=5)
    meal_b = make_meal("B", calories_kcal=650, protein_g=28, fat_g=18,
                       sugar_g=8, sodium_mg=600, fiber_g=5)

    result = recommend(child, meal_a, meal_b, make_rule())

    assert result["score_a"] == result["score_b"], f"Scores should be equal: {result['score_a']} vs {result['score_b']}"
    assert result["recommended_plan"] in ("A", "B")
    assert "得分相同" in result["reason"] or "得分完全相同" in result.get("risk_notes", "")
    print("✅ test_equal_scores_tiebreaker PASSED")


def test_weight_change_affects_score():
    """权重修改后评分结果正确变化"""
    child = make_child()

    # A餐热量更优但蛋白质不足
    meal_a = make_meal("A", calories_kcal=1700, protein_g=15)  # 热量好，蛋白质差
    meal_b = make_meal("B", calories_kcal=2200, protein_g=45)  # 热量差，蛋白质好

    # 默认权重（热量25%，蛋白质20%）
    rule1 = make_rule(version="test-v1")
    result1 = recommend(child, meal_a, meal_b, rule1)

    # 提高蛋白质权重，降低热量权重
    rule2 = make_rule(version="test-v2",
                      weight_calorie=0.05, weight_protein=0.50,
                      weight_sugar=0.10, weight_sodium=0.10,
                      weight_fat=0.10, weight_fiber=0.10, weight_special=0.05)
    result2 = recommend(child, meal_a, meal_b, rule2)

    # 两个结果应该不同（权重变化会导致评分不同）
    print(f"  Rule1: A={result1['score_a']}, B={result1['score_b']}, winner={result1['recommended_plan']}")
    print(f"  Rule2: A={result2['score_a']}, B={result2['score_b']}, winner={result2['recommended_plan']}")
    # 至少分数应该不同
    assert result1["score_a"] != result2["score_a"] or result1["score_b"] != result2["score_b"], \
        "Scores should change with different weights"
    print("✅ test_weight_change_affects_score PASSED")


def test_dietary_restriction_vegetarian():
    """素食忌口排除含肉套餐"""
    child = make_child(dietary_restrictions=["素食"])
    meal_a = make_meal("A", ingredients=["米饭", "牛肉", "青菜"])  # 含牛肉
    meal_b = make_meal("B", ingredients=["米饭", "豆腐", "青菜"])  # 全素

    result = recommend(child, meal_a, meal_b, make_rule())

    assert result["recommended_plan"] == "B", f"Expected B for vegetarian, got {result['recommended_plan']}"
    assert "素食" in result["exclusion_reason"] or "素食" in result["reason"]
    print("✅ test_dietary_restriction_vegetarian PASSED")


def test_special_needs_low_sugar():
    """低糖需求选择含低糖标签的套餐"""
    child = make_child(special_needs=["低糖", "低脂"])
    meal_a = make_meal("A", suitable_tags=["低盐"])  # 不含低糖
    meal_b = make_meal("B", suitable_tags=["低糖", "低脂", "高蛋白"])  # 含低糖低脂

    result = recommend(child, meal_a, meal_b, make_rule())

    # A应被排除（不满足低糖需求），B应被推荐
    assert result["recommended_plan"] == "B", f"Expected B, got {result['recommended_plan']}"
    print("✅ test_special_needs_low_sugar PASSED")


def test_calculate_bmi():
    """BMI计算正确"""
    bmi = calculate_bmi(135, 30)
    assert bmi is not None
    assert abs(bmi - 16.46) < 0.1, f"BMI should be ~16.46, got {bmi}"

    bmi2 = calculate_bmi(170, 65)
    assert bmi2 is not None
    assert abs(bmi2 - 22.49) < 0.1, f"BMI should be ~22.49, got {bmi2}"

    assert calculate_bmi(0, 50) is None
    assert calculate_bmi(170, 0) is None
    assert calculate_bmi(None, 50) is None
    print("✅ test_calculate_bmi PASSED")


def test_validate_meal_data():
    """套餐数据验证"""
    valid_meal = make_meal("A")
    valid, msg = validate_meal_data(valid_meal)
    assert valid, f"Should be valid: {msg}"

    invalid_meal = make_meal("A", calories_kcal=None, protein_g=None, sugar_g=-5)
    valid, msg = validate_meal_data(invalid_meal)
    assert not valid, f"Should be invalid"
    print("✅ test_validate_meal_data PASSED")


def test_anomaly_detection():
    """异常数据检测"""
    # BMI异常
    warnings = check_anomalies(make_child(bmi=11.5))
    assert len(warnings) > 0, "Should detect low BMI"

    warnings = check_anomalies(make_child(bmi=28.0))
    assert len(warnings) > 0, "Should detect high BMI"

    # 正常BMI
    warnings = check_anomalies(make_child(bmi=18.0))
    assert len(warnings) == 0, "Normal BMI should not warn"
    print("✅ test_anomaly_detection PASSED")


def test_age_group():
    """年龄段分组"""
    assert _get_age_group(4) == "3-6"
    assert _get_age_group(8) == "7-10"
    assert _get_age_group(12) == "11-13"
    assert _get_age_group(15) == "14-17"
    assert _get_age_group(None) == "7-10"  # default
    print("✅ test_age_group PASSED")


def test_special_needs_coverage_score():
    """特殊需求覆盖率评分"""
    child = make_child(special_needs=["低糖", "低盐", "素食"])
    meal_full = make_meal(suitable_tags=["低糖", "低盐", "素食"])
    score_full = calculate_meal_score(meal_full, child, make_rule())

    meal_partial = make_meal(suitable_tags=["低糖"])
    score_partial = calculate_meal_score(meal_partial, child, make_rule())

    assert score_full >= score_partial, \
        f"Full coverage ({score_full}) should >= partial ({score_partial})"
    print("✅ test_special_needs_coverage_score PASSED")


def test_batch_recommend():
    """批量推荐"""
    children = [
        make_child(child_code="NC_0001", allergies=["牛奶"]),
        make_child(child_code="NC_0002", allergies=["花生"]),
        make_child(child_code="NC_0003", allergies=[]),
        make_child(child_code="NC_0004", age=None, height_cm=None),  # 数据缺失
    ]
    meal_a = make_meal("A", allergens=["牛奶"])
    meal_b = make_meal("B", allergens=["花生"])

    results = batch_recommend(children, meal_a, meal_b, make_rule())

    assert len(results) == 4

    # NC_0001: 牛奶过敏，A餐含牛奶 → 推荐B
    r1 = results[0]
    assert r1["child_code"] == "NC_0001"
    assert r1["recommended_plan"] == "B"

    # NC_0002: 花生过敏，B餐含花生 → 推荐A
    r2 = results[1]
    assert r2["child_code"] == "NC_0002"
    assert r2["recommended_plan"] == "A"

    # NC_0003: 无过敏 → 正常评分
    r3 = results[2]
    assert r3["recommended_plan"] in ("A", "B")

    # NC_0004: 数据缺失
    r4 = results[3]
    assert r4["recommended_plan"] == "MANUAL"
    assert not r4["data_valid"]

    print("✅ test_batch_recommend PASSED")


def test_muslim_dietary_restriction():
    """清真饮食忌口排除猪肉"""
    child = make_child(dietary_restrictions=["清真"])
    meal_a = make_meal("A", ingredients=["米饭", "猪肉", "白菜"])
    meal_b = make_meal("B", ingredients=["米饭", "鸡肉", "青菜"])

    result = recommend(child, meal_a, meal_b, make_rule())

    assert result["recommended_plan"] == "B", f"Expected B, got {result['recommended_plan']}"
    assert "清真" in result["reason"] or "清真" in result["exclusion_reason"]
    print("✅ test_muslim_dietary_restriction PASSED")


def test_negative_values_in_meal():
    """套餐营养负值检测"""
    meal = make_meal("A", calories_kcal=-100)
    valid, msg = validate_meal_data(meal)
    assert not valid
    assert "负数" in msg
    print("✅ test_negative_values_in_meal PASSED")


def test_unusual_height_weight():
    """异常身高体重检测"""
    # 极低身高（低于50cm绝对下限）
    child = make_child(age=10, height_cm=30)
    valid, _ = validate_child_data(child)
    assert not valid, "30cm should be rejected"

    # 极高身高
    child = make_child(age=10, height_cm=250)
    valid, _ = validate_child_data(child)
    assert not valid, "250cm should be rejected"

    # 负体重
    child = make_child(weight_kg=-10)
    valid, _ = validate_child_data(child)
    assert not valid, "Negative weight should be rejected"

    print("✅ test_unusual_height_weight PASSED")


def test_allergen_alias_normalization():
    """过敏原别名归一化"""
    # 单个归一化
    assert _normalize_allergen("奶") == "牛奶", f"Expected 牛奶, got {_normalize_allergen('奶')}"
    assert _normalize_allergen("乳制品") == "牛奶"
    assert _normalize_allergen("鸡蛋") == "鸡蛋"
    assert _normalize_allergen("虾仁") == "虾"
    assert _normalize_allergen("对虾") == "虾"
    assert _normalize_allergen("蛋") == "鸡蛋"
    # 无映射的原样返回
    assert _normalize_allergen("芝麻") == "芝麻"

    # 批量归一化
    result = _normalize_allergens(["奶", "牛奶", "乳制品", "鸡蛋"])
    assert result == {"牛奶", "鸡蛋"}, f"Expected {{'牛奶','鸡蛋'}}, got {result}"
    print("✅ test_allergen_alias_normalization PASSED")


def test_allergen_alias_match():
    """过敏原别名匹配：'奶'应匹配套餐中的'牛奶'"""
    child = make_child(allergies=["奶", "花生"])
    meal_a = make_meal("A", allergens=["牛奶"])  # "奶"归一化为"牛奶"→匹配
    meal_b = make_meal("B", allergens=["鸡蛋"])

    result = recommend(child, meal_a, meal_b, make_rule())

    # A餐含"牛奶"应匹配儿童"奶"过敏→排除A
    assert result["recommended_plan"] == "B", f"Expected B, got {result['recommended_plan']}"
    assert "牛奶" in result["exclusion_reason"], f"Exclusion reason should mention 牛奶: {result['exclusion_reason']}"
    print("✅ test_allergen_alias_match PASSED")


def test_allergen_alias_no_false_match():
    """过敏原别名不应误匹配不相关的过敏原"""
    child = make_child(allergies=["虾"])
    # 套餐含"蛋"但被归一化为"鸡蛋"，不应匹配"虾"
    meal_a = make_meal("A", allergens=["鸡蛋"])
    meal_b = make_meal("B", allergens=["小麦"])

    result = recommend(child, meal_a, meal_b, make_rule())

    # 两餐都不含虾类过敏原，应正常评分推荐
    assert result["recommended_plan"] in ("A", "B")
    assert result["exclusion_reason"] == ""
    print("✅ test_allergen_alias_no_false_match PASSED")


# ============================================================
# 运行所有测试
# ============================================================

def run_all_tests():
    tests = [
        test_a_has_allergen_choose_b,
        test_b_has_allergen_choose_a,
        test_both_have_allergen_manual,
        test_missing_data_no_recommend,
        test_equal_scores_tiebreaker,
        test_weight_change_affects_score,
        test_dietary_restriction_vegetarian,
        test_special_needs_low_sugar,
        test_calculate_bmi,
        test_validate_meal_data,
        test_anomaly_detection,
        test_age_group,
        test_special_needs_coverage_score,
        test_batch_recommend,
        test_muslim_dietary_restriction,
        test_negative_values_in_meal,
        test_unusual_height_weight,
        test_allergen_alias_normalization,
        test_allergen_alias_match,
        test_allergen_alias_no_false_match,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    if failed == 0:
        print("🎉 ALL TESTS PASSED!")
    else:
        print(f"⚠️  {failed} test(s) failed")


if __name__ == "__main__":
    run_all_tests()
