# Baoshan Islands

校园成长岛与营养选餐平台，支持学生家长、班主任和总务三类独立账号，以及按校区物理隔离的业务库与认证库。

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
   ```

2. 复制并填写环境配置：

   ```bash
   cp server/.env.example server/.env
   ```

3. 在本地放置或构建数据库。数据库文件已被 `.gitignore` 排除。

4. 启动服务：

   ```bash
   python server/app.py
   ```

## 校区隔离

- 本部：项目根目录下的业务库和认证库
- 宝林：`campus_data/baolin/` 下的独立业务库和认证库

请使用 `server/campus_config.example.json` 创建部署服务器上的 `server/campus_config.json`，真实配置不进入仓库。

## 测试

```bash
python -m unittest discover -s tests
```

## 数据构建工具

- `scripts/build_independent_auth.py`：从只读数据源构建独立账号密码库
- `scripts/build_baolin_campus.py`：从通讯录构建宝林校区的独立业务库和认证库

这些脚本生成的 `credentials.json`、Excel 账号表和数据库均属于私密交付物，不得提交到公开仓库。
