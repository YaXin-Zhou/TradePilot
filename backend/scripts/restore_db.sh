#!/bin/bash
# ============================================================
# AI Quant Trade — PostgreSQL 数据库恢复脚本（N3）
# 用法：
#   docker exec ai_quant_backend bash /app/scripts/restore_db.sh /app/backups/ai_quant_trade_YYYYMMDD_HHMMSS.sql.gz
#
# ⚠️ 警告：恢复会覆盖当前数据库所有数据！请先确认备份文件正确。
# ============================================================
set -euo pipefail

BACKUP_FILE="${1:-}"
DATABASE_URL="${DATABASE_URL:-}"

# 校验参数
if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file.sql.gz>"
    echo "Available backups:"
    ls -1 /app/backups/ai_quant_trade_*.sql.gz 2>/dev/null || echo "  (no backups found)"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE" >&2
    exit 1
fi

if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not set" >&2
    exit 1
fi

# 二次确认
echo "⚠️  WARNING: This will OVERWRITE all data in the database!"
echo "   Target: $DATABASE_URL"
echo "   Backup: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
echo ""
read -p "Are you sure? Type 'CONFIRM' to proceed: " CONFIRM
if [ "$CONFIRM" != "CONFIRM" ]; then
    echo "Aborted."
    exit 0
fi

# 解析 DATABASE_URL
PARSED_URL=$(echo "$DATABASE_URL" | sed 's|postgresql+asyncpg://|postgresql://|')

echo "[$(date)] Starting restore from $BACKUP_FILE..."

# 解压 + psql 恢复
if gunzip -c "$BACKUP_FILE" | psql "$PARSED_URL" 2>&1 | grep -v "^NOTICE\|^SET\|^INSERT\|^CREATE\|^ALTER\|^COPY\|^--" ; then
    echo "[$(date)] Restore OK from $BACKUP_FILE"
else
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date)] Restore completed (with notices)"
    else
        echo "[$(date)] ERROR: Restore failed (exit $EXIT_CODE)" >&2
        exit $EXIT_CODE
    fi
fi

echo "[$(date)] Done."
