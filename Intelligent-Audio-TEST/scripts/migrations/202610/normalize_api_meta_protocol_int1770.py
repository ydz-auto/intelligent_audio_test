# -*- coding: utf-8 -*-
"""迁移脚本：apis.meta.protocol 存量取值归一化（INT-1770）

背景：
- 前端（旧 Vue FormField / 新 Vue deviceFields）「协议」写入的是传输层词表
  http / https / ws / wss；运行时 `api_test_service/infrastructure/adapters/
  registry.py::infer_protocol` 按适配器维度枚举 `AdapterProtocol`
  （http / websocket / realtime / any）取值，`https` / `ws` / `wss` 直接
  `ValueError`，任何用前端保存过协议的 API 在建任务/选适配器这一步必失败
  （主库 apis.id=1：device_type=http_api、meta={"protocol": "https"}）。
- 卡上裁定走方案 A：协议来源以 `apis.device_type` + 端点 URL 前缀为准，
  `meta.protocol` 降级为只读存量兼容输入。代码侧已按映射兜底
  （https → http、ws/wss → websocket，记 WARNING，不再抛错），本脚本负责把
  存量值一次性回写为标准词表；归一后重复执行命中 0 行。

**已被 INT-1799 取代（2026-10-25，B0 裁定 §3.4.5）**：协议唯一来源改为
`apis.protocol` 列，`infer_protocol` 不再读 `meta.protocol` / 用例级 protocol /
端点前缀，`_LEGACY_PROTOCOL_ALIASES` 随 INT-1770 的只读兼容层一并删除；
INT-1799 的 `add_api_protocol_streaming_int1798.py`（引导链排在 ㊸-1）会把
`apis.meta.protocol` 整键删除。本脚本因此对存量库恒为空转（命中 0 行），
保留只为历史引导链编号稳定（INT-1827 已排定 ㊸~㊽）。

归一映射（INT-1799 起与 `shared/models/common_enums.PROTOCOL_ALIASES` 同口径）：
    https → http
    ws    → websocket
    wss   → websocket
其余取值（http / websocket / realtime / any / 缺失 / 无法识别的旧值）不动。

用法：
    python scripts/migrations/202610/normalize_api_meta_protocol_int1770.py
        # 预览（显式 BEGIN + UPDATE + ROLLBACK，并打印归一前后对照，不落库）
    python scripts/migrations/202610/normalize_api_meta_protocol_int1770.py --apply
        # 真正执行 UPDATE

幂等性：
    只处理 meta->>'protocol' ∈ {https, ws, wss}（大小写不敏感、去首尾空白）的行；
    回写值为标准词表后再次执行命中 0 行。不动其它 meta 键，不碰已标准的值。

注意：
    meta 列是 json（非 jsonb），本脚本经 meta::jsonb 改写后再转回 json，jsonb
    规范化会重排 meta 的键顺序（语义不变）；只对需要归一的行执行。
"""
import argparse
import json
import os
import sys

import psycopg2

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

# 前端传输层词表 → AdapterProtocol 标准值（与 registry._LEGACY_PROTOCOL_ALIASES 同口径）
LEGACY_PROTOCOL_ALIASES = {
    'https': 'http',
    'ws': 'websocket',
    'wss': 'websocket',
}

# 候选行：meta 是对象且 protocol 命中旧词表（含大小写 / 空白变体）
SELECT_CANDIDATES_SQL = """
SELECT id, name, device_type, meta->>'protocol' AS protocol
FROM apis
WHERE json_typeof(meta) = 'object'
  AND json_typeof(meta->'protocol') = 'string'
  AND lower(btrim(meta->>'protocol')) = ANY(%(legacy)s)
ORDER BY id
"""

UPDATE_SQL = """
UPDATE apis
SET meta = jsonb_set(meta::jsonb, '{protocol}', to_jsonb(%(new_protocol)s::text))::json
WHERE id = %(id)s
"""


def normalize_protocol_value(value):
    """旧词表 → 标准词表；无需归一（含无法识别）返回 None。"""
    if value is None:
        return None
    return LEGACY_PROTOCOL_ALIASES.get(str(value).strip().lower())


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='INT-1770 apis.meta.protocol 存量取值归一化')
    parser.add_argument('--apply', action='store_true',
                        help='真正执行 UPDATE（默认 dry-run，事务内执行后回滚）')
    args = parser.parse_args(argv)

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(SELECT_CANDIDATES_SQL, {'legacy': sorted(LEGACY_PROTOCOL_ALIASES)})
        rows = cur.fetchall()
        print(f'[{"EXEC" if args.apply else "DRY-RUN"}] 命中待归一 meta.protocol 行：{len(rows)}')
        if rows:
            print('  id | device_type | 归一前 → 归一后 | name')
            for api_id, name, device_type, protocol in rows:
                target = normalize_protocol_value(protocol)
                print(f'  {api_id} | {device_type} | {protocol!r} → {target!r} | {name}')

        if args.apply:
            changed = 0
            for api_id, _name, _device_type, protocol in rows:
                target = normalize_protocol_value(protocol)
                if target is None:
                    continue
                cur.execute(UPDATE_SQL, {'id': api_id, 'new_protocol': target})
                changed += cur.rowcount
            print(f'[EXEC] 已更新 {changed} 行')
        else:
            # 预览：显式 BEGIN + UPDATE + 回读 + ROLLBACK（0 行 UPDATE 后
            # psycopg2 隐性事务不自动 BEGIN，会直接落库，故必须显式 BEGIN）
            cur.execute('BEGIN')
            try:
                for api_id, _name, _device_type, protocol in rows:
                    target = normalize_protocol_value(protocol)
                    if target is None:
                        continue
                    cur.execute(UPDATE_SQL, {'id': api_id, 'new_protocol': target})
                cur.execute(
                    "SELECT id, meta->>'protocol' FROM apis WHERE id = ANY(%s) ORDER BY id",
                    ([r[0] for r in rows],) if rows else ([-1],))
                after = cur.fetchall()
                print('[DRY-RUN] 事务内回读（将回滚）：'
                      + json.dumps(dict(after), ensure_ascii=False))
            finally:
                cur.execute('ROLLBACK')
            print('[DRY-RUN] 已回滚，未落库（--apply 执行）')
    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
