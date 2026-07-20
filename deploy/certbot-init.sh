#!/bin/bash
# v1.2: Certbot 首次证书签发
# 用法: DOMAIN=your-domain.com EMAIL=admin@your-domain.com bash deploy/certbot-init.sh
# 前置: DNS A 记录已指向服务器 IP，80 端口已开放

set -e

DOMAIN="${DOMAIN:-example.com}"
EMAIL="${EMAIL:-admin@example.com}"
WEBROOT="/var/www/certbot"

echo "=== AI Quant Trade Certbot Init ==="
echo "Domain: ${DOMAIN}"
echo "Email:  ${EMAIL}"
echo ""

# 确保 webroot 存在
mkdir -p "${WEBROOT}"

# 首次签发（使用 webroot 验证，不中断 nginx）
docker run --rm \
  -v "$(pwd)/deploy/certbot/www:/var/www/certbot" \
  -v "$(pwd)/deploy/certbot/conf:/etc/letsencrypt" \
  certbot/certbot:latest \
  certonly --webroot \
  -w /var/www/certbot \
  -d "${DOMAIN}" \
  --email "${EMAIL}" \
  --agree-tos \
  --non-interactive

echo ""
echo "✅ Certificate obtained for ${DOMAIN}"
echo "Next: restart nginx to apply SSL (docker compose restart nginx)"
