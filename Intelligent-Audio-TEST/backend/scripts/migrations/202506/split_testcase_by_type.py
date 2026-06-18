# -*- coding: utf-8 -*-
"""
拆分测试用例：将混合 API/E2E 的测试用例拆分为两条独立记录

迁移步骤：
1. DDL：为 test_cases 表新增 test_type、related_case_id 字段
2. DDL：为 case_algorithm_params 表新增 scope 字段
3. 数据迁移：识别包含 E2E 音频的混合用例，拆分为 API + E2E 两条记录
   - 原记录保留为 API 记录（test_type='api'）
   - 克隆新记录为 E2E 记录（test_type='e2e'）
   - 双向关联 related_case_id
   - 拆分 config（audios 按类型过滤、dimensions 展平）
   - 拆分 reference_params（api/e2e 键转为 value 键）
   - 复制标签关联到 E2E 记录

使用方法：
    cd Intelligent-Audio-TEST
    python -m backend.scripts.migrations.202506.split_testcase_by_type

或直接：
    python backend/scripts/migrations/202506/split_testcase_by_type.py

注意：此脚本可重复执行（幂等），不会重复拆分已迁移的记录
"""

import os
import sys
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)


def _exec_ddl(conn, sql, success_msg, skip_msg):
    """在独立 SAVEPOINT 中执行 DDL，避免失败污染外层事务"""
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(sql))
        savepoint.commit()
        print(f"  + {success_msg}")
    except Exception as e:
        savepoint.rollback()
        msg = str(e).lower()
        if 'already' in msg or 'duplicate' in msg or 'exists' in msg:
            print(f"  - {skip_msg}")
        else:
            raise


def add_columns(conn):
    """Step 1 & 2: 新增 DDL 字段"""
    print("=== Step 1: 新增 test_cases 字段 ===")

    _exec_ddl(conn,
        "ALTER TABLE test_cases ADD COLUMN test_type VARCHAR(10) NOT NULL DEFAULT 'api'",
        "test_cases.test_type (VARCHAR(10), NOT NULL, DEFAULT 'api')",
        "test_cases.test_type 已存在，跳过")

    _exec_ddl(conn,
        "ALTER TABLE test_cases ADD COLUMN related_case_id VARCHAR(50)",
        "test_cases.related_case_id (VARCHAR(50), NULLABLE)",
        "test_cases.related_case_id 已存在，跳过")

    _exec_ddl(conn,
        "CREATE INDEX ix_test_cases_test_type ON test_cases (test_type)",
        "INDEX ix_test_cases_test_type",
        "INDEX ix_test_cases_test_type 已存在，跳过")

    print("\n=== Step 2: 新增 case_algorithm_params.scope ===")

    _exec_ddl(conn,
        "ALTER TABLE case_algorithm_params ADD COLUMN scope VARCHAR(10) NOT NULL DEFAULT 'common'",
        "case_algorithm_params.scope (VARCHAR(10), NOT NULL, DEFAULT 'common')",
        "case_algorithm_params.scope 已存在，跳过")


def _has_e2e_audios(config):
    """判断 config 是否包含 E2E 音频（混合用例）"""
    if not config or not isinstance(config, dict):
        return False
    audios = config.get('audios', [])
    if not isinstance(audios, list):
        return False
    for audio in audios:
        if isinstance(audio, dict) and audio.get('test_type') == 'e2e':
            return True
    return False


def _is_already_migrated(tc_row):
    """判断记录是否已经迁移过（test_type 已被显式设置）"""
    # 如果 related_case_id 已有值，说明已迁移
    if tc_row.get('related_case_id'):
        return True
    return False


def _split_audios(audios, target_type):
    """按 test_type 过滤音频列表，并移除每项的 test_type 字段"""
    result = []
    for audio in audios:
        if not isinstance(audio, dict):
            continue
        audio_type = audio.get('test_type', 'api')
        if audio_type == target_type:
            clean_audio = {k: v for k, v in audio.items() if k != 'test_type'}
            result.append(clean_audio)
    return result


def _split_dimensions(dimensions, target_type):
    """展平 dimensions 配置
    旧格式: {api: [...], e2e: [...]}
    新格式: [...]（按 target_type 取对应数组）
    """
    if isinstance(dimensions, list):
        # 已经是新格式，直接返回
        return dimensions
    if isinstance(dimensions, dict):
        return dimensions.get(target_type, [])
    return []


def _split_reference_params(ref_params, target_type):
    """拆分 reference_params
    旧格式: [{code, type, api: ..., e2e: ...}, ...]
    新格式: [{code, type, value: ...}, ...]（取 target_type 对应的值）
    """
    if not ref_params or not isinstance(ref_params, list):
        return ref_params

    result = []
    for param in ref_params:
        if not isinstance(param, dict):
            result.append(param)
            continue

        new_param = {}
        for key in ['code', 'type']:
            if key in param:
                new_param[key] = param[key]

        # 取对应 test_type 的值存到 value
        value = param.get(target_type)
        if value is not None:
            new_param['value'] = value
        elif 'value' in param:
            # 已经是新格式
            new_param['value'] = param['value']

        result.append(new_param)

    return result


def migrate_data(conn):
    """Step 3: 拆分混合用例"""
    print("\n=== Step 3: 拆分混合 API/E2E 测试用例 ===")

    # 查询所有未删除的测试用例
    rows = conn.execute(text(
        "SELECT id, name, config, reference_params, test_type, related_case_id "
        "FROM test_cases WHERE deleted = false"
    )).fetchall()

    print(f"  共查询到 {len(rows)} 条未删除用例")

    mixed_cases = []
    for row in rows:
        row_dict = dict(row._mapping)
        config = row_dict.get('config') or {}
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = {}

        if _has_e2e_audios(config) and not _is_already_migrated(row_dict):
            mixed_cases.append(row_dict)

    print(f"  识别到 {len(mixed_cases)} 条混合用例需要拆分")

    if not mixed_cases:
        print("  无需拆分，跳过")
        return

    now = datetime.now(timezone.utc)
    split_count = 0

    for tc in mixed_cases:
        tc_id = tc['id']
        tc_name = tc['name']
        config = tc.get('config') or {}
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = {}

        ref_params = tc.get('reference_params')
        if isinstance(ref_params, str):
            try:
                ref_params = json.loads(ref_params)
            except json.JSONDecodeError:
                ref_params = None

        audios = config.get('audios', [])
        dimensions = config.get('dimensions', [])

        # --- 构建 E2E 配置（原记录保留，E2E 专属配置完整保留） ---
        e2e_config = config.copy()
        e2e_config['audios'] = _split_audios(audios, 'e2e')
        e2e_config['dimensions'] = _split_dimensions(dimensions, 'e2e')

        # --- 构建 API 配置（新记录，仅基础配置，移除 E2E 专属项） ---
        api_id = str(uuid.uuid4())
        api_config = config.copy()
        api_config['audios'] = _split_audios(audios, 'api')
        api_config['dimensions'] = _split_dimensions(dimensions, 'api')
        for e2e_key in ['background_noise']:
            api_config.pop(e2e_key, None)

        # --- 拆分 reference_params ---
        api_ref_params = _split_reference_params(ref_params, 'api')
        e2e_ref_params = _split_reference_params(ref_params, 'e2e')

        # --- 用 SAVEPOINT 隔离每条用例的拆分操作 ---
        sp = conn.begin_nested()
        try:
            # 更新原记录为 E2E（保留完整配置）
            conn.execute(text(
                "UPDATE test_cases SET test_type = 'e2e', related_case_id = :api_id, "
                "config = CAST(:config AS jsonb), reference_params = CAST(:ref AS jsonb), "
                "updated_at = :now "
                "WHERE id = :id"
            ), {
                'api_id': api_id,
                'config': json.dumps(e2e_config, ensure_ascii=False),
                'ref': json.dumps(e2e_ref_params, ensure_ascii=False) if e2e_ref_params else None,
                'now': now,
                'id': tc_id,
            })

            # 查询原记录的完整信息
            full_row = conn.execute(text(
                "SELECT id, name, description, group_id, algorithm_type, algorithm_params "
                "FROM test_cases WHERE id = :id"
            ), {'id': tc_id}).fetchone()
            full_dict = dict(full_row._mapping)

            # 插入新 API 记录（仅基础配置）
            conn.execute(text(
                "INSERT INTO test_cases "
                "(id, name, description, group_id, config, algorithm_type, algorithm_params, "
                "reference_params, test_type, related_case_id, created_at, updated_at, deleted) "
                "VALUES "
                "(:id, :name, :description, :group_id, CAST(:config AS jsonb), :algorithm_type, "
                "CAST(:algorithm_params AS jsonb), CAST(:reference_params AS jsonb), 'api', :related_case_id, "
                ":now, :now, false)"
            ), {
                'id': api_id,
                'name': full_dict['name'],
                'description': full_dict.get('description'),
                'group_id': full_dict.get('group_id'),
                'config': json.dumps(api_config, ensure_ascii=False),
                'algorithm_type': full_dict.get('algorithm_type'),
                'algorithm_params': json.dumps(full_dict.get('algorithm_params'), ensure_ascii=False)
                    if full_dict.get('algorithm_params') else None,
                'reference_params': json.dumps(api_ref_params, ensure_ascii=False)
                    if api_ref_params else None,
                'related_case_id': tc_id,
                'now': now,
            })

            # 复制标签关联到新 API 记录
            tag_rows = conn.execute(text(
                "SELECT tag_id FROM test_case_tags WHERE test_case_id = :id"
            ), {'id': tc_id}).fetchall()

            for tag_row in tag_rows:
                tag_sp = conn.begin_nested()
                try:
                    conn.execute(text(
                        "INSERT INTO test_case_tags (test_case_id, tag_id) VALUES (:tc_id, :tag_id)"
                    ), {'tc_id': api_id, 'tag_id': tag_row[0]})
                    tag_sp.commit()
                except Exception:
                    tag_sp.rollback()

            # 检查并更新引用原 ID 的外键记录
            fk_tables = [
                ('task_case_relations', 'test_case_id'),
                ('test_results', 'test_case_id'),
            ]
            for tbl, col in fk_tables:
                ref_count = conn.execute(text(
                    f"SELECT COUNT(*) FROM {tbl} WHERE {col} = :id"
                ), {'id': tc_id}).scalar()
                if ref_count > 0:
                    print(f"    [WARN] {tbl} 中有 {ref_count} 条记录引用原 ID，将保留指向 E2E 记录")

            sp.commit()
            split_count += 1
            print(f"  [{split_count}] 拆分 '{tc_name}' (id={tc_id[:8]}... -> E2E + API(id={api_id[:8]}...))")
        except Exception as e:
            sp.rollback()
            print(f"  !! 拆分 '{tc_name}' (id={tc_id[:8]}...) 失败: {e}")

    print(f"\n  拆分完成：共拆分 {split_count} 条用例，新增 {split_count} 条 API 记录")


def convert_reference_params(conn):
    """Step 4: 转换所有记录的 reference_params 格式
    旧格式: [{code, type, api: ..., e2e: ...}, ...]
    新格式: [{code, type, value: ...}, ...]
    """
    print("\n=== Step 4: 转换 reference_params 格式 ===")

    rows = conn.execute(text(
        "SELECT id, name, reference_params, test_type "
        "FROM test_cases WHERE deleted = false"
    )).fetchall()

    print(f"  共查询到 {len(rows)} 条未删除用例")
    convert_count = 0

    for row in rows:
        row_dict = dict(row._mapping)
        ref_params = row_dict.get('reference_params')
        test_type = row_dict.get('test_type') or 'api'

        if not ref_params or not isinstance(ref_params, list):
            continue

        # 检查是否有旧格式（包含 api/e2e 键）
        needs_convert = False
        for param in ref_params:
            if isinstance(param, dict) and ('api' in param or 'e2e' in param):
                needs_convert = True
                break

        if not needs_convert:
            continue

        # 转换为新格式
        new_params = []
        for param in ref_params:
            if not isinstance(param, dict):
                new_params.append(param)
                continue

            new_param = {}
            for key in ['code', 'type']:
                if key in param:
                    new_param[key] = param[key]

            # 取对应 test_type 的值
            value = param.get(test_type)
            if value is not None:
                new_param['value'] = value
            elif 'value' in param:
                new_param['value'] = param['value']

            new_params.append(new_param)

        # 更新数据库
        sp = conn.begin_nested()
        try:
            conn.execute(text(
                "UPDATE test_cases SET reference_params = CAST(:params AS jsonb) "
                "WHERE id = :id"
            ), {
                'params': json.dumps(new_params, ensure_ascii=False),
                'id': row_dict['id'],
            })
            sp.commit()
            convert_count += 1
            print(f"  [{convert_count}] 转换 '{row_dict['name']}' (id={row_dict['id'][:8]}...)")
        except Exception as e:
            sp.rollback()
            print(f"  !! 转换 '{row_dict['name']}' (id={row_dict['id'][:8]}...) 失败: {e}")

    print(f"\n  转换完成：共转换 {convert_count} 条记录的 reference_params")


def verify(conn):
    """Step 5: 验证迁移结果"""
    print("\n=== Step 5: 验证迁移结果 ===")

    total = conn.execute(text(
        "SELECT COUNT(*) FROM test_cases WHERE deleted = false"
    )).scalar()

    api_count = conn.execute(text(
        "SELECT COUNT(*) FROM test_cases WHERE deleted = false AND test_type = 'api'"
    )).scalar()

    e2e_count = conn.execute(text(
        "SELECT COUNT(*) FROM test_cases WHERE deleted = false AND test_type = 'e2e'"
    )).scalar()

    linked = conn.execute(text(
        "SELECT COUNT(*) FROM test_cases WHERE deleted = false AND related_case_id IS NOT NULL"
    )).scalar()

    orphaned = conn.execute(text(
        "SELECT COUNT(*) FROM test_cases tc "
        "WHERE tc.deleted = false AND tc.related_case_id IS NOT NULL "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM test_cases tc2 "
        "  WHERE tc2.id = tc.related_case_id AND tc2.deleted = false"
        ")"
    )).scalar()

    # 检查是否还有混合 audios
    all_configs = conn.execute(text(
        "SELECT id, name, config FROM test_cases WHERE deleted = false"
    )).fetchall()

    still_mixed = 0
    for row in all_configs:
        row_dict = dict(row._mapping)
        config = row_dict.get('config') or {}
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                continue
        if _has_e2e_audios(config):
            still_mixed += 1
            print(f"  WARNING: '{row_dict['name']}' (id={row_dict['id'][:8]}...) 仍包含 E2E 音频")

    print(f"\n  总用例数: {total}")
    print(f"  API 用例: {api_count}")
    print(f"  E2E 用例: {e2e_count}")
    print(f"  已关联: {linked}")
    print(f"  孤立关联: {orphaned} {'(WARNING!)' if orphaned > 0 else ''}")
    print(f"  残留混合: {still_mixed} {'(WARNING!)' if still_mixed > 0 else ''}")

    if orphaned == 0 and still_mixed == 0:
        print("\n  ✓ 迁移验证通过")
    else:
        print("\n  ✗ 迁移存在问题，请检查")


def main():
    engine = create_engine(POSTGRES_URI)

    # Step 1 & 2: DDL 在独立事务中执行（避免 "列已存在" 错误污染后续事务）
    with engine.begin() as conn:
        add_columns(conn)

    # Step 3: 数据迁移
    with engine.begin() as conn:
        migrate_data(conn)

    # Step 4: 转换所有记录的 reference_params 格式
    with engine.begin() as conn:
        convert_reference_params(conn)

    # Step 5: 验证
    with engine.connect() as conn:
        verify(conn)

    print("\n=== 迁移完成 ===")


if __name__ == '__main__':
    main()
