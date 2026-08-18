# -*- coding: utf-8 -*-
"""
修复 param_mappings 表中 source='evaluation' 的脏数据。

根因：前端 autoSaveMapping 在 record.source 为空时回退到 props.componentType='evaluation'，
导致 DB 里出现 source='evaluation' 的记录。但 'evaluation' 是目标类别，不是合法来源。
合法来源只有：case / reference / device / api

修复策略：根据 source_param 在各参数表中反查真实来源，然后 UPDATE。
"""
import os
import sys
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

VALID_SOURCES = ('case', 'reference', 'device', 'api')


def resolve_source(conn, algo_type, source_param):
    """根据 source_param 在各参数表反查真实来源"""
    if not source_param:
        return 'case'

    # case_algorithm_params
    r = conn.execute(text(
        "SELECT 1 FROM case_algorithm_params "
        "WHERE algorithm_type = :at AND param_code = :sp AND deleted = false LIMIT 1"
    ), {'at': algo_type, 'sp': source_param}).fetchone()
    if r:
        return 'case'

    # algorithm_reference_params
    r = conn.execute(text(
        "SELECT 1 FROM algorithm_reference_params "
        "WHERE algorithm_type = :at AND code = :sp AND deleted = false LIMIT 1"
    ), {'at': algo_type, 'sp': source_param}).fetchone()
    if r:
        return 'reference'

    # algorithm_device_params
    r = conn.execute(text(
        "SELECT 1 FROM algorithm_device_params "
        "WHERE algorithm_type = :at AND param_code = :sp AND deleted = false LIMIT 1"
    ), {'at': algo_type, 'sp': source_param}).fetchone()
    if r:
        return 'device'

    # algorithm_api_params
    r = conn.execute(text(
        "SELECT 1 FROM algorithm_api_params "
        "WHERE algorithm_type = :at AND param_code = :sp AND deleted = false LIMIT 1"
    ), {'at': algo_type, 'sp': source_param}).fetchone()
    if r:
        return 'api'

    # 找不到，默认 case
    return 'case'


def main():
    engine = create_engine(POSTGRES_URI)
    conn = engine.connect()

    # 查看修复前状态
    print("=== 修复前 source 分布 ===")
    rows = conn.execute(text(
        "SELECT source, COUNT(*) FROM param_mappings WHERE deleted = false GROUP BY source ORDER BY source"
    )).fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]} 条")

    # 找出所有 source 不合法的记录
    dirty = conn.execute(text(
        "SELECT id, algorithm_type, source, source_param "
        "FROM param_mappings WHERE deleted = false "
        "AND source NOT IN ('case', 'reference', 'device', 'api')"
    )).fetchall()

    print(f"\n=== 需修复记录: {len(dirty)} 条 ===")

    fixed = 0
    for row in dirty:
        mid, algo_type, old_source, source_param = row
        new_source = resolve_source(conn, algo_type, source_param)
        print(f"  id={mid} algo={algo_type} source_param={source_param} "
              f"'{old_source}' -> '{new_source}'")
        conn.execute(text(
            "UPDATE param_mappings SET source = :ns, updated_at = NOW() WHERE id = :id"
        ), {'ns': new_source, 'id': mid})
        fixed += 1

    conn.commit()

    # 查看修复后状态
    print(f"\n=== 修复完成: {fixed} 条已更新 ===")
    rows = conn.execute(text(
        "SELECT source, COUNT(*) FROM param_mappings WHERE deleted = false GROUP BY source ORDER BY source"
    )).fetchall()
    print("=== 修复后 source 分布 ===")
    for r in rows:
        print(f"  {r[0]}: {r[1]} 条")

    conn.close()


if __name__ == '__main__':
    main()
