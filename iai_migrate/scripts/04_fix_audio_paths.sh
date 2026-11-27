#!/usr/bin/env bash
# 2) 修正音频路径：把 122 条 Windows 本地路径改成对象存储 key（迁移包已含对应文件）
# 用法: DATABASE_URL=... bash 04_fix_audio_paths.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
: "${DATABASE_URL:?请先导出 DATABASE_URL}"
psql "$DATABASE_URL" -f "$DIR/db/fix_audio_paths.sql"
psql "$DATABASE_URL" -c "select count(*) as 仍为本地路径 from audios where file_path like 'D:%'"
