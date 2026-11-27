#!/usr/bin/env bash
# 1) 还原数据库（原生 PostgreSQL，无 Docker）
# 用法: DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/intelligent_audio_test bash 01_restore_db.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
DUMP="$DIR/db/intelligent_audio_test.dump"
: "${DATABASE_URL:?请先导出 DATABASE_URL}"
[[ -f "$DUMP" ]] || { echo "缺少 $DUMP"; exit 1; }

echo "==> 还原 $DUMP"
pg_restore --clean --if-exists --no-owner --no-privileges -d "$DATABASE_URL" "$DUMP"
echo "==> 统计"
psql "$DATABASE_URL" -c "select (select count(*) from test_cases where deleted=false) as 在用用例, (select count(*) from audios where deleted=false) as 音频, (select count(*) from tags) as 标签"
