# 宝山学习群岛 · 后端 API 部署指南

## 架构

```
钉钉 / 浏览器
     │
     ▼
┌──────────────────────────────────┐
│  前端（纯静态 HTML / JS）         │
│  - 直接静态托管，也可由 Flask 提供 │
└──────────────────┬───────────────┘
                   │ /api/*
                   ▼
┌──────────────────────────────────┐
│  Flask 后端（本文件夹）           │
│  - /api/ai/chat       AI 代理     │
│  - /api/auth/dingtalk 钉钉 SSO    │
│  - /api/custom-students CRUD     │
│  - /api/students 等               │
└──────────────────┬───────────────┘
                   ▼
        SQLite (student_data.db)
                   │
        百度千帆 API（仅服务端）
```

---

## 1. 本地启动（开发）

```bash
# 0. 安装依赖
pip3 install -r requirements.txt

# 1. 配置环境变量
cp server/.env.example server/.env
vim server/.env       # 填入你的 BAIDU_AI_KEY 等

# 2. 加载 env 并启动
set -a; source server/.env; set +a
cd server && python3 app.py

# 3. 访问
open http://localhost:5000
```

启动后会看到：
```
================ 宝山学习群岛 API ================
 数据库:    .../student_data.db
 AI:        ✓ 已配置 (ernie-5.1)
 钉钉 SSO:  ✓ 已配置
 监听:      http://localhost:5000
==================================================
```

---

## 2. 钉钉应用注册

### 创建 H5 微应用
1. 进入 [钉钉开放平台](https://open-dev.dingtalk.com/) → "应用开发" → "企业内部应用"
2. 创建 "H5 微应用"，记下 `AgentId / AppKey / AppSecret / CorpId`
3. **应用首页地址**填你的 HTTPS 域名（如 `https://baoshan.your-domain.com/island-homepage.html`）
4. **服务器出口 IP** 填你部署后端的服务器公网 IP
5. **开发管理 → 安全域名** 加入你的域名
6. **权限管理** 勾选：
   - `通讯录个人信息读权限`
   - `成员信息读取`

### 嵌入钉钉 JSAPI
首页 `island-homepage.html` 的 `<head>` 加入：
```html
<script>window.BS_DINGTALK_CORP_ID = '你的CorpId';</script>
<script src="//g.alicdn.com/dingding/dingtalk-jsapi/2.13.42/dingtalk.open.js"></script>
<script src="assets/dingtalk-bootstrap.js"></script>
```

之后用户在钉钉里打开页面，会自动 SSO，sessionToken 存 `sessionStorage.bs_session_token`，所有 `/api/*` 请求自动带上 Authorization 头。

---

## 3. 生产部署（HTTPS 必需）

### 选项 A · Nginx + Gunicorn（推荐）
```bash
# 装 gunicorn
pip3 install gunicorn

# 用 systemd 跑 gunicorn
# /etc/systemd/system/baoshan.service:
[Service]
WorkingDirectory=/opt/baoshan/server
EnvironmentFile=/opt/baoshan/server/.env
ExecStart=/usr/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app

# Nginx 反代 + Let's Encrypt 证书
server {
  listen 443 ssl http2;
  server_name baoshan.your-domain.com;
  root /opt/baoshan;
  
  location /api/ {
    proxy_pass http://127.0.0.1:5000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
  }
  location / {
    try_files $uri /island-homepage.html;
  }
}
```

### 选项 B · Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt gunicorn
COPY . .
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "server.app:app"]
```

### 选项 C · 钉钉云托管 / 阿里云函数计算
钉钉应用可直接配置"云托管"，省去自购服务器。需要把代码打包成 `python:3.11` 镜像。

---

## 4. 安全清单

- [x] `BAIDU_AI_KEY` 仅在服务端，不进前端代码 ✓
- [x] 学生姓名通过 `@anonymize_response` 自动脱敏 ✓
- [x] 钉钉 SSO 后会话签名（HMAC-SHA256）✓
- [ ] **生产环境务必更换** `SESSION_SECRET` 为长随机串
- [ ] **生产环境** `app.run(debug=True)` 改为 gunicorn
- [ ] 学生数据 SQLite 文件做定期备份
- [ ] 钉钉应用配置 "可见范围"，限定学校/年级

---

## 5. API 速查

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/ai/chat` | POST | AI 代理调用（body: `{system, user}`）|
| `/api/ai/status` | GET | AI 是否可用 |
| `/api/auth/dingtalk` | POST | 钉钉 authCode → sessionToken |
| `/api/custom-students` | GET / POST | 自定义学生（按钉钉用户隔离）|
| `/api/custom-students/<id>` | DELETE | 删除自定义学生 |
| `/api/students` | GET / POST | 学生主数据 |
| `/api/students/<id_card>` | GET / PUT / DELETE | 学生详情 |
| `/api/fitness` | GET / POST | 体测数据 |
| `/api/menu?week=N` | GET | 周菜单 |
| `/api/stats` | GET | 概览统计 |
| `/api/privacy/toggle` | POST | 切换脱敏开关 |
