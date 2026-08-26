#!/bin/bash
# 服务器首次初始化脚本 · 在腾讯云服务器上跑一次
# 用法：
#   wget https://raw.githubusercontent.com/<你的用户名>/<repo>/main/server/bootstrap-server.sh
#   chmod +x bootstrap-server.sh
#   sudo ./bootstrap-server.sh <你的 GitHub 仓库 SSH 地址>

set -e

REPO_URL="$1"
if [ -z "$REPO_URL" ]; then
  echo "用法: $0 <git@github.com:user/repo.git>"
  exit 1
fi

DEPLOY_DIR=/opt/baoshan
DEPLOY_USER=${SUDO_USER:-ubuntu}

echo "▶ 1/6 装系统依赖…"
apt-get update -qq
apt-get install -y python3 python3-pip git nginx ufw certbot python3-certbot-nginx

echo "▶ 2/6 克隆仓库到 $DEPLOY_DIR…"
if [ -d "$DEPLOY_DIR/.git" ]; then
  echo "  已存在，跳过"
else
  mkdir -p $(dirname $DEPLOY_DIR)
  git clone "$REPO_URL" "$DEPLOY_DIR"
fi
chown -R $DEPLOY_USER:$DEPLOY_USER $DEPLOY_DIR

echo "▶ 3/6 装 Python 依赖 + gunicorn…"
pip3 install -r $DEPLOY_DIR/requirements.txt
pip3 install gunicorn

echo "▶ 4/6 配置 .env…"
if [ ! -f $DEPLOY_DIR/server/.env ]; then
  cp $DEPLOY_DIR/server/.env.example $DEPLOY_DIR/server/.env
  echo "  ⚠️  $DEPLOY_DIR/server/.env 已创建，请马上 vim 填入真实密钥！"
fi

echo "▶ 5/6 注册 systemd 服务…"
cp $DEPLOY_DIR/server/baoshan.service /etc/systemd/system/baoshan.service
# 替换占位 user（如果 deploy user 不是 ubuntu）
sed -i "s|^User=ubuntu|User=$DEPLOY_USER|" /etc/systemd/system/baoshan.service
systemctl daemon-reload
systemctl enable baoshan
systemctl start baoshan

echo "▶ 6/6 开放防火墙端口…"
ufw allow OpenSSH || true
ufw allow 'Nginx Full' || true

echo ""
echo "✅ 初始化完成！下一步："
echo "   1. 填密钥：sudo vim $DEPLOY_DIR/server/.env"
echo "   2. 配置 Nginx（参考 $DEPLOY_DIR/server/nginx.conf.example）"
echo "   3. 配置 GitHub Secrets（见 docs/腾讯云自动部署.md）"
echo "   4. 申请 HTTPS 证书：sudo certbot --nginx -d your-domain.com"
echo "   5. 检查服务：sudo systemctl status baoshan"
