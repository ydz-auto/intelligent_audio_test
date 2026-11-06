# -*- coding: utf-8 -*-
"""迁移脚本：任务用例被测设备类型历史数据回填（INT-789）

背景（父卡 INT-775 FEAT 评审 17:59 结论；设计口径见
doc/功能设计文档/01_测试执行/05_路由与废弃.md §3.3）：
- task_case_relations.device_type 历史行全量 NULL，导致任务列表「类型」列
  对 E2E 任务误显「API测试」（前端 deriveTaskType 空回退 api）；
- 202610 drop_task_type_and_testcase_test_type.py 的 device_type 回填以
  test_tasks.type 列存在为前提，该列先被删除 → 回填被列存在性门控整体
  SKIP，历史 NULL 行从未补齐（task.type 已废弃，无法再按其回填）；
- 本脚本按关系表确定性回填（设计 §3.3，纯数据修复、不引兼容层）：
  ① task_api_relations → http_api（device_id = api_id）；
  ② 剩余 NULL 行 → task_device_relations → physical（device_id = device_id）；
  ③ http_api 且对应 apis.api_endpoints 含 ws% 前缀 URL → websocket_api；
  合并容器任务（task_merge_relations.merged_task_id 存在）按设计 §3.3 不回填。
- device_id 一并回填（设计 §3.3 原口径：physical=task_device_relations.device_id /
  API=task_api_relations.api_id），供 task_dispatch 重执行时物理设备互斥绑定
  （task_dispatch.py _acquire_physical_device_lock 读 tc_rel.device_id）。
  多设备任务取关系表任一 device_id（设计 §3.3 口径，单设备任务确定性）。
- ①/② 的 WHERE 同时覆盖「device_type 已正确但 device_id 仍 NULL」的部分
  迁移行（device_type 分支不覆写、device_id 仅补 NULL），保证重复执行与
  先补 type 后补 device 的任意执行顺序均收敛到同一终态。

用法：
    python scripts/migrations/202610/backfill_task_case_device_type_int789.py            # 预览（事务内执行并回滚，不落库）
    python scripts/migrations/202610/backfill_task_case_device_type_int789.py --apply    # 执行 UPDATE

幂等性：
    ①/② 只处理 device_type IS NULL 或 device_id IS NULL 的行；③ 只处理
    device_type='http_api' 的行；不覆写既有值、不产生重复数据。执行后重复
    运行三步均命中 0 行。
"""
import argparse
import os
import sys

import psycopg2

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

DEVICE_TYPE_PHYSICAL = 'physical'
DEVICE_TYPE_HTTP_API = 'http_api'
DEVICE_TYPE_WEBSOCKET_API = 'websocket_api'
WS_URL_PREFIX = 'ws%'

# 合并容器任务（按设计 §3.3 不回填，合并报告按 TaskCase.device_type 聚合）
_MERGED_EXCLUDE = """
  AND NOT EXISTS (
      SELECT 1 FROM task_merge_relations tmr
      WHERE tmr.merged_task_id = tcr.task_id
  )
"""

# 各步 WHERE（UPDATE 与事务回滚预览共用同一片段，避免口径漂移）
_WHERE_API = """
  tcr.task_id = tap.task_id
  AND (
      tcr.device_type IS NULL
      OR (tcr.device_type IN (%(http_api)s, %(websocket_api)s) AND tcr.device_id IS NULL)
  )
{merged}
""".replace('{merged}', _MERGED_EXCLUDE)

_WHERE_DEVICE = """
  tcr.task_id = tdr.task_id
  AND (
      tcr.device_type IS NULL
      OR (tcr.device_type = %(physical)s AND tcr.device_id IS NULL)
  )
{merged}
""".replace('{merged}', _MERGED_EXCLUDE)

_WHERE_WS = """
  tcr.device_type = %(http_api)s
  AND tcr.device_id = a.id::text
  AND a.api_endpoints IS NOT NULL
  AND json_typeof(a.api_endpoints) = 'array'
  AND EXISTS (
      SELECT 1 FROM json_array_elements(a.api_endpoints) AS e
      WHERE e->>'url' LIKE %(ws_prefix)s
  )
"""

# ① API 关系 → http_api + api_id（NULL 行补 type；已 http_api/websocket 行补 device_id）
STEP1_API_SQL = f"""
UPDATE task_case_relations tcr
SET device_type = COALESCE(tcr.device_type, '{DEVICE_TYPE_HTTP_API}'),
    device_id = tap.api_id::text
FROM task_api_relations tap
WHERE {_WHERE_API}
"""

# ② 设备关系 → physical + device_id（NULL 行补 type；已 physical 行补 device_id）
STEP2_DEVICE_SQL = f"""
UPDATE task_case_relations tcr
SET device_type = COALESCE(tcr.device_type, '{DEVICE_TYPE_PHYSICAL}'),
    device_id = tdr.device_id::text
FROM task_device_relations tdr
WHERE {_WHERE_DEVICE}
"""

# ③ ws% 前缀识别 → websocket_api（设计 §3.3 step 2，URL 前缀规则配置于本常量）
STEP3_WS_SQL = f"""
UPDATE task_case_relations tcr
SET device_type = '{DEVICE_TYPE_WEBSOCKET_API}'
FROM apis a
WHERE {_WHERE_WS}
"""

_PARAMS = {
    'physical': DEVICE_TYPE_PHYSICAL,
    'http_api': DEVICE_TYPE_HTTP_API,
    'websocket_api': DEVICE_TYPE_WEBSOCKET_API,
    'ws_prefix': WS_URL_PREFIX,
}

STEPS = [
    ('① task_api_relations → http_api（+api_id）', STEP1_API_SQL),
    ('② task_device_relations → physical（+device_id）', STEP2_DEVICE_SQL),
    ('③ apis.api_endpoints url ws% 前缀 → websocket_api', STEP3_WS_SQL),
]


def _params_for(sql):
    # 各步 SQL 引用到的参数子集：从 SQL 文本提取 %(name)s 键
    import re
    names = set(re.findall(r'%\((\w+)\)s', sql))
    return {k: v for k, v in _PARAMS.items() if k in names}


def main(argv=None):
    parser = argparse.ArgumentParser(description='INT-789 历史 task_case_relations.device_type 回填')
    parser.add_argument('--apply', action='store_true', help='真正执行 UPDATE（默认 dry-run 事务内回滚预览）')
    args = parser.parse_args(argv)

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = True
    cur = conn.cursor()
    try:
        for label, update_sql in STEPS:
            params = _params_for(update_sql)
            if args.apply:
                cur.execute(update_sql, params)
                print(f'[EXEC] {label}：{cur.rowcount} 行')
            else:
                # 预览：显式 BEGIN + 逐步 UPDATE + ROLLBACK（psycopg2 隐性事务在
                # 0 行 UPDATE 后不自动 BEGIN，已实测会落库，故预览必须显式 BEGIN）
                cur.execute('BEGIN')
                cur.execute(update_sql, params)
                n = cur.rowcount
                cur.execute('ROLLBACK')
                print(f'[DRY-RUN] {label}：将更新 {n} 行')
    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
