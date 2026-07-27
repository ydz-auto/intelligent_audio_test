#!/usr/bin/env python3
"""
本地数据迁移到 S3/MinIO 脚本

将生产环境本地磁盘的历史数据批量迁移到 OSS（S3/MinIO）。
支持迁移的数据类型：
  - 音频文件（audios/）
  - 设备采集结果（case_result/）
  - 参考参数（ref_params/）
  - 报告文件（reports/）
  - 归档文件（archives/）
  - 临时文件（temp/）

用法：
  # 全量迁移（交互式确认）
  python scripts/migrate_local_to_s3.py

  # 只迁移音频
  python scripts/migrate_local_to_s3.py --only audios

  # 干跑（只列出，不上传）
  python scripts/migrate_local_to_s3.py --dry-run

  # 指定本地根目录
  python scripts/migrate_local_to_s3.py --local-root /data/static

  # 迁移完后更新数据库（file_path 本地路径 → OSS key）
  python scripts/migrate_local_to_s3.py --update-db

环境变量：
  OSS_ENDPOINT       S3/MinIO 地址
  OSS_ACCESS_KEY     访问密钥
  OSS_SECRET_KEY     秘密密钥
  OSS_REGION         区域
  DATABASE_URL       数据库连接（--update-db 时需要）
  LOCAL_STATIC_PATH  本地静态文件根目录（默认 ./static）
  LOCAL_ARCHIVE_PATH 本地归档目录（默认 ./archives）
"""
import os
import sys
import argparse
import json
import logging
from pathlib import Path
from typing import Optional

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / 'migration.log', encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)


# ============================================================
# 数据类型映射：本地子目录 → OSS bucket
# ============================================================
MIGRATION_TARGETS = {
    'audios': {
        'local_subdir': 'audios',
        'oss_category': 'audios',
        'description': '音频文件（wav/mp3/m4a 等）',
        'extensions': None,  # 全部文件
    },
    'case_result': {
        'local_subdir': 'case_result',
        'oss_category': 'case_result',
        'description': '设备采集结果（srt/stm/rttm/log 等）',
        'extensions': None,
    },
    'ref_params': {
        'local_subdir': 'ref_params',
        'oss_category': 'ref_params',
        'description': '参考参数文件（json）',
        'extensions': ['.json'],
    },
    'reports': {
        'local_subdir': 'reports',
        'oss_category': 'reports',
        'description': '报告文件',
        'extensions': None,
    },
    'archives': {
        'local_subdir': '',  # 归档直接在根目录下
        'oss_category': 'archives',
        'description': '归档文件',
        'extensions': ['.json'],
        'alt_env': 'LOCAL_ARCHIVE_PATH',
    },
    'temp': {
        'local_subdir': 'temp_uploads',
        'oss_category': 'temp',
        'description': '临时上传文件',
        'extensions': None,
    },
}


def get_local_root(args):
    """获取本地静态文件根目录"""
    if args.local_root:
        return Path(args.local_root)
    return Path(os.environ.get('LOCAL_STATIC_PATH', PROJECT_ROOT / 'static'))


def get_archive_root(args):
    """获取归档目录"""
    if args.archive_path:
        return Path(args.archive_path)
    return Path(os.environ.get('LOCAL_ARCHIVE_PATH', PROJECT_ROOT / 'archives'))


def scan_local_files(local_dir: Path, extensions: Optional[list] = None) -> list:
    """扫描本地目录下所有文件，返回 (相对路径, 绝对路径) 列表"""
    if not local_dir.exists():
        return []

    results = []
    for root, dirs, files in os.walk(local_dir):
        for fname in files:
            if extensions:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in extensions:
                    continue
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, local_dir).replace('\\', '/')
            results.append((rel_path, abs_path))

    return results


def migrate_file_to_oss(oss, local_path: str, oss_category: str, oss_key: str,
                         dry_run: bool = False) -> bool:
    """上传单个文件到 OSS"""
    if dry_run:
        logger.info(f"  [DRY-RUN] {local_path} → {oss_category}/{oss_key}")
        return True

    try:
        oss.upload_file(local_path, oss_category, oss_key)
        return True
    except Exception as e:
        logger.error(f"  上传失败: {local_path} → {oss_category}/{oss_key}: {e}")
        return False


def migrate_category(oss, category_name: str, config: dict, args) -> dict:
    """迁移一个类别的数据"""
    logger.info(f"\n{'='*60}")
    logger.info(f"迁移类别: {category_name} - {config['description']}")
    logger.info(f"{'='*60}")

    # 确定本地目录
    if config.get('alt_env'):
        local_dir = get_archive_root(args)
    else:
        local_dir = get_local_root(args) / config['local_subdir']

    if not local_dir.exists():
        logger.warning(f"  本地目录不存在，跳过: {local_dir}")
        return {'category': category_name, 'scanned': 0, 'uploaded': 0, 'failed': 0}

    # 扫描文件
    files = scan_local_files(local_dir, config.get('extensions'))
    logger.info(f"  扫描到 {len(files)} 个文件")

    if not files:
        return {'category': category_name, 'scanned': 0, 'uploaded': 0, 'failed': 0}

    # 检查是否已存在于 OSS（幂等迁移）
    uploaded = 0
    failed = 0
    skipped = 0

    for i, (rel_path, abs_path) in enumerate(files, 1):
        oss_key = rel_path

        # 幂等检查：已存在则跳过（除非 --force）
        if not args.force and oss.exists(config['oss_category'], oss_key):
            skipped += 1
            if i % 100 == 0:
                logger.info(f"  进度: {i}/{len(files)} (跳过已存在)")
            continue

        ok = migrate_file_to_oss(oss, abs_path, config['oss_category'], oss_key, args.dry_run)
        if ok:
            uploaded += 1
        else:
            failed += 1

        if i % 100 == 0:
            logger.info(f"  进度: {i}/{len(files)} (上传 {uploaded}, 跳过 {skipped}, 失败 {failed})")

    logger.info(f"  完成: 扫描 {len(files)}, 上传 {uploaded}, 跳过 {skipped}, 失败 {failed}")

    return {
        'category': category_name,
        'scanned': len(files),
        'uploaded': uploaded,
        'skipped': skipped,
        'failed': failed,
    }


# ============================================================
# 数据库路径更新
# ============================================================
def update_database_paths(args):
    """更新数据库中 file_path 等字段的本地路径为 OSS key"""
    logger.info(f"\n{'='*60}")
    logger.info("更新数据库路径")
    logger.info(f"{'='*60}")

    if args.dry_run:
        logger.info("[DRY-RUN] 仅列出需要更新的记录，不实际修改")

    from shared.models.database import db, init_app
    from flask import Flask

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        os.environ.get('SQLALCHEMY_DATABASE_URI', 'postgresql://localhost/audio_test')
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    init_app(app)

    from shared.models.models import Audio, TestResult

    static_root = str(get_local_root(args))

    with app.app_context():
        # 1. Audio.file_path: 本地绝对路径 → OSS key
        audios = Audio.query.filter(Audio.file_path.like(f'{static_root}%')).all()
        logger.info(f"Audio.file_path 需更新: {len(audios)} 条")

        updated = 0
        for audio in audios:
            old_path = audio.file_path
            # 提取 OSS key：去掉 static_root 前缀 + audios/
            # 例如 /data/static/audios/audio_123.wav → audio_123.wav
            rel = old_path.replace('\\', '/')
            for prefix in [f'{static_root}/audios/', f'{static_root}/', 'audios/']:
                prefix = prefix.replace('\\', '/')
                if rel.startswith(prefix):
                    audio.file_path = rel[len(prefix):]
                    break
            else:
                # 只取文件名
                audio.file_path = os.path.basename(old_path)

            if not args.dry_run:
                db.session.add(audio)
            updated += 1

            if updated % 100 == 0:
                logger.info(f"  Audio 进度: {updated}/{len(audios)}")

        # 2. TestResult.result_data_path: 本地路径 → OSS key
        results = TestResult.query.filter(
            TestResult.result_data_path.like(f'{static_root}%')
        ).all()
        logger.info(f"TestResult.result_data_path 需更新: {len(results)} 条")

        result_updated = 0
        for tr in results:
            old_path = tr.result_data_path
            if not old_path:
                continue
            rel = old_path.replace('\\', '/')
            for prefix in [f'{static_root}/case_result/', f'{static_root}/']:
                prefix = prefix.replace('\\', '/')
                if rel.startswith(prefix):
                    tr.result_data_path = rel[len(prefix):]
                    break
            else:
                tr.result_data_path = os.path.basename(old_path)

            if not args.dry_run:
                db.session.add(tr)
            result_updated += 1

            if result_updated % 100 == 0:
                logger.info(f"  TestResult 进度: {result_updated}/{len(results)}")

        # 3. reference_params 独立列（如果有）
        try:
            from sqlalchemy import text
            # 检查是否有 reference_params_path 列
            rows = db.session.execute(text(
                "SELECT id, reference_params_path FROM test_results "
                "WHERE reference_params_path LIKE :pattern"
            ), {'pattern': f'{static_root}%'}).fetchall()
            logger.info(f"test_results.reference_params_path 需更新: {len(rows)} 条")

            for row in rows:
                old_path = row[1]
                rel = old_path.replace('\\', '/')
                for prefix in [f'{static_root}/ref_params/', f'{static_root}/']:
                    prefix = prefix.replace('\\', '/')
                    if rel.startswith(prefix):
                        new_path = rel[len(prefix):]
                        break
                else:
                    new_path = os.path.basename(old_path)

                if not args.dry_run:
                    db.session.execute(text(
                        "UPDATE test_results SET reference_params_path = :new "
                        "WHERE id = :id"
                    ), {'new': new_path, 'id': row[0]})

            ref_updated = len(rows)
        except Exception as e:
            logger.warning(f"reference_params_path 列更新失败（可能列不存在）: {e}")
            ref_updated = 0

        # 提交
        if not args.dry_run:
            db.session.commit()
            logger.info("数据库更新已提交")
        else:
            logger.info("[DRY-RUN] 未提交数据库变更")

        logger.info(f"数据库更新完成: Audio {updated}, TestResult {result_updated}, "
                    f"reference_params {ref_updated}")


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(description='本地数据迁移到 S3/MinIO')
    parser.add_argument('--local-root', help='本地静态文件根目录（默认 ./static 或 LOCAL_STATIC_PATH）')
    parser.add_argument('--archive-path', help='本地归档目录（默认 ./archives 或 LOCAL_ARCHIVE_PATH）')
    parser.add_argument('--only', choices=list(MIGRATION_TARGETS.keys()),
                        help='只迁移指定类别')
    parser.add_argument('--dry-run', action='store_true', help='只列出文件，不上传')
    parser.add_argument('--force', action='store_true', help='强制上传（跳过幂等检查）')
    parser.add_argument('--update-db', action='store_true', help='迁移后更新数据库路径')
    parser.add_argument('--no-confirm', action='store_true', help='跳过交互式确认')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("本地数据 → S3/MinIO 迁移工具")
    logger.info("=" * 60)
    logger.info(f"模式: {'DRY-RUN' if args.dry_run else '实际迁移'}")
    logger.info(f"本地根目录: {get_local_root(args)}")
    logger.info(f"归档目录: {get_archive_root(args)}")
    logger.info(f"OSS Endpoint: {os.environ.get('OSS_ENDPOINT', 'http://localhost:9000')}")

    # 交互式确认
    if not args.no_confirm and not args.dry_run:
        print("\n即将开始迁移，这会上传大量文件到 OSS。")
        answer = input("确认继续？(yes/no): ")
        if answer.lower() != 'yes':
            logger.info("已取消")
            return

    # 初始化 OSS 客户端
    from shared.clients.oss_client import oss

    # 选择迁移目标
    if args.only:
        targets = {args.only: MIGRATION_TARGETS[args.only]}
    else:
        targets = MIGRATION_TARGETS

    # 执行迁移
    results = []
    for category_name, config in targets.items():
        result = migrate_category(oss, category_name, config, args)
        results.append(result)

    # 汇总
    logger.info(f"\n{'='*60}")
    logger.info("迁移汇总")
    logger.info(f"{'='*60}")
    total_scanned = 0
    total_uploaded = 0
    total_skipped = 0
    total_failed = 0
    for r in results:
        logger.info(f"  {r['category']:15s}: 扫描 {r['scanned']}, "
                    f"上传 {r.get('uploaded', 0)}, "
                    f"跳过 {r.get('skipped', 0)}, "
                    f"失败 {r.get('failed', 0)}")
        total_scanned += r['scanned']
        total_uploaded += r.get('uploaded', 0)
        total_skipped += r.get('skipped', 0)
        total_failed += r.get('failed', 0)

    logger.info(f"  {'合计':15s}: 扫描 {total_scanned}, "
                f"上传 {total_uploaded}, 跳过 {total_skipped}, "
                f"失败 {total_failed}")

    # 数据库更新
    if args.update_db:
        update_database_paths(args)

    if total_failed > 0:
        logger.warning(f"\n有 {total_failed} 个文件迁移失败，请查看 migration.log")
        sys.exit(1)

    logger.info("\n迁移完成！")


if __name__ == '__main__':
    main()
