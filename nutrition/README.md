# 儿童营养餐智能分配系统

## ⚠️ 重要声明

**本系统仅提供营养餐分配建议，不进行疾病诊断，也不能替代医生或专业营养师的意见。**

所有营养阈值和权重均为**测试演示配置**，不构成医学标准。真实阈值应由有资质的营养师配置并审核。

---

## 快速开始

### 1. 集成到现有 Flask 应用

```python
# 在现有 app.py 中添加：
from nutrition_system import init_app
init_app(app)
```

### 2. 部署前端

将 `static/` 目录下的文件复制到 Web 服务器的静态资源路径：
```bash
cp -r static/* /var/www/baoshan/static/nutrition/
```

### 3. 安装依赖

```bash
pip install cryptography  # 真实姓名加密（可选，无此依赖则明文存储）
```

### 4. 运行测试

```bash
python3 test_engine.py
```

---

## 系统架构

```
nutrition-system/
├── __init__.py          # 模块入口
├── engine.py            # 推荐引擎（纯函数，独立可测）
├── models.py            # 数据模型（SQLite）
├── routes.py            # Flask API 路由
├── security.py          # 加密/脱敏/权限
├── import_export.py     # 批量导入导出
├── test_engine.py       # 引擎单元测试（17 项）
├── static/              # 前端页面
│   ├── common.css       # 公共样式
│   ├── common.js        # 公共 JS 工具
│   ├── login.html       # 登录页
│   ├── children.html    # 儿童信息管理
│   ├── child-detail.html# 儿童详情
│   ├── meal-plans.html  # 套餐管理
│   ├── rules.html       # 营养规则配置
│   ├── recommendations.html  # 自动分配结果
│   ├── review.html      # 人工复核
│   ├── history.html     # 历史记录
│   └── audit-logs.html  # 审计日志
└── README.md
```

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/nutrition/children` | 儿童列表（分页+筛选） |
| GET | `/api/nutrition/children/<id>` | 儿童详情 |
| POST | `/api/nutrition/children` | 新增儿童 |
| PUT | `/api/nutrition/children/<id>` | 更新儿童 |
| DELETE | `/api/nutrition/children/<id>` | 删除（软删除） |
| POST | `/api/nutrition/children/import` | 批量导入 |
| GET | `/api/nutrition/children/export` | 批量导出CSV |
| GET | `/api/nutrition/children/anomalies` | 异常数据检查 |
| GET | `/api/nutrition/children/template` | 下载导入模板 |
| GET | `/api/nutrition/meal-plans` | 套餐列表 |
| GET | `/api/nutrition/meal-plans/<id>` | 套餐详情 |
| POST | `/api/nutrition/meal-plans` | 新增套餐 |
| POST | `/api/nutrition/meal-plans/batch` | 批量录入 A+B |
| DELETE | `/api/nutrition/meal-plans/<id>` | 删除套餐 |
| GET | `/api/nutrition/rules` | 规则列表 |
| POST | `/api/nutrition/rules` | 创建规则 |
| POST | `/api/nutrition/rules/<id>/activate` | 激活规则 |
| POST | `/api/nutrition/recommend` | 执行全量推荐 |
| GET | `/api/nutrition/recommendations` | 推荐结果列表 |
| GET | `/api/nutrition/recommendations/<id>` | 单条推荐详情 |
| POST | `/api/nutrition/recommendations/<id>/confirm` | 人工确认 |
| GET | `/api/nutrition/recommendations/export` | 导出配餐名单 |
| GET | `/api/nutrition/recommendations/stats` | 推荐统计 |
| GET | `/api/nutrition/audit-logs` | 审计日志 |
| GET | `/api/nutrition/health` | 健康检查 |

---

## 推荐引擎

### 核心函数

```python
from engine import recommend, batch_recommend

result = recommend(child_data, meal_a, meal_b, rule)
# => { recommended_plan, score_a, score_b, reason, exclusion_reason, risk_notes, rule_version }
```

### 算法流程

1. **硬性排除**：过敏原 → 忌口 → 特殊需求 → 不适用人群
2. **营养评分**：热量(25%) + 蛋白质(20%) + 糖(15%) + 钠(15%) + 脂肪(10%) + 纤维(10%) + 特殊需求(5%)
3. **结果判定**：排除 → 人工 / 单可用 → 推荐 / 比较得分 / 同分 → 优先级

### 测试覆盖（17 项）

- ✅ A餐含过敏原 → 选B餐
- ✅ B餐含过敏原 → 选A餐
- ✅ 两餐都含过敏原 → 人工处理
- ✅ 数据缺失 → 不自动推荐
- ✅ 两餐同分 → 优先级规则
- ✅ 权重修改 → 评分变化
- ✅ 素食忌口 → 排除含肉套餐
- ✅ 低糖需求 → 选择匹配标签套餐
- ✅ BMI计算
- ✅ 套餐数据验证
- ✅ 异常数据检测
- ✅ 年龄段分组
- ✅ 特殊需求覆盖率评分
- ✅ 批量推荐
- ✅ 清真忌口
- ✅ 负值检测
- ✅ 异常身高体重

---

## 隐私与安全

| 措施 | 实现 |
|------|------|
| 数据最小化 | 支持匿名编号 |
| 加密存储 | 真实姓名 AES 加密（Fernet） |
| 角色权限 | admin/teacher/parent/nutritionist 四级权限 |
| 审计日志 | 所有 CRUD/导入导出/推荐执行 |
| 日志脱敏 | 禁止日志输出完整身体数据 |
| 导出校验 | 导出文件前权限检查 |

---

## 演示角色

| 角色 | 权限 |
|------|------|
| admin | 全部权限 |
| teacher | 儿童读写 + 套餐查看 + 推荐执行/确认/导出 + 审计查看 |
| nutritionist | 儿童查看 + 套餐管理 + 规则管理 + 推荐查看/确认 |
| parent | 仅查看自己孩子的推荐结果 |
