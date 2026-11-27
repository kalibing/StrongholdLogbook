#!/usr/bin/env bash
# 生成 Docker Compose 用的 .env：随机数据库密码与凭据密钥，权限 600。
# 用法：scripts/init-env.sh [域名]
#   scripts/init-env.sh logbook.example.com   # 公网 HTTPS：监听 0.0.0.0:80/443，Caddy 自动申请证书
#   scripts/init-env.sh                       # 仅本机测试：http://localhost:8080
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -e .env ]]; then
  echo ".env 已存在，未覆盖（密钥丢失会导致已保存的令牌无法解密）" >&2
  exit 1
fi

random_b64() { head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '\n'; }
password=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40)
key=$(random_b64)

domain=${1:-}
if [[ -n $domain ]]; then
  site="$domain"; origin="https://$domain"; bind=0.0.0.0; http=80; https=443
else
  site="http://localhost"; origin="http://localhost:8080"; bind=127.0.0.1; http=8080; https=8443
fi

umask 077
sed -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$password|" \
    -e "s|^LOGBOOK_CREDENTIAL_KEY=.*|LOGBOOK_CREDENTIAL_KEY=$key|" \
    -e "s|^SITE_ADDRESS=.*|SITE_ADDRESS=$site|" \
    -e "s|^PUBLIC_ORIGIN=.*|PUBLIC_ORIGIN=$origin|" \
    -e "s|^HOST_BIND=.*|HOST_BIND=$bind|" \
    -e "s|^HTTP_PORT=.*|HTTP_PORT=$http|" \
    -e "s|^HTTPS_PORT=.*|HTTPS_PORT=$https|" \
    .env.example > .env
chmod 600 .env
mkdir -p deploy/download

echo "已生成 .env（600）：SITE_ADDRESS=$site  PUBLIC_ORIGIN=$origin  监听 $bind:$http/$https"
echo "请把 LOGBOOK_CREDENTIAL_KEY 另外备份一份，与数据库备份分开保管。"
