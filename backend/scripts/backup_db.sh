#!/bin/bash
# ============================================================
# AI Quant Trade — PostgreSQL 数据库备份脚本（N3）
# 用法：
#   手动：docker exec ai_quant_backend bash /app/scripts/backup_db.sh
#   定时：crontab -e → 0 3 * * * docker exec ai_quant_backend bash /app/scripts/backup_db.sh
# ============================================================
set -euo pipefail

# 从环境变量读取配置
DATABASE_URL="${DATABASE_URL:-}"
BACKUP_DIR="${BACKUP_DIR:-/app/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/ai_quant_trade_${TIMESTAMP}.sql.gz"

# 校验
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not set" >&2
    exit 1
fi

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 执行备份
echo "[$(date)] Starting backup → $BACKUP_FILE"

# 解析 DATABASE_URL（支持 postgresql+asyncpg:// 和 postgresql://）
PARSED_URL=$(echo "$DATABASE_URL" | sed 's|postgresql+asyncpg://|postgresql://|')

# pg_dump + gzip
if pg_dump "$PARSED_URL" 2>/dev/null | gzip > "$BACKUP_FILE"; then
    FILESIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[$(date)] Backup OK: $BACKUP_FILE ($FILESIZE)"
else
    echo "[$(date)] ERROR: Backup failed" >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

# 清理过期备份
echo "[$(date)] Cleaning backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "ai_quant_trade_*.sql.gz" -mtime +${RETENTION_DAYS} -print -delete

# 列出当前备份
echo "[$(date)] Current backups:"
ls -lh "$BACKUP_DIR"/ai_quant_trade_*.sql.gz 2>/dev/null | awk '{print "  "$NF" ("$5")"}'

echo "[$(date)] Done."
