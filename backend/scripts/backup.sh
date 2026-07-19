#!/bin/bash
# AI Quant Trade — 数据库备份脚本
# 用法: ./backup.sh （建议加 crontab: 0 3 * * * /path/to/backup.sh）
set -e

BACKUP_DIR="$(dirname "$0")/../backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/ai_quant_trade_$TIMESTAMP.sql.gz"

mkdir -p "$BACKUP_DIR"

# 从环境变量读取数据库配置
DB_URL="${DATABASE_URL:-postgresql+asyncpg://root:root@127.0.0.1:5432/ai_quant_trade}"

# 提取连接信息
DB_USER=$(echo "$DB_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
DB_PASS=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
DB_HOST=$(echo "$DB_URL" | sed -n 's|.*@\([^:]*\):.*|\1|p')
DB_PORT=$(echo "$DB_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
DB_NAME=$(echo "$DB_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')

echo "Backing up $DB_NAME at $DB_HOST:$DB_PORT to $BACKUP_FILE"

PGPASSWORD="$DB_PASS" pg_dump -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" "$DB_NAME" | gzip > "$BACKUP_FILE"

echo "Backup complete: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# 清理 7 天前的备份
find "$BACKUP_DIR" -name "ai_quant_trade_*.sql.gz" -mtime +7 -delete
echo "Cleaned backups older than 7 days"
