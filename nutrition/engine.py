"""
儿童营养餐智能分配系统 — 推荐引擎（纯函数模块）

============================================================
输入：
    - child: dict，儿童身体数据
    - meal_a: dict，A餐营养数据
    - meal_b: dict，B餐营养数据
    - rule: dict，营养规则配置（含权重和阈值）
============================================================
输出：
    - dict: {
        "recommended_plan": "A" | "B" | "MANUAL",
        "score_a": float (0.0-1.0),
        "score_b": float (0.0-1.0),
        "reason": str (可解释推荐原因),
        "exclusion_reason": str,
        "risk_notes": str,
        "rule_version": str
      }
============================================================
功能：
    1. 硬性排除：过敏原/忌口/特殊需求/不适用人群
    2. 营养评分：热量/蛋白质/糖/钠/脂肪/纤维/特殊需求加权
    3. 结果判定：排除→人工 / 单可用→推荐 / 都比分→高分 / 同分→优先级
============================================================
"""

import json
from typing import Dict, Optional, Tuple, List

# ============================================================
# 演示用阈值配置 — ⚠️ 非医学标准，仅供系统功能演示
# 真实阈值应由有资质的营养师配置并审核
# ============================================================
DEMO_CALORIE_RANGES = {
    "3-6":   (1200, 1600),   # 学龄前
    "7-10":  (1600, 2000),   # 小学低年级
    "11-13": (2000, 2400),   # 小学高年级
    "14-17": (2200, 2800),   # 中学生
}

DEMO_PROTEIN_MIN = {
    "3-6":   20,   # 克
    "7-10":  30,
    "11-13": 40,
    "14-17": 55,
}

DEMO_SUGAR_MAX = {
    "3-6":   25,
    "7-10":  30,
    "11-13": 35,
    "14-17": 40,
}

DEMO_SODIUM_MAX = {
    "3-6":   1200,  # 毫克
    "7-10":  1500,
    "11-13": 1800,
    "14-17": 2000,
}

DEMO_FAT_RANGES = {
    "3-6":   (30, 50),
    "7-10":  (40, 65),
    "11-13": (50, 75),
    "14-17": (60, 90),
}

DEMO_FIBER_MIN = {
    "3-6":   10,
    "7-10":  14,
    "11-13": 18,
    "14-17": 22,
}

# ============================================================
# 辅助函数
# ============================================================

def _get_age_group(age: int) -> str:
    """根据年龄返回年龄段 key"""
    if age is None:
        return "7-10"  # 默认值
    if age <= 6:
        return "3-6"
    elif age <= 10:
        return "7-10"
    elif age <= 13:
        return "11-13"
    else:
        return "14-17"


def _linear_sub_score(value: float, lower: float, upper: float) -> float:
    """
    计算范围匹配子分数。
    value 在 [lower, upper] 内 → 1.0
    偏离时按比例线性衰减，最低 0.0
    """
    if value is None:
        return 0.5  # 数据缺失给中性分
    if lower <= value <= upper:
        return 1.0
    if value < lower:
        return max(0.0, value / lower)
    if value > upper:
        ratio = upper / value
        return max(0.0, ratio)


def _min_achievement_score(value: float, min_val: float) -> float:
    """计算最小值达标分数"""
    if value is None:
        return 0.5
    if min_val <= 0:
        return 1.0
    if value >= min_val:
        return 1.0
    return max(0.0, value / min_val)


def _max_achievement_score(value: float, max_val: float) -> float:
    """计算最大值达标分数"""
    if value is None:
        return 0.5
    if max_val <= 0:
        return 1.0
    if value <= max_val:
        return 1.0
    return max(0.0, max_val / value)


# ============================================================
# 过敏原别名映射 — 处理名称不统一问题
# 将常见变体归一为统一名称
# ============================================================

ALLERGEN_ALIASES = {
    # 奶类
    "牛奶": "牛奶", "奶": "牛奶", "乳制品": "牛奶", "牛乳": "牛奶", "乳清": "牛奶", "乳": "牛奶",
    # 蛋类
    "鸡蛋": "鸡蛋", "蛋": "鸡蛋", "蛋类": "鸡蛋",
    # 花生
    "花生": "花生",
    # 海鲜
    "虾": "虾", "虾仁": "虾", "海虾": "虾", "对虾": "虾",
    "蟹": "蟹", "螃蟹": "蟹",
    "鱼": "鱼", "鱼肉": "鱼", "鱼类": "鱼",
    # 大豆
    "大豆": "大豆", "黄豆": "大豆", "豆类": "大豆",
    # 小麦/麸质
    "小麦": "小麦", "面粉": "小麦", "麸质": "小麦",
    # 坚果
    "坚果": "坚果", "核桃": "坚果", "杏仁": "坚果", "腰果": "坚果",
}


def _normalize_allergen(raw: str) -> str:
    """将过敏原名称归一化，处理同义词"""
    name = raw.strip().lower()
    # 先查别名映射
    if name in ALLERGEN_ALIASES:
        return ALLERGEN_ALIASES[name]
    # 无映射则保留原样
    return name


def _normalize_allergens(items: List[str]) -> set:
    """批量归一化过敏原列表，返回去重后的集合"""
    return {_normalize_allergen(a) for a in items if a and a.strip()}


# ============================================================
# 硬性排除检查
# ============================================================

def check_allergen_exclusion(child_allergies: List[str],
                              meal_allergens: List[str]) -> Tuple[bool, str]:
    """
    检查过敏原排除。
    使用别名映射处理过敏原名称不统一的情况。
    返回 (是否排除, 原因)
    """
    if not child_allergies:
        return False, ""
    if not meal_allergens:
        return False, ""

    child_set = _normalize_allergens(child_allergies)
    meal_set = _normalize_allergens(meal_allergens)

    matched = child_set & meal_set
    if matched:
        return True, f"该儿童对以下过敏原过敏：{', '.join(matched)}，套餐中含有这些成分"
    return False, ""


def check_dietary_restriction_conflict(child_restrictions: List[str],
                                         meal_ingredients: List[str]) -> Tuple[bool, str]:
    """
    检查忌口冲突。
    采用简单关键词匹配。
    """
    if not child_restrictions:
        return False, ""

    restriction_map = {
        "素食": ["肉", "猪肉", "牛肉", "鸡肉", "鸭肉", "鱼", "虾", "蟹", "贝", "火腿", "腊肉", "培根", "排骨", "鸡腿", "鸡翅"],
        "清真": ["猪肉", "火腿", "腊肉", "培根"],
        "无乳糖": ["牛奶", "乳清", "奶酪", "黄油", "奶油", "芝士", "酸奶"],
        "无麸质": ["面粉", "小麦", "面筋", "面包", "面条", "馒头"],
        "低糖": [],   # 由营养评分处理
        "低盐": [],   # 由营养评分处理
        "低脂": [],   # 由营养评分处理
        "高蛋白": [], # 由营养评分处理
    }

    ingredients_lower = [i.strip().lower() for i in meal_ingredients if i.strip()]

    for restriction in child_restrictions:
        keywords = restriction_map.get(restriction, [])
        for kw in keywords:
            for ing in ingredients_lower:
                if kw.lower() in ing:
                    return True, f"该儿童忌「{restriction}」，套餐中含「{ing}」"
    return False, ""


def check_special_needs_compatibility(child_special_needs: List[str],
                                        meal_suitable_tags: List[str]) -> Tuple[bool, str]:
    """
    检查特殊需求兼容性。
    如果儿童有特殊需求但套餐不适用标签则不兼容。
    """
    if not child_special_needs:
        return False, ""

    needs = [n.strip() for n in child_special_needs if n.strip()]
    tags = [t.strip() for t in meal_suitable_tags if t.strip()]
    tags_lower = [t.lower() for t in tags]

    unsatisfied = []
    for need in needs:
        if need.lower() not in tags_lower:
            unsatisfied.append(need)

    if unsatisfied:
        return True, f"套餐不支持的饮食需求：{', '.join(unsatisfied)}"
    return False, ""


def check_unsuitable_match(child_info: dict, unsuitable_notes: str) -> Tuple[bool, str]:
    """
    检查是否属于不适用人群。
    简单关键词匹配。
    """
    if not unsuitable_notes:
        return False, ""
    # 简化处理：如果儿童有特殊备注且套餐明确标注不适用，标记
    doctor_notes = child_info.get("doctor_notes", "") or ""
    special_needs = child_info.get("special_needs", []) or []
    all_text = (doctor_notes + " " + " ".join(special_needs)).lower()
    notes_lower = unsuitable_notes.lower()

    # 简单检查：如果任何特殊需求关键词出现在不适用说明中
    for need in special_needs:
        if need.lower() in notes_lower:
            return True, f"套餐标注不适用人群包含「{need}」"
    return False, ""


# ============================================================
# 营养匹配评分
# ============================================================

def calc_sub_score_calorie(meal: dict, child: dict, rule: dict) -> float:
    """热量匹配子分数"""
    age_group = _get_age_group(child.get("age"))
    config = json.loads(rule.get("calorie_range_config", "{}")) if isinstance(rule.get("calorie_range_config"), str) else (rule.get("calorie_range_config") or {})
    lower, upper = config.get(age_group, DEMO_CALORIE_RANGES.get(age_group, (1600, 2000)))
    return _linear_sub_score(meal.get("calories_kcal"), lower, upper)


def calc_sub_score_protein(meal: dict, child: dict, rule: dict) -> float:
    """蛋白质匹配子分数"""
    age_group = _get_age_group(child.get("age"))
    config = json.loads(rule.get("protein_min_config", "{}")) if isinstance(rule.get("protein_min_config"), str) else (rule.get("protein_min_config") or {})
    min_val = config.get(age_group, DEMO_PROTEIN_MIN.get(age_group, 30))
    return _min_achievement_score(meal.get("protein_g"), min_val)


def calc_sub_score_sugar(meal: dict, child: dict, rule: dict) -> float:
    """糖含量子分数"""
    age_group = _get_age_group(child.get("age"))
    config = json.loads(rule.get("sugar_max_config", "{}")) if isinstance(rule.get("sugar_max_config"), str) else (rule.get("sugar_max_config") or {})
    max_val = config.get(age_group, DEMO_SUGAR_MAX.get(age_group, 30))
    return _max_achievement_score(meal.get("sugar_g"), max_val)


def calc_sub_score_sodium(meal: dict, child: dict, rule: dict) -> float:
    """钠含量子分数"""
    age_group = _get_age_group(child.get("age"))
    config = json.loads(rule.get("sodium_max_config", "{}")) if isinstance(rule.get("sodium_max_config"), str) else (rule.get("sodium_max_config") or {})
    max_val = config.get(age_group, DEMO_SODIUM_MAX.get(age_group, 1500))
    return _max_achievement_score(meal.get("sodium_mg"), max_val)


def calc_sub_score_fat(meal: dict, child: dict, rule: dict) -> float:
    """脂肪匹配子分数"""
    age_group = _get_age_group(child.get("age"))
    config = json.loads(rule.get("fat_range_config", "{}")) if isinstance(rule.get("fat_range_config"), str) else (rule.get("fat_range_config") or {})
    lower, upper = config.get(age_group, DEMO_FAT_RANGES.get(age_group, (40, 65)))
    return _linear_sub_score(meal.get("fat_g"), lower, upper)


def calc_sub_score_fiber(meal: dict, child: dict, rule: dict) -> float:
    """膳食纤维子分数"""
    age_group = _get_age_group(child.get("age"))
    config = json.loads(rule.get("fiber_min_config", "{}")) if isinstance(rule.get("fiber_min_config"), str) else (rule.get("fiber_min_config") or {})
    min_val = config.get(age_group, DEMO_FIBER_MIN.get(age_group, 14))
    return _min_achievement_score(meal.get("fiber_g"), min_val)


def calc_sub_score_special(meal: dict, child: dict, rule: dict) -> float:
    """特殊需求匹配子分数"""
    special_needs = child.get("special_needs", []) or []
    if not special_needs:
        return 1.0  # 无特殊需求则满分
    suitable_tags = meal.get("suitable_tags", []) or []
    suitable_lower = [t.lower() for t in suitable_tags]
    matched = sum(1 for n in special_needs if n.lower() in suitable_lower)
    return matched / len(special_needs)


# ============================================================
# 核心推荐函数（单次）
# ============================================================

def calculate_meal_score(meal: dict, child: dict, rule: dict) -> float:
    """
    计算套餐对单个儿童的匹配得分。
    """
    weights = {
        "calorie": float(rule.get("weight_calorie", 0.25)),
        "protein": float(rule.get("weight_protein", 0.20)),
        "sugar": float(rule.get("weight_sugar", 0.15)),
        "sodium": float(rule.get("weight_sodium", 0.15)),
        "fat": float(rule.get("weight_fat", 0.10)),
        "fiber": float(rule.get("weight_fiber", 0.10)),
        "special": float(rule.get("weight_special", 0.05)),
    }

    sub_scores = {
        "calorie": calc_sub_score_calorie(meal, child, rule),
        "protein": calc_sub_score_protein(meal, child, rule),
        "sugar": calc_sub_score_sugar(meal, child, rule),
        "sodium": calc_sub_score_sodium(meal, child, rule),
        "fat": calc_sub_score_fat(meal, child, rule),
        "fiber": calc_sub_score_fiber(meal, child, rule),
        "special": calc_sub_score_special(meal, child, rule),
    }

    score = sum(weights[k] * sub_scores[k] for k in weights)
    return round(score, 4)


def check_exclusion(meal: dict, child: dict) -> Tuple[bool, str]:
    """
    检查套餐是否应被排除。
    返回 (是否排除, 排除原因)
    """
    reasons = []

    # 辅助：把可能为 JSON 字符串的字段转为列表
    def _parse_list(val):
        if val is None:
            return []
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return [v.strip() for v in val.split(",") if v.strip()] if val else []
        return []

    # 1. 过敏原检查
    child_allergies = _parse_list(child.get("allergies"))
    meal_allergens = _parse_list(meal.get("allergens"))
    excluded, reason = check_allergen_exclusion(child_allergies, meal_allergens)
    if excluded:
        reasons.append(reason)

    # 2. 忌口冲突检查
    child_restrictions = _parse_list(child.get("dietary_restrictions"))
    meal_ingredients = _parse_list(meal.get("ingredients"))
    excluded, reason = check_dietary_restriction_conflict(child_restrictions, meal_ingredients)
    if excluded:
        reasons.append(reason)

    # 3. 特殊需求兼容性
    child_special = _parse_list(child.get("special_needs"))
    meal_tags = _parse_list(meal.get("suitable_tags"))
    excluded, reason = check_special_needs_compatibility(child_special, meal_tags)
    if excluded:
        reasons.append(reason)

    # 4. 不适用人群检查
    unsuitable = meal.get("unsuitable_notes", "") or ""
    excluded, reason = check_unsuitable_match(child, unsuitable)
    if excluded:
        reasons.append(reason)

    return len(reasons) > 0, "；".join(reasons)


def recommend(child: dict, meal_a: dict, meal_b: dict, rule: dict) -> dict:
    """
    核心推荐函数 — 为单个儿童推荐更合适的套餐。

    输入:
        child  = { child_code, age, gender, height_cm, weight_kg, bmi, allergies, ... }
        meal_a = { plan_type: 'A', calories_kcal, protein_g, fat_g, carbs_g,
                   sugar_g, sodium_mg, fiber_g, allergens, ingredients,
                   suitable_tags, unsuitable_notes, ... }
        meal_b = { ... 同上 ... }
        rule   = { version, weight_calorie, weight_protein, ..., calorie_range_config, ... }

    输出:
        { recommended_plan, score_a, score_b, reason, exclusion_reason, risk_notes, rule_version }
    """
    rule_version = rule.get("version", "unknown")

    # 阶段一：硬性排除
    a_excluded, a_exclusion_reason = check_exclusion(meal_a, child)
    b_excluded, b_exclusion_reason = check_exclusion(meal_b, child)

    # 阶段二：营养匹配评分
    score_a = calculate_meal_score(meal_a, child, rule) if not a_excluded else 0.0
    score_b = calculate_meal_score(meal_b, child, rule) if not b_excluded else 0.0

    # 阶段三：结果判定
    risk_notes = ""

    # 情况1: 两餐都排除
    if a_excluded and b_excluded:
        return {
            "recommended_plan": "MANUAL",
            "score_a": 0.0,
            "score_b": 0.0,
            "reason": f"两餐均不满足安全要求，需要人工处理。A餐排除原因：{a_exclusion_reason}；B餐排除原因：{b_exclusion_reason}",
            "exclusion_reason": f"A: {a_exclusion_reason}; B: {b_exclusion_reason}",
            "risk_notes": "该儿童无法从现有A/B餐中选择安全套餐，请人工安排特殊餐食。",
            "rule_version": rule_version,
        }

    # 情况2: A被排除，只能选B
    if a_excluded:
        return {
            "recommended_plan": "B",
            "score_a": 0.0,
            "score_b": score_b,
            "reason": f"推荐B餐。A餐排除原因：{a_exclusion_reason}；B餐无过敏原冲突，营养评分{score_b}。",
            "exclusion_reason": f"A餐已排除：{a_exclusion_reason}",
            "risk_notes": risk_notes or "",
            "rule_version": rule_version,
        }

    # 情况3: B被排除，只能选A
    if b_excluded:
        return {
            "recommended_plan": "A",
            "score_a": score_a,
            "score_b": 0.0,
            "reason": f"推荐A餐。B餐排除原因：{b_exclusion_reason}；A餐无过敏原冲突，营养评分{score_a}。",
            "exclusion_reason": f"B餐已排除：{b_exclusion_reason}",
            "risk_notes": risk_notes or "",
            "rule_version": rule_version,
        }

    # 情况4: 比较得分
    diff = round(score_a - score_b, 4)

    if abs(diff) < 0.001:
        # 同分配优先级：热量更优 → 蛋白质更优 → 选A
        a_calorie_score = calc_sub_score_calorie(meal_a, child, rule)
        b_calorie_score = calc_sub_score_calorie(meal_b, child, rule)
        if a_calorie_score > b_calorie_score:
            winner = "A"
            tie_reason = "A餐热量更接近推荐范围"
        elif b_calorie_score > a_calorie_score:
            winner = "B"
            tie_reason = "B餐热量更接近推荐范围"
        else:
            a_protein_score = calc_sub_score_protein(meal_a, child, rule)
            b_protein_score = calc_sub_score_protein(meal_b, child, rule)
            if a_protein_score > b_protein_score:
                winner = "A"
                tie_reason = "A餐蛋白质更充足"
            elif b_protein_score > a_protein_score:
                winner = "B"
                tie_reason = "B餐蛋白质更充足"
            else:
                winner = "A"
                tie_reason = "两餐在各维度得分相同，默认选择A餐"

        return {
            "recommended_plan": winner,
            "score_a": score_a,
            "score_b": score_b,
            "reason": f"两餐得分相同（A: {score_a}, B: {score_b}），{tie_reason}。",
            "exclusion_reason": "",
            "risk_notes": risk_notes or "两餐得分完全相同，按预设优先级规则判定。",
            "rule_version": rule_version,
        }

    # 情况5: 正常比较
    winner = "A" if score_a > score_b else "B"
    winner_score = score_a if winner == "A" else score_b
    loser_score = score_b if winner == "A" else score_a

    return {
        "recommended_plan": winner,
        "score_a": score_a,
        "score_b": score_b,
        "reason": f"推荐{winner}餐。A餐得分{score_a}，B餐得分{score_b}，{winner}餐综合匹配更优。",
        "exclusion_reason": "",
        "risk_notes": risk_notes or "",
        "rule_version": rule_version,
    }


# ============================================================
# 数据完整性检查（输入验证）
# ============================================================

def validate_child_data(child: dict) -> Tuple[bool, str]:
    """
    验证儿童数据是否完整可进行推荐。

    输入: child dict
    输出: (是否可推荐, 原因)
    """
    issues = []

    if child.get("age") is None or child.get("age", 0) <= 0:
        issues.append("年龄缺失或异常")
    if child.get("age") is not None and (child["age"] < 2 or child["age"] > 18):
        issues.append(f"年龄({child['age']}岁)超出正常范围(2-18)")

    if child.get("height_cm") is None or child.get("height_cm", 0) <= 0:
        issues.append("身高缺失或异常")
    elif child["height_cm"] < 50 or child["height_cm"] > 220:
        issues.append(f"身高({child['height_cm']}cm)超出正常范围(50-220)")

    if child.get("weight_kg") is None or child.get("weight_kg", 0) <= 0:
        issues.append("体重缺失或异常")
    elif child["weight_kg"] < 5 or child["weight_kg"] > 200:
        issues.append(f"体重({child['weight_kg']}kg)超出正常范围(5-200)")

    if child.get("gender") not in ("男", "女", "其他"):
        issues.append("性别缺失或无效")

    if issues:
        return False, "；".join(issues)
    return True, ""


def validate_meal_data(meal: dict) -> Tuple[bool, str]:
    """
    验证套餐数据是否完整。

    输入: meal dict
    输出: (是否完整, 原因)
    """
    required_fields = {
        "calories_kcal": "热量",
        "protein_g": "蛋白质",
        "fat_g": "脂肪",
        "carbs_g": "碳水化合物",
        "sugar_g": "糖",
        "sodium_mg": "钠",
        "fiber_g": "膳食纤维",
    }

    missing = []
    for field, label in required_fields.items():
        if meal.get(field) is None:
            missing.append(label)

    if missing:
        return False, f"缺少营养数据：{', '.join(missing)}"

    # 负值检查
    for field, label in required_fields.items():
        val = meal.get(field)
        if val is not None and val < 0:
            return False, f"{label}为负数({val})，数据异常"

    return True, ""


def check_anomalies(child: dict) -> List[str]:
    """
    检查儿童数据的异常项（不阻止推荐，但提供告警）。

    输入: child dict
    输出: 异常信息列表
    """
    warnings = []

    if child.get("bmi") is not None:
        bmi = child["bmi"]
        if bmi < 13:
            warnings.append(f"BMI({bmi})偏低(<13)，可能存在营养不良风险")
        elif bmi > 26:
            warnings.append(f"BMI({bmi})偏高(>26)，注意体重管理")

    if child.get("height_cm") and child.get("age"):
        # 粗略身高异常检测
        expected_min = 80 + (child["age"] - 2) * 5
        expected_max = 120 + (child["age"] - 2) * 7
        if child["height_cm"] < expected_min * 0.8:
            warnings.append(f"身高({child['height_cm']}cm)明显低于同年龄段预期")
        if child["height_cm"] > expected_max * 1.2:
            warnings.append(f"身高({child['height_cm']}cm)明显高于同年龄段预期")

    return warnings


def calculate_bmi(height_cm: float, weight_kg: float) -> Optional[float]:
    """计算 BMI = 体重(kg) / 身高(m)^2"""
    if height_cm and weight_kg and height_cm > 0:
        return round(weight_kg / ((height_cm / 100) ** 2), 2)
    return None


# ============================================================
# 批量推荐
# ============================================================

def batch_recommend(children: List[dict],
                     meal_a: dict,
                     meal_b: dict,
                     rule: dict) -> List[dict]:
    """
    批量推荐 — 对多个儿童执行推荐。

    输入:
        children: 儿童数据列表
        meal_a, meal_b: 当日套餐
        rule: 营养规则

    输出:
        [{ child_code, ...recommendation fields, data_valid, data_issues, anomalies }]
    """
    results = []
    for child in children:
        # 数据完整性检查
        data_valid, data_issues = validate_child_data(child)
        meal_a_valid, meal_a_issues = validate_meal_data(meal_a)
        meal_b_valid, meal_b_issues = validate_meal_data(meal_b)

        if not data_valid or not meal_a_valid or not meal_b_valid:
            all_issues = []
            if not data_valid:
                all_issues.append(f"儿童数据不完整: {data_issues}")
            if not meal_a_valid:
                all_issues.append(f"A餐数据不完整: {meal_a_issues}")
            if not meal_b_valid:
                all_issues.append(f"B餐数据不完整: {meal_b_issues}")

            results.append({
                "child_code": child.get("child_code", "unknown"),
                "child_id": child.get("id"),
                "recommended_plan": "MANUAL",
                "score_a": 0.0,
                "score_b": 0.0,
                "reason": "需要补充数据",
                "exclusion_reason": "；".join(all_issues),
                "risk_notes": "",
                "rule_version": rule.get("version", "unknown"),
                "data_valid": False,
                "data_issues": "；".join(all_issues),
                "anomalies": [],
            })
            continue

        # 执行推荐
        result = recommend(child, meal_a, meal_b, rule)

        # 异常检测
        anomalies = check_anomalies(child)
        if anomalies:
            if result.get("risk_notes"):
                result["risk_notes"] += " " + "；".join(anomalies)
            else:
                result["risk_notes"] = "；".join(anomalies)

        result["child_code"] = child.get("child_code", "unknown")
        result["child_id"] = child.get("id")
        result["data_valid"] = True
        result["data_issues"] = ""
        result["anomalies"] = anomalies

        results.append(result)

    return results
