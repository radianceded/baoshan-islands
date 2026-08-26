"""
批量导入导出模块
支持 Excel (.xlsx) 和 CSV 格式
"""

import json
import csv
import io
from datetime import datetime
from typing import List, Dict


def parse_import_data(file_content: bytes, file_type: str = "csv") -> tuple:
    """
    解析导入文件。
    返回 (children_list, errors_list)
    """
    children = []
    errors = []

    if file_type == "csv":
        children, errors = _parse_csv(file_content)
    elif file_type == "json":
        children, errors = _parse_json(file_content)
    else:
        errors.append(f"不支持的文件格式: {file_type}")

    return children, errors


def _parse_csv(content: bytes) -> tuple:
    """解析 CSV 文件"""
    children = []
    errors = []
    try:
        text = content.decode("utf-8-sig")  # 支持 BOM
    except UnicodeDecodeError:
        try:
            text = content.decode("gbk")
        except UnicodeDecodeError:
            errors.append("无法解码文件编码（尝试了 UTF-8 和 GBK）")
            return [], errors

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        errors.append("CSV 文件没有表头")
        return [], errors

    # 字段名映射（支持中英文）
    field_map = {
        "儿童编号": "child_code", "编号": "child_code", "child_code": "child_code",
        "姓名": "display_name", "名字": "display_name", "display_name": "display_name",
        "年龄": "age", "age": "age",
        "性别": "gender", "gender": "gender",
        "身高": "height_cm", "身高(cm)": "height_cm", "height_cm": "height_cm",
        "体重": "weight_kg", "体重(kg)": "weight_kg", "weight_kg": "weight_kg",
        "过敏": "allergies", "过敏信息": "allergies", "过敏原": "allergies",
        "忌口": "dietary_restrictions", "dietary_restrictions": "dietary_restrictions",
        "特殊需求": "special_needs", "饮食需求": "special_needs",
        "医生备注": "doctor_notes", "备注": "doctor_notes",
        "校区": "campus", "campus": "campus",
    }

    row_num = 1
    for row in reader:
        row_num += 1
        try:
            child = {}
            for header, value in row.items():
                header_clean = header.strip()
                target = field_map.get(header_clean, header_clean)
                if target not in field_map.values():
                    continue

                value = value.strip() if value else ""

                # 类型转换
                if target in ("age",):
                    child[target] = int(value) if value else None
                elif target in ("height_cm", "weight_kg"):
                    child[target] = float(value) if value else None
                elif target in ("allergies", "dietary_restrictions", "special_needs"):
                    if value:
                        child[target] = [v.strip() for v in value.replace("，", ",").split(",") if v.strip()]
                    else:
                        child[target] = []
                else:
                    child[target] = value if value else None

            if not child.get("display_name") and not child.get("child_code"):
                errors.append(f"第{row_num}行：缺少姓名和编号")
                continue

            children.append(child)
        except (ValueError, TypeError) as e:
            errors.append(f"第{row_num}行：数据格式错误 - {e}")

    return children, errors


def _parse_json(content: bytes) -> tuple:
    """解析 JSON 文件"""
    children = []
    errors = []
    try:
        data = json.loads(content.decode("utf-8"))
        if isinstance(data, dict) and "children" in data:
            data = data["children"]
        if not isinstance(data, list):
            errors.append("JSON 数据格式错误：期望数组或 {children: [...]}")
            return [], errors
        for i, item in enumerate(data):
            try:
                children.append(item)
            except Exception as e:
                errors.append(f"第{i+1}项：{e}")
    except json.JSONDecodeError as e:
        errors.append(f"JSON 解析错误：{e}")
    return children, errors


def export_to_csv(recommendations: List[Dict], include_sensitive: bool = False) -> str:
    """导出推荐结果到 CSV"""
    output = io.StringIO()
    writer = csv.writer(output)

    headers = ["儿童编号", "年龄", "性别", "身高(cm)", "体重(kg)", "校区",
               "数据状态", "A餐得分", "B餐得分", "推荐结果", "推荐原因",
               "排除原因", "风险提示", "确认状态", "规则版本"]
    writer.writerow(headers)

    for r in recommendations:
        row = [
            r.get("child_code", ""),
            r.get("age", ""),
            r.get("gender", ""),
            r.get("height_cm", "") if include_sensitive else (r.get("height_cm") or ""),
            r.get("weight_kg", "") if include_sensitive else (r.get("weight_kg") or ""),
            r.get("campus", ""),
            r.get("data_status", ""),
            r.get("score_a", ""),
            r.get("score_b", ""),
            r.get("recommended_plan", ""),
            r.get("reason", ""),
            r.get("exclusion_reason", ""),
            r.get("risk_notes", ""),
            "已确认" if r.get("confirmed") else "未确认",
            r.get("rule_version", ""),
        ]
        writer.writerow(row)

    return output.getvalue()


def export_to_json(recommendations: List[Dict]) -> str:
    """导出推荐结果到 JSON"""
    return json.dumps(recommendations, ensure_ascii=False, indent=2, default=str)


def generate_import_template() -> str:
    """生成导入模板 CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["儿童编号", "姓名", "年龄", "性别", "身高(cm)", "体重(kg)",
                      "过敏信息", "忌口", "特殊需求", "医生备注", "校区"])
    writer.writerow(["NC_0001", "张三", "9", "男", "135", "30",
                      "牛奶,花生", "", "低糖", "", "本部"])
    writer.writerow(["NC_0002", "李四", "8", "女", "128", "26",
                      "", "素食", "", "", "宝林"])
    return output.getvalue()
