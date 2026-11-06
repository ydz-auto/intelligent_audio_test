# -*- coding: utf-8 -*-
"""INT-1645 存量参考参数文件迁移：宿主目录 → ref_params bucket。

背景：用例参考参数的写入口径是「内容存对象存储、路径存
`test_cases.reference_params` 独立列」，key 为 `<case_id>/round_N.json`。
V9.7.10 遗留数据仍落在宿主目录 `D:\\00_static\\static\\ref_params\\<case_id>\\*.json`，
DB 里存的是该宿主绝对路径；读写端点按卡面规则归一化后到 ref_params bucket
找对象，所以必须先把存量文件按同一 key 上传一次（DB 不用改）。

用法（宿主运行，项目环境 python）：
    $env:OSS_ENDPOINT='http://localhost:9000'
    $env:OSS_ACCESS_KEY/SECRET_KEY 与 docker compose 一致
    # 桶模式必须与 compose 一致：主 compose 是单桶模式（见下方说明）
    $env:OSS_BUCKET_NAME='intelligent-audio-test'
    $env:OSS_KEY_PREFIX='intelligent_audio_test'
    $env:PYTHONIOENCODING='utf-8'
    python scripts/migrate_ref_params_to_oss.py --source D:\\00_static\\static\\ref_params
    python scripts/migrate_ref_params_to_oss.py --source <dir> --dry-run
    python scripts/migrate_ref_params_to_oss.py --source <dir> --limit 50 --force

桶模式：`shared.clients.oss_client` 在 OSS_BUCKET_NAME 非空时走单桶模式，key 统一拼成
`{OSS_KEY_PREFIX}/{category}/{原key}`；为空时退回多桶模式（ref_params→ref-params 桶）。
主 compose 的 task_service / api_gateway 用的是单桶 `intelligent-audio-test` +
前缀 `intelligent_audio_test`，宿主侧不显式配置就会传错桶（上传成功但服务侧读不到）。

（DATABASE_URL 只为满足配置导入期校验自动占位，脚本不连 DB。）

幂等：默认跳过已存在的对象（`storage.exists`），`--force` 覆盖。
只经 shared.infrastructure.storage（Storage/OSSClient）上传，不碰 DB。
输出汇总：scanned / uploaded / skipped / failed。
退出码：0 完成（含部分 skipped）；1 存在 failed。
"""

import argparse
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# 本脚本不碰 DB（只经存储抽象上传对象），但 shared.infrastructure.config 在导入期
# 强校验 DATABASE_URL；未设置时给占位串，脚本全程不会建立数据库连接。
os.environ.setdefault('DATABASE_URL', 'sqlite:///ref_params_migration_placeholder.db')

from task_service.infrastructure.oss.ref_params_store import REF_PARAMS_BUCKET  # noqa: E402

DEFAULT_SOURCE = r'D:\00_static\static\ref_params'
_CONTENT_TYPE = 'application/json'


def _iter_source_files(source: Path, limit: int = 0):
    """按 <case_id>/<filename> 顺序产出 (case_id, file_path)，稳定排序。"""
    count = 0
    for case_dir in sorted(p for p in source.iterdir() if p.is_dir()):
        for file_path in sorted(p for p in case_dir.iterdir() if p.is_file()):
            if limit and count >= limit:
                return
            yield case_dir.name, file_path
            count += 1


def migrate(source: Path, dry_run: bool = False, limit: int = 0,
            force: bool = False) -> dict:
    """执行迁移，返回汇总 dict。"""
    from shared.infrastructure.config import BaseConfig
    from shared.infrastructure.storage import storage

    if not BaseConfig.OSS_BUCKET_NAME:
        print('[警告] 未配置 OSS_BUCKET_NAME，将走多桶模式（ref-params 桶）；'
              '主 compose 用的是单桶 intelligent-audio-test + 前缀 intelligent_audio_test，'
              '请确认桶模式与服务一致，否则对象传上去服务侧读不到。', file=sys.stderr)

    stats = {'scanned': 0, 'uploaded': 0, 'skipped': 0, 'failed': 0}
    failures = []

    for case_id, file_path in _iter_source_files(source, limit):
        stats['scanned'] += 1
        key = f'{case_id}/{file_path.name}'
        target = storage.build_path(REF_PARAMS_BUCKET, key)

        if not force and storage.exists(target):
            stats['skipped'] += 1
            continue

        if dry_run:
            print(f'[dry-run] {file_path} -> {target}')
            stats['uploaded'] += 1
            continue

        try:
            # save_file 内部按 OSS 可用性选择落点，失败时按配置降级本地
            stored = storage.save_file(str(file_path), REF_PARAMS_BUCKET, key)
            stats['uploaded'] += 1
            print(f'[uploaded] {file_path} -> {stored}')
        except Exception as exc:
            stats['failed'] += 1
            failures.append((str(file_path), str(exc)))
            print(f'[failed] {file_path}: {exc}', file=sys.stderr)

    if failures:
        print('失败明细：', file=sys.stderr)
        for path, reason in failures:
            print(f'  - {path}: {reason}', file=sys.stderr)

    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='INT-1645 存量参考参数文件迁移到 ref_params bucket（不碰 DB）')
    parser.add_argument('--source', default=DEFAULT_SOURCE,
                        help=f'存量目录，默认 {DEFAULT_SOURCE}')
    parser.add_argument('--dry-run', action='store_true',
                        help='只打印将要上传的映射，不写对象')
    parser.add_argument('--limit', type=int, default=0,
                        help='最多处理 N 个文件（0=不限）')
    parser.add_argument('--force', action='store_true',
                        help='覆盖已存在的对象（默认跳过）')
    args = parser.parse_args(argv)

    source = Path(args.source)
    if not source.is_dir():
        print(f'源目录不存在: {source}', file=sys.stderr)
        return 1

    stats = migrate(source, dry_run=args.dry_run, limit=args.limit, force=args.force)
    mode = '（dry-run，未写入）' if args.dry_run else ''
    print(f"完成{mode}: scanned={stats['scanned']} uploaded={stats['uploaded']} "
          f"skipped={stats['skipped']} failed={stats['failed']}")
    return 1 if stats['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
