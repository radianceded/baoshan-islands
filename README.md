# Baoshan Islands

宝山实验小学的校园成长岛与营养选餐平台。系统面向学生家长、班主任、总务和管理员，覆盖多校区身份认证、学生画像、社团报名、营养选餐，以及按周留存的菜单、选餐结果和餐食实拍。

当前公开代码快照同步自生产版本 `04941d6`（2026-09-16）；GitHub 提交不会自动部署生产环境。详细同步边界见 [PRODUCTION_SYNC.md](PRODUCTION_SYNC.md)。

## 主要功能

- 三校区独立登录与数据隔离：本部、宝林、罗泾
- 家长多孩切换，班主任按绑定班级访问，总务按校区管理
- 兴趣岛社团发布、报名、名单确认与统计
- A/B 餐菜单导入、家长选餐、班级与全校汇总
- 截止后按周归档菜单和选餐结果，支持总务补传餐食实拍
- 学生画像、健康、阅读、劳动、档案与荣誉等成长岛页面

## 隐私说明

本公开仓库是脱敏代码快照，不包含：

- 学生通讯录、体测、屈光、获奖等个人数据
- 业务数据库与认证数据库
- 钉钉 AppKey、AppSecret、CorpId 和服务器密钥
- 真实教师 UserID、白名单和明文账号密码表

仓库中的人名、UserID、域名和 IP 均为示例或脱敏值。请勿将生产数据提交到 Git。

## 本地运行

1. 安装 Python 依赖：

   ```bash
   pip install -r requirements.txt
   pip install -r requirements-meal-history.txt
   ```

2. 复制并填写环境配置：

   ```bash
   cp server/.env.example server/.env
   ```

3. 在本地放置或构建测试数据库。数据库文件已被 `.gitignore` 排除；不要复制生产数据库到公开仓库。

4. 启动服务：

   ```bash
   python server/app.py
   ```

## 校区隔离

- 本部：项目根目录下的业务库和认证库
- 宝林：`campus_data/baolin/` 下的独立业务库和认证库
- 罗泾：`campus_data/luojing/` 下的独立业务库和认证库

请使用 `server/campus_config.example.json` 创建部署服务器上的 `server/campus_config.json`，真实配置不进入仓库。总务和双身份教师的真实 UserID 也只通过部署环境配置。

## 餐食历史

餐食历史按“校区 + 学期 + 周次”保存菜单快照、截止时的选餐结果和实拍照片版本。图片保存在部署服务器的私有上传目录，数据库只记录路径与元数据；家长只看绑定孩子，班主任只看本班，总务查看本校区。

迁移、备份、Nginx 保护和回滚步骤见 [MEAL_HISTORY_DEPLOYMENT.md](MEAL_HISTORY_DEPLOYMENT.md)。

## 测试

```bash
python -m unittest discover -s tests -p test_meal_history.py -q
python -m unittest discover -s tests -p test_menu_excel_import.py -q
python -m unittest discover -s tests -p test_meal_pending.py -q
```

仓库也保留其他模块的回归测试。当前公开生产快照中，旧综合测试仍有已知的基线失败，因此不要仅凭一次全量测试结果判断本次餐食历史功能是否回归。

## 数据构建工具

- `scripts/build_independent_auth.py`：从只读数据源构建独立账号密码库
- `scripts/build_baolin_campus.py`：从通讯录构建宝林校区的独立业务库和认证库
- `server/migrate_meal_history.py`：预演或执行餐食历史的增量迁移
- `server/backup_meal_history.py`：在网站目录外创建一致性 SQLite 备份

这些脚本生成的 `credentials.json`、Excel 账号表和数据库均属于私密交付物，不得提交到公开仓库。
