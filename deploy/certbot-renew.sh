#!/bin/bash
# v1.2: Certbot 证书自动续期（cron 月度执行）
# 建议 crontab: 0 3 1 * * /bin/bash deploy/certbot-renew.sh

set -e

echo "[$(date)] Starting certbot renewal..."

docker run --rm \
  -v "$(pwd)/deploy/certbot/www:/var/www/certbot" \
  -v "$(pwd)/deploy/certbot/conf:/etc/letsencrypt" \
  certbot/certbot:latest \
  renew --quiet --deploy-hook "nginx -s reload"

echo "[$(date)] Renewal check completed"
