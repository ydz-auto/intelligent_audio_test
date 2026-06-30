"""
迁移脚本：将所有旧格式 reference_params 统一为新格式

处理目标：
1. static/ref_params/*.json 文件 — 归一化为标准 list [{code, type, value}]
2. TestCase.config — 清理顶层旧 reference_params 字段
3. ReportCase.reference_params — 保持 dict 格式，但清理 api/e2e 字段，补 value

使用方法：
    python migrate_ref_params_format.py --dry-run     # 预览，不修改
    python migrate_ref_params_format.py               # 正式执行
    python migrate_ref_params_format.py --files-only  # 只处理文件
    python migrate_ref_params_format.py --db-only     # 只处理数据库
"""
import sys
import os
import json
import glob
import argparse

sys.path.insert(0, '.')

from backend.utils.algorithm.reference_params_generator import normalize_reference_params


def _is_legacy_file_format(data):
    """检查 list 格式的 JSON 文件是否含旧 api/e2e 字段"""
    if not isinstance(data, list):
        return False
    for item in data:
        if isinstance(item, dict) and ('api' in item or 'e2e' in item):
            return True
    return False


def _clean_report_ref_params(ref_params):
    """清理 ReportCase.reference_params (dict 格式) 中的旧 api/e2e 字段，保持 dict 结构"""
    if not isinstance(ref_params, dict):
        return ref_params, False
    changed = False
    for code, info in ref_params.items():
        if not isinstance(info, dict):
            continue
        if 'value' not in info or info.get('value') is None:
            if 'api' in info or 'e2e' in info:
                info['value'] = info.get('api') or info.get('e2e')
                info.pop('api', None)
                info.pop('e2e', None)
                info.pop('test_type', None)
                changed = True
        elif 'api' in info or 'e2e' in info:
            info.pop('api', None)
            info.pop('e2e', None)
            info.pop('test_type', None)
            changed = True
    return ref_params, changed


def migrate_files(dry_run=False):
    """迁移 static/ref_params/*.json 文件"""
    ref_dir = os.path.join(os.path.dirname(__file__), 'static', 'ref_params')
    pattern = os.path.join(ref_dir, '*.json')
    files = glob.glob(pattern)

    stats = {'total': len(files), 'legacy': 0, 'migrated': 0, 'skipped': 0, 'errors': 0}

    print(f"\n=== 扫描 JSON 文件 ({len(files)} 个) ===")

    for filepath in files:
        fname = os.path.basename(filepath)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"  [ERROR] {fname}: 读取失败 {e}")
            stats['errors'] += 1
            continue

        if not isinstance(data, list):
            print(f"  [SKIP] {fname}: 非 list 格式 ({type(data).__name__})")
            stats['skipped'] += 1
            continue

        if not _is_legacy_file_format(data):
            stats['skipped'] += 1
            continue

        stats['legacy'] += 1
        normalized = normalize_reference_params(data, test_type='api')

        if dry_run:
            codes = [p.get('code') for p in normalized]
            print(f"  [DRY] {fname}: 旧格式 → 新格式, codes={codes}")
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            print(f"  [OK]  {fname}: 已迁移")
        stats['migrated'] += 1

    print(f"\n文件统计: 总计={stats['total']}, 旧格式={stats['legacy']}, "
          f"已迁移={stats['migrated']}, 跳过={stats['skipped']}, 错误={stats['errors']}")
    return stats


def migrate_database(dry_run=False):
    """迁移数据库中的 reference_params"""
    from backend.app import create_app
    from backend.models.models import TestCase, ReportCase
    from backend.models.database import db

    app = create_app()
    stats = {'tc_total': 0, 'tc_updated': 0, 'rc_total': 0, 'rc_updated': 0}

    with app.app_context():
        # 1. TestCase.config — 清理顶层旧 reference_params
        cases = TestCase.query.filter_by(deleted=False).all()
        stats['tc_total'] = len(cases)
        print(f"\n=== 扫描 TestCase ({len(cases)} 条) ===")

        for tc in cases:
            config = tc.config or {}
            if not isinstance(config, dict):
                continue

            ref_params = config.get('reference_params')
            if ref_params is None:
                continue

            normalized = normalize_reference_params(ref_params, test_type=tc.test_type or 'api')
            config['reference_params'] = normalized

            if not dry_run:
                tc.config = config
            stats['tc_updated'] += 1
            print(f"  [{'DRY' if dry_run else 'OK'}] TestCase {tc.id}: "
                  f"{type(ref_params).__name__} → list[{len(normalized)}]")

        if not dry_run and stats['tc_updated'] > 0:
            db.session.commit()

        # 2. ReportCase.reference_params — 保持 dict，清理 api/e2e
        report_cases = ReportCase.query.all()
        stats['rc_total'] = len(report_cases)
        print(f"\n=== 扫描 ReportCase ({len(report_cases)} 条) ===")

        for rc in report_cases:
            ref_params = rc.reference_params
            if not ref_params:
                continue

            cleaned, changed = _clean_report_ref_params(ref_params)
            if not changed:
                continue

            if not dry_run:
                from sqlalchemy.orm.attributes import flag_modified
                rc.reference_params = cleaned
                flag_modified(rc, 'reference_params')
            stats['rc_updated'] += 1
            print(f"  [{'DRY' if dry_run else 'OK'}] ReportCase {rc.id}: 清理 api/e2e 字段")

        if not dry_run and stats['rc_updated'] > 0:
            db.session.commit()

    print(f"\n数据库统计:")
    print(f"  TestCase: 总计={stats['tc_total']}, 更新={stats['tc_updated']}")
    print(f"  ReportCase: 总计={stats['rc_total']}, 更新={stats['rc_updated']}")
    return stats


def main():
    parser = argparse.ArgumentParser(description='迁移 reference_params 到统一格式')
    parser.add_argument('--dry-run', action='store_true', help='预览模式，不执行任何更改')
    parser.add_argument('--files-only', action='store_true', help='只处理 JSON 文件')
    parser.add_argument('--db-only', action='store_true', help='只处理数据库')
    args = parser.parse_args()

    print("=" * 60)
    print("reference_params 格式统一迁移")
    print(f"模式: {'预览 (DRY RUN)' if args.dry_run else '正式执行'}")
    print("=" * 60)

    if not args.db_only:
        migrate_files(dry_run=args.dry_run)

    if not args.files_only:
        migrate_database(dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print("迁移完成！" if not args.dry_run else "[DRY RUN] 预览完成，未修改任何数据")
    print("=" * 60)


if __name__ == '__main__':
    main()
