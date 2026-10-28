# -*- coding: utf-8 -*-
"""存量音频源文件迁移：宿主本地目录 → audios 对象（按 DB file_path 作 key）。

背景：网页播放走 `GET /audios/{id}/stream`，返回 rustfs 预签名地址，key =
`{OSS_KEY_PREFIX}/audios/{audios.file_path}`。存量音频源 .wav 目前只在宿主本地
目录（用户已移动到 C:\\S2TT\\...），未上传到 rustfs → 预签名 404 → 全部播不了。
本脚本按 DB 每条 audios.file_path 作 key，把对应本地文件上传到 rustfs，DB 不改。

两种 DB file_path 前缀都落到同一个本地根（去掉前缀 = 相对路径）：
    D:/00_static/static/audios/<rel>
    C:/S2TT/auto_test/ver8/202604231600/Intelligent-Audio-TEST/static/audios/<rel>
    → 本地文件 = <audio-root>/<rel>

用法（宿主运行，conda 环境 python；先 dry-run）：
    $env:DATABASE_URL='postgresql://intelligent_audio_test:intelligent_audio_test666@127.0.0.1:15435/intelligent_audio_test'
    $env:OSS_ENDPOINT='http://127.0.0.1:9000'
    $env:OSS_ACCESS_KEY='intelligent_audio_test'; $env:OSS_SECRET_KEY='intelligent_audio_test666'
    $env:OSS_BUCKET_NAME='intelligent-audio-test'; $env:OSS_KEY_PREFIX='intelligent_audio_test'
    $env:PYTHONIOENCODING='utf-8'
    python scripts/migrate_audios_to_oss.py --dry-run
    python scripts/migrate_audios_to_oss.py            # 正式（默认跳过已存在）
    python scripts/migrate_audios_to_oss.py --force    # 覆盖

幂等：默认 storage.exists 跳过；--force 覆盖。只经 storage.save_file 上传，不改 DB。
退出码：0 完成（含 skipped/missing_local）；1 存在 failed。
"""

import argparse
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

DEFAULT_AUDIO_ROOT = r'C:\S2TT\auto_test\ver8\202604231600\Intelligent-Audio-TEST\static\audios'

# DB file_path 历史前缀（去掉后即 <audio-root> 下的相对路径）
PATH_PREFIXES = (
    'D:/00_static/static/audios/',
    'C:/S2TT/auto_test/ver8/202604231600/Intelligent-Audio-TEST/static/audios/',
)

CATEGORY = 'audios'


def _rel_of(file_path: str):
    fp = (file_path or '').replace('\\', '/')
    for pref in PATH_PREFIXES:
        if fp.startswith(pref):
            return fp[len(pref):]
    return None


def _iter_db_audios(limit: int = 0):
    import psycopg2
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        cur = conn.cursor()
        q = ("SELECT id, file_path FROM audios "
             "WHERE deleted=false AND file_path IS NOT NULL AND file_path <> ''")
        if limit:
            q += f' LIMIT {int(limit)}'
        cur.execute(q)
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    for aid, fp in rows:
        yield aid, fp


def migrate(audio_root: Path, dry_run: bool = False, limit: int = 0,
            force: bool = False) -> dict:
    from shared.infrastructure.storage import storage
    from shared.infrastructure.config import BaseConfig

    if not BaseConfig.OSS_BUCKET_NAME:
        print('[警告] OSS_BUCKET_NAME 未设，走多桶模式；compose 用单桶 '
              'intelligent-audio-test + 前缀 intelligent_audio_test，'
              '否则传上去服务侧读不到。', file=sys.stderr)

    stats = {'db': 0, 'local_found': 0, 'uploaded': 0, 'skipped': 0,
             'missing_local': 0, 'unknown_prefix': 0, 'failed': 0}
    failures = []

    for aid, fp in _iter_db_audios(limit):
        stats['db'] += 1
        rel = _rel_of(fp)
        if rel is None:
            stats['unknown_prefix'] += 1
            continue
        local = audio_root / rel
        if not local.is_file():
            stats['missing_local'] += 1
            continue
        stats['local_found'] += 1
        target = storage.build_path(CATEGORY, fp)

        # storage.exists 对 "C:/..." 这类「盘符冒号」开头的 key 会误报 True
        # （实测：对象并不存在但 exists 返回真，导致 skip 漏传）。带盘符的历史
        # 路径一律不走 exists 短路，确保真上传；其余 key 仍按 exists 幂等跳过。
        trust_exists = not re.match(r'^[A-Za-z]:/', fp)
        if not force and trust_exists and storage.exists(target):
            stats['skipped'] += 1
            continue

        if dry_run:
            stats['uploaded'] += 1
            print(f'[dry-run] id={aid} {local} -> {target}')
            continue

        try:
            storage.save_file(str(local), CATEGORY, fp)
            stats['uploaded'] += 1
            if stats['uploaded'] % 100 == 0:
                print(f'[progress] uploaded={stats["uploaded"]}', flush=True)
        except Exception as exc:  # noqa: BLE001
            stats['failed'] += 1
            failures.append((aid, str(fp), str(exc)))
            print(f'[failed] id={aid} {fp}: {exc}', file=sys.stderr)

    if failures:
        print('失败明细（前 20）：', file=sys.stderr)
        for aid, fp, reason in failures[:20]:
            print(f'  - id={aid} {fp}: {reason}', file=sys.stderr)
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='存量音频源文件迁移：本地目录 → audios 对象（按 DB file_path 作 key）')
    parser.add_argument('--audio-root', default=DEFAULT_AUDIO_ROOT,
                        help=f'本地音频根目录，默认 {DEFAULT_AUDIO_ROOT}')
    parser.add_argument('--dry-run', action='store_true', help='只打印映射，不上传')
    parser.add_argument('--limit', type=int, default=0, help='最多处理 N 条（0=不限）')
    parser.add_argument('--force', action='store_true', help='覆盖已存在对象')
    args = parser.parse_args(argv)

    if not os.environ.get('DATABASE_URL'):
        print('缺少 DATABASE_URL', file=sys.stderr)
        return 1
    root = Path(args.audio_root)
    if not root.is_dir():
        print(f'音频根目录不存在: {root}', file=sys.stderr)
        return 1

    stats = migrate(root, dry_run=args.dry_run, limit=args.limit, force=args.force)
    mode = '（dry-run）' if args.dry_run else ''
    print(f"完成{mode}: db={stats['db']} local_found={stats['local_found']} "
          f"uploaded={stats['uploaded']} skipped={stats['skipped']} "
          f"missing_local={stats['missing_local']} unknown_prefix={stats['unknown_prefix']} "
          f"failed={stats['failed']}")
    return 1 if stats['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
