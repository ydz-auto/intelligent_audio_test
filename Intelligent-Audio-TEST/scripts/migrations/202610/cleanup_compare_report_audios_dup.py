# -*- coding: utf-8 -*-
"""
存量对比报告 report_cases.audios 重复数据清洗（INT-135）
=============================================================================

背景：
  INT-134（commit 6cbd9dec）修复了 ReportHelpers._build_audios_list compare
  分支同一音频项 append 后又 extend(round_dry) 二次入列的缺陷，但修复只对
  新生成的报告生效；修复前落库的对比报告（comparison / secondary_comparison）
  的 report_cases.audios 中，同一音频 dict 会以相邻两份出现，前端
  AudioTimelineVisualization 对这些历史报告仍会渲染上下两层同位段。

清洗口径（与 INT-134 修复后生成侧输出一致）：
  - 仅处理未删除、type IN ('comparison', 'secondary_comparison') 报告的
    report_cases.audios 数组；task 报告与已删除报告不在范围
  - 对象级去重：按 dict 的规范化 JSON（sort_keys）识别同一项，保留首见项、
    保持原顺序。缺陷引入的重复是同一 dict 的紧邻两份引用，去重后布局与
    修复后生成侧完全一致（每音频恰好一次；噪声段每轮一条、位于末尾，
    天然唯一不受影响）
  - 只写 audios 数组字段，其余字段一律不触碰
  - 幂等：清洗后不存在重复项，重复执行为 no-op

用法：
    python scripts/migrations/202610/cleanup_compare_report_audios_dup.py           # dry-run 预览（默认）
    python scripts/migrations/202610/cleanup_compare_report_audios_dup.py --apply   # 实际清洗

--apply 行为：
  ① 将全部受影响 case 行（report_id / case_id / 原始 audios）备份为 JSON 文件
     （--backup-dir 指定目录，默认当前目录 backups_compare_audios_cleanup/）
  ② 单事务逐行 UPDATE report_cases SET audios = 去重后列表
  ③ 清洗后复核扫描（应 0 重复），并在备份目录留档执行记录 exec_record_<时间戳>.json

⚠️ 建议执行前暂停 report_service / api_gateway 的报告生成写入，避免清洗期间
   并发生成对比报告导致统计口径漂移（不停服无数据风险，仅统计可能偏少）。
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime

from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test'
)

COMPARE_REPORT_TYPES = ('comparison', 'secondary_comparison')

SCAN_SQL = text(
    "SELECT r.id AS report_id, r.name AS report_name, r.type AS report_type, "
    "       c.id AS case_id, c.audios AS audios "
    "FROM report_cases c "
    "JOIN test_reports r ON r.id = c.report_id "
    "WHERE r.type = ANY(:types) AND r.deleted = false AND c.audios IS NOT NULL "
    "ORDER BY r.id, c.id"
)

DELETED_COMPARE_REPORTS_SQL = text(
    "SELECT count(*) FROM test_reports "
    "WHERE type = ANY(:types) AND deleted = true"
)


def canonical_key(item):
    """音频项 → 规范化 JSON 串，作为对象级同一性判据。"""
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


def dedup_audios(audios):
    """对象级去重：保留首见项、保持原顺序。返回 (去重后列表, 移除数)。"""
    seen = set()
    kept = []
    removed = 0
    for item in audios:
        key = canonical_key(item)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        kept.append(item)
    return kept, removed


def scan(conn):
    """扫描 compare 报告的 report_cases.audios，返回 (受影响行列表, 汇总统计)。"""
    types = list(COMPARE_REPORT_TYPES)
    rows = conn.execute(SCAN_SQL, {'types': types}).mappings().all()
    skipped_deleted_reports = conn.execute(
        DELETED_COMPARE_REPORTS_SQL, {'types': types}).scalar()

    affected = []
    reports = {}
    cases_scanned = 0
    items_total = 0
    dups_total = 0
    for row in rows:
        audios = row['audios']
        if not isinstance(audios, list):
            continue
        cases_scanned += 1
        items_total += len(audios)
        kept, removed = dedup_audios(audios)
        st = reports.setdefault(row['report_id'], {
            'report_name': row['report_name'],
            'report_type': row['report_type'],
            'cases': 0, 'affected_cases': 0,
            'items_before': 0, 'items_after': 0, 'dups_removed': 0,
        })
        st['cases'] += 1
        st['items_before'] += len(audios)
        st['items_after'] += len(kept)
        if removed:
            st['affected_cases'] += 1
            st['dups_removed'] += removed
            dups_total += removed
            affected.append({
                'report_id': row['report_id'],
                'report_name': row['report_name'],
                'report_type': row['report_type'],
                'case_id': row['case_id'],
                'items_before': len(audios),
                'items_after': len(kept),
                'dups_removed': removed,
                'audios_original': audios,
            })

    stats = {
        'mode': None,
        'scanned_at': datetime.now().isoformat(),
        'report_types': list(COMPARE_REPORT_TYPES),
        'reports_scanned': len(reports),
        'reports_affected': sum(1 for s in reports.values() if s['affected_cases']),
        'cases_scanned': cases_scanned,
        'cases_affected': len(affected),
        'audio_items_total': items_total,
        'audio_items_after': items_total - dups_total,
        'duplicates_removed': dups_total,
        'skipped_deleted_compare_reports': skipped_deleted_reports or 0,
        'per_report': [
            {'report_id': rid, **st}
            for rid, st in sorted(reports.items())
        ],
    }
    return affected, stats


def print_stats(stats):
    print(f"  扫描报告数（未删除 compare 类）: {stats['reports_scanned']}")
    print(f"  扫描 case 数（audios 非空）    : {stats['cases_scanned']}")
    print(f"  音频项总数                     : {stats['audio_items_total']}")
    print(f"  受影响报告数                   : {stats['reports_affected']}")
    print(f"  受影响 case 数                 : {stats['cases_affected']}")
    print(f"  待移除重复音频项数             : {stats['duplicates_removed']}")
    print(f"  （跳过已删除 compare 报告      : {stats['skipped_deleted_compare_reports']} 个）")
    for st in stats['per_report']:
        mark = ' <-- 受影响' if st['affected_cases'] else ''
        print(f"  - 报告 {st['report_id']} [{st['report_type']}] "
              f"cases={st['cases']} items={st['items_before']}"
              f"{'->' + str(st['items_after']) if st['affected_cases'] else ''}"
              f" dups={st['dups_removed']}{mark}")


def main():
    parser = argparse.ArgumentParser(
        description='存量对比报告 report_cases.audios 重复数据清洗（INT-135，默认 dry-run）')
    parser.add_argument('--apply', action='store_true',
                        help='实际执行清洗（默认 dry-run 仅扫描预览）')
    parser.add_argument('--backup-dir',
                        default=os.path.join('backups_compare_audios_cleanup'),
                        help='--apply 时受影响行备份与执行记录的输出目录'
                             '（默认 ./backups_compare_audios_cleanup/）')
    args = parser.parse_args()
    apply_mode = args.apply

    print("=" * 64)
    print("存量对比报告 audios 重复数据清洗（INT-135）")
    print(f"模式: {'实际清洗 (--apply)' if apply_mode else '预览 (dry-run)'}")
    print(f"目标库: {POSTGRES_URI.split('@')[-1]}")
    print("=" * 64)

    engine = create_engine(POSTGRES_URI)
    with engine.connect() as conn:
        affected, stats = scan(conn)
        stats['mode'] = 'apply' if apply_mode else 'dry-run'

        print("\n[1] 扫描统计")
        print_stats(stats)

        if not affected:
            print("\n[2] 无受影响数据：当前库不存在 audios 内同一对象重复入列的"
                  " compare 报告，无需清洗。")
            if apply_mode:
                print("    --apply 在 0 受影响行时为 no-op，未执行任何写入、未生成备份。")
            return

        print("\n[2] 受影响明细（报告 / case / 音频项数变化）")
        for a in affected:
            print(f"  - 报告 {a['report_id']}「{a['report_name']}」 "
                  f"case {a['case_id']}: {a['items_before']} -> {a['items_after']} "
                  f"(移除 {a['dups_removed']} 个重复项)")

        if not apply_mode:
            print("\n[dry-run] 未做任何写入。确认无误后加 --apply 执行。")
            return

        os.makedirs(args.backup_dir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(args.backup_dir, f'backup_{ts}.json')
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump({'scanned_at': stats['scanned_at'], 'affected': affected},
                      f, ensure_ascii=False, indent=2)
        print(f"\n[3] 已备份受影响行原始 audios -> {backup_path}")

        print("[4] 执行清洗（单事务）")
        for a in affected:
            kept, _ = dedup_audios(a['audios_original'])
            conn.execute(text("UPDATE report_cases SET audios = CAST(:audios AS json) "
                              "WHERE id = :case_id"),
                         {'audios': json.dumps(kept, ensure_ascii=False),
                          'case_id': a['case_id']})
        conn.commit()
        print(f"    已更新 {len(affected)} 行 report_cases.audios")

        print("[5] 清洗后复核扫描")
        affected_after, stats_after = scan(conn)
        if affected_after:
            print(f"    !! 复核仍发现 {len(affected_after)} 行存在重复，"
                  f"请检查是否有并发生成写入")
            sys.exit(1)
        print(f"    复核通过：重复项 0（duplicates_removed=0），脚本幂等可重复执行")

        record_path = os.path.join(args.backup_dir, f'exec_record_{ts}.json')
        with open(record_path, 'w', encoding='utf-8') as f:
            json.dump({'before': stats, 'after': stats_after,
                       'backup_file': backup_path}, f, ensure_ascii=False, indent=2)
        print(f"\n[完成] 执行记录已留档 -> {record_path}")


if __name__ == '__main__':
    main()
