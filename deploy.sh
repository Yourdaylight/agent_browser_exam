#!/bin/bash
set -e

# ============================================================
# Agent Browser Exam — 部署到远程服务器
# 目标: browserexam.clawtown.cn (43.132.178.232)
# 方式: rsync 代码 + uv 安装依赖 + uvicorn(内网) + nginx(HTTPS) + 自签证书
# ============================================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
REMOTE_IP="43.132.178.232"
REMOTE_USER="root"
REMOTE_PASS="lightclaw@1234"
REMOTE_APP_DIR="/opt/agent-browser-exam"
DOMAIN="browserexam.clawtown.cn"

echo "=== 同步代码到远端 ==="
sshpass -p "$REMOTE_PASS" ssh -o StrictHostKeyChecking=no -p 22 ${REMOTE_USER}@${REMOTE_IP} "mkdir -p $REMOTE_APP_DIR"
sshpass -p "$REMOTE_PASS" rsync -avz --delete \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.git' \
  --exclude='.codebuddy' \
  --exclude='*.db' \
  --exclude='*.log' \
  --exclude='servers.conf' \
  --exclude='deploy.sh' \
  --exclude='Dockerfile' \
  --exclude='.dockerignore' \
  -e "sshpass -p '$REMOTE_PASS' ssh -o StrictHostKeyChecking=no -p 22" \
  "$PROJECT_DIR/" "${REMOTE_USER}@${REMOTE_IP}:${REMOTE_APP_DIR}/"

echo "=== 远端安装依赖并启动 ==="
sshpass -p "$REMOTE_PASS" ssh -o StrictHostKeyChecking=no -p 22 ${REMOTE_USER}@${REMOTE_IP} bash -s << 'DEPLOY'
set -e

APP_DIR="/opt/agent-browser-exam"
DOMAIN="browserexam.clawtown.cn"
SSL_DIR="/etc/nginx/ssl"
cd "$APP_DIR"

# ---- 安装 uv（如果没有） ----
if ! command -v uv &>/dev/null; then
  echo "--- 安装 uv ---"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# ---- 创建虚拟环境并安装依赖 ----
echo "--- 安装依赖 ---"
uv venv .venv --python 3.11 2>/dev/null || true
source .venv/bin/activate
uv pip install -r requirements.txt

# ---- 数据目录 ----
mkdir -p /data/exam

# ---- 停止旧进程 ----
pkill -f "uvicorn server.main:app" 2>/dev/null || true
sleep 1

# ---- 启动 uvicorn（监听 127.0.0.1:8080，仅内网） ----
echo "--- 启动服务 ---"
export EXAM_BASE_URL="https://browserexam.clawtown.cn"
export EXAM_DB_PATH="/data/exam/exam.db"
export EXAM_HMAC_SECRET="$(cat /data/exam/.hmac_secret 2>/dev/null || (head -c 32 /dev/urandom | xxd -p | tee /data/exam/.hmac_secret))"

nohup .venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8080 > /data/exam/app.log 2>&1 &
sleep 2

# ---- 验证 uvicorn ----
HEALTH=$(curl -s http://127.0.0.1:8080/api/health)
echo "uvicorn: $HEALTH"

# ---- 安装 nginx（如果没有） ----
if ! command -v nginx &>/dev/null; then
  echo "--- 安装 nginx ---"
  yum install -y nginx || dnf install -y nginx || true
fi

# ---- 自签证书 ----
mkdir -p "$SSL_DIR"
if [ ! -f "$SSL_DIR/${DOMAIN}.crt" ]; then
  echo "--- 生成自签证书 ---"
  openssl req -x509 -nodes -days 3650 \
    -newkey rsa:2048 \
    -keyout "$SSL_DIR/${DOMAIN}.key" \
    -out "$SSL_DIR/${DOMAIN}.crt" \
    -subj "/CN=${DOMAIN}" \
    -addext "subjectAltName=DNS:${DOMAIN},DNS:*.${DOMAIN},IP:43.132.178.232" 2>/dev/null || \
  openssl req -x509 -nodes -days 3650 \
    -newkey rsa:2048 \
    -keyout "$SSL_DIR/${DOMAIN}.key" \
    -out "$SSL_DIR/${DOMAIN}.crt" \
    -subj "/CN=${DOMAIN}"
  echo "证书已生成: $SSL_DIR/${DOMAIN}.crt"
fi

# ---- nginx 配置（仅 HTTPS，80 端口未放行） ----
cat > /etc/nginx/conf.d/browserexam.conf << 'NGINX'
server {
    listen 443 ssl;
    server_name browserexam.clawtown.cn;

    ssl_certificate     /etc/nginx/ssl/browserexam.clawtown.cn.crt;
    ssl_certificate_key /etc/nginx/ssl/browserexam.clawtown.cn.key;
    ssl_protocols       TLSv1.2 TLSv1.3;

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX

# ---- 启动/重载 nginx ----
nginx -t
pkill nginx 2>/dev/null; sleep 1; nginx
systemctl enable nginx 2>/dev/null || true

echo "=== 部署完成 ==="
echo "https://${DOMAIN}"
DEPLOY
