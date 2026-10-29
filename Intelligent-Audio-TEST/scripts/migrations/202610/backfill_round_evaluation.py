# -*- coding: utf-8 -*-
"""回填脚本：多轮结果 algorithm_result.rounds[].evaluation

背景：逐轮评估分数只落在 test_result_dimensions，历史数据未回填到
TestResult.algorithm_result.rounds[].evaluation。重新评估按该字段判断"本轮是否
有评估数据"，缺失时会跳过整轮（全量重评还会先清空旧评分），导致重评零提交、
评分丢失。

口径（与在线写回一致：evaluation_service RoundAggregator）：
- 目标行：algorithm_result.rounds 为非空数组，且存在轮次缺 evaluation（API / E2E 统一字段）；
- 逐轮键：dimensions.name 小写、空格/短横线转下划线；
- 分数：test_result_dimensions.evaluation_status='completed' 且 score 非空，
  按 round_number（0 基，与 rounds 下标对齐）归组；
- 幂等：只补齐缺失/为空的 evaluation，已有值不覆盖，可重复执行。

用法：
    # 预览（只读）
    python scripts/migrations/202610/backfill_round_evaluation.py
    # 执行
    python scripts/migrations/202610/backfill_round_evaluation.py --apply
    # 分批 / 限速（大库避免与在线评估抢 IO）
    python scripts/migrations/202610/backfill_round_evaluation.py --apply \
        --limit 5000 --batch-size 500 --sleep 0.2

环境：DATABASE_URL（或 DATABASE_URI）
退出码：0 成功；1 参数/连接错误
"""
import argparse
import json
import os
import sys
import time
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BATCH_SIZE = 500
DEFAULT_SLEEP_SECONDS = 0.0
DEFAULT_SCAN_LIMIT = 1000000

_CANDIDATE_SQL = """
SELECT id, algorithm_result
FROM test_results
WHERE algorithm_result IS NOT NULL
  AND jsonb_typeof(algorithm_result::jsonb -> 'rounds') = 'array'
  AND jsonb_array_length(algorithm_result::jsonb -> 'rounds') > 0
  -- 只取仍有轮次缺 evaluation 的行，保证 --limit 分批可推进
  AND EXISTS (
      SELECT 1
      FROM jsonb_array_elements(algorithm_result::jsonb -> 'rounds') AS r
      WHERE r -> 'evaluation' IS NULL
         OR r -> 'evaluation' = '{}'::jsonb
  )
ORDER BY id
LIMIT %s
"""

_SCORE_SQL = """
SELECT trd.round_number,
       COALESCE(d.name, trd.dimension_id::text) AS dim_name,
       trd.score
FROM test_result_dimensions trd
LEFT JOIN dimensions d ON d.id = trd.dimension_id
WHERE trd.test_result_id = %s
  AND trd.round_number IS NOT NULL
  AND trd.evaluation_status = 'completed'
  AND trd.score IS NOT NULL
"""


def _round_eval_key(dim_name):
    """维度名 → 逐轮评估字典键（与 RoundAggregator._round_eval_key 一致）"""
    return str(dim_name).lower().replace(' ', '_').replace('-', '_')


def _connect():
    database_url = os.environ.get('DATABASE_URL') or os.environ.get('DATABASE_URI')
    if not database_url:
        print('[ERROR] 未配置 DATABASE_URL / DATABASE_URI')
        sys.exit(1)
    parsed = urlparse(database_url)
    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'),
        user=parsed.username,
        password=parsed.password,
    )


def _load_round_evals(cur, result_id):
    """读取某结果的逐轮分数：{round_number: {维度键: 分数}}"""
    cur.execute(_SCORE_SQL, (result_id,))
    round_evals = {}
    for round_number, dim_name, score in cur.fetchall():
        round_evals.setdefault(int(round_number), {})[_round_eval_key(dim_name)] = score
    return round_evals


def _needs_backfill(rounds):
    """是否存在需要补的轮次（evaluation 缺失或为空）"""
    for round_item in rounds:
        if isinstance(round_item, dict) and not round_item.get('evaluation'):
            return True
    return False


def _merge_round_evaluation(rounds, round_evals):
    """把逐轮分数合并进 rounds[].evaluation（已有值不覆盖）。返回改动轮次数"""
    changed = 0
    for idx, round_item in enumerate(rounds):
        if not isinstance(round_item, dict) or round_item.get('evaluation'):
            continue
        evals = round_evals.get(idx)
        if not evals:
            continue
        round_item['evaluation'] = evals
        changed += 1
    return changed


def backfill(apply_changes=False, limit=None, batch_size=DEFAULT_BATCH_SIZE,
             sleep_seconds=DEFAULT_SLEEP_SECONDS):
    conn = _connect()
    conn.autocommit = False
    cur = conn.cursor()

    scanned = 0
    changed_results = 0
    changed_rounds = 0
    batch_since_commit = 0

    try:
        page_size = int(limit) if limit else DEFAULT_SCAN_LIMIT
        cur.execute(_CANDIDATE_SQL, (page_size,))
        rows = cur.fetchall()

        for result_id, algorithm_result in rows:
            scanned += 1
            if isinstance(algorithm_result, str):
                algorithm_result = json.loads(algorithm_result)
            if not isinstance(algorithm_result, dict):
                continue
            rounds = algorithm_result.get('rounds')
            if not isinstance(rounds, list) or not _needs_backfill(rounds):
                continue

            round_evals = _load_round_evals(cur, result_id)
            if not round_evals:
                continue

            changed = _merge_round_evaluation(rounds, round_evals)
            if not changed:
                continue

            changed_results += 1
            changed_rounds += changed

            if apply_changes:
                cur.execute(
                    "UPDATE test_results SET algorithm_result = %s::jsonb WHERE id = %s",
                    (json.dumps(algorithm_result, ensure_ascii=False), result_id),
                )
                batch_since_commit += 1
                if batch_since_commit >= batch_size:
                    conn.commit()
                    batch_since_commit = 0
                    if sleep_seconds:
                        time.sleep(sleep_seconds)

        if apply_changes:
            conn.commit()
        else:
            conn.rollback()

        print(f"[{'APPLY' if apply_changes else 'DRY-RUN'}] 扫描结果 {scanned} 条，"
              f"需回填 {changed_results} 条 / 轮次 {changed_rounds} 个")
        return 0
    except Exception as e:
        conn.rollback()
        print(f'[ERROR] 回填失败: {e}')
        return 1
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='回填多轮结果 rounds[].evaluation')
    parser.add_argument('--apply', action='store_true', help='实际写库（缺省只预览）')
    parser.add_argument('--limit', type=int, default=None, help='单次扫描结果条数上限')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                        help=f'每批提交条数（默认 {DEFAULT_BATCH_SIZE}）')
    parser.add_argument('--sleep', type=float, default=DEFAULT_SLEEP_SECONDS,
                        help='每批提交后休眠秒数（默认 0）')
    args = parser.parse_args()
    sys.exit(backfill(
        apply_changes=args.apply,
        limit=args.limit,
        batch_size=args.batch_size,
        sleep_seconds=args.sleep,
    ))


if __name__ == '__main__':
    main()
