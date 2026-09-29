"""
audio_algorithm_relations 关联表回填脚本

背景：
    音频列表按算法筛选依赖 audio_algorithm_relations 关联表，但历史音频
    仅在上传时显式选择算法才写入关联，未选的音频无关联行，导致筛选结果为空。

数据来源：
    audio_annotations.code 在实际数据中即为算法类型码（如 voice_llm），
    以其作为推导来源：为每个音频的每个非空、且存在于 algorithm_definitions
    （未删除）的标注 code 建立关联（幂等：跳过已存在的 (audio_id, algorithm_type)）。

使用方法（在项目根目录执行）：
    python backend/scripts/migrations/202609/backfill_audio_algorithm_relations.py --dry-run   # 预览
    python backend/scripts/migrations/202609/backfill_audio_algorithm_relations.py             # 执行
"""

import sys
import os
import argparse

# 上溯 4 级：202609 → migrations → scripts → backend → 项目根目录（backend 的包导入需要）
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..'))
sys.path.insert(0, _ROOT)

from backend.app import create_app
from backend.models.database import db
from backend.models.models import Audio, AudioAnnotation, AudioAlgorithmRelation
from backend.models.algorithm_models import AlgorithmDefinition


def backfill(dry_run=False):
    print("=" * 60)
    print(f"开始回填 audio_algorithm_relations（{'dry-run 预览' if dry_run else '实际执行'}）")
    print("=" * 60)

    # 有效算法码（未删除的算法定义）
    valid_types = {a.type for a in AlgorithmDefinition.query.filter_by(deleted=False).all()}
    print(f"有效算法类型: {sorted(valid_types)}")

    audios = Audio.query.filter_by(deleted=False).all()
    print(f"待处理音频数: {len(audios)}")

    # 已存在关联集合（幂等）
    existing = {
        (r.audio_id, r.algorithm_type)
        for r in AudioAlgorithmRelation.query.filter_by(deleted=False).all()
    }

    created = 0
    skipped_no_code = 0
    skipped_exists = 0
    skipped_invalid = 0

    for audio in audios:
        anns = AudioAnnotation.query.filter(
            AudioAnnotation.audio_id == audio.id,
            AudioAnnotation.deleted == False,  # noqa: E712
            AudioAnnotation.code.isnot(None),
            AudioAnnotation.code != ''
        ).all()
        codes = {ann.code for ann in anns if ann.code in valid_types}
        if not codes:
            invalid = {ann.code for ann in anns if ann.code} - valid_types
            if invalid:
                skipped_invalid += 1
            else:
                skipped_no_code += 1
            continue

        for code in codes:
            if (audio.id, code) in existing:
                skipped_exists += 1
                continue
            print(f"  音频 #{audio.id} [{(audio.name or '')[:30]}] -> {code}")
            if not dry_run:
                db.session.add(AudioAlgorithmRelation(
                    audio_id=audio.id,
                    algorithm_type=code,
                    is_primary=True,
                    weight=1.0,
                    deleted=False
                ))
            existing.add((audio.id, code))
            created += 1

    if not dry_run:
        db.session.commit()

    print("-" * 60)
    print(f"完成: {'预览' if dry_run else '新建'}关联 {created} 条，"
          f"已存在跳过 {skipped_exists} 条，"
          f"无有效标注码跳过 {skipped_no_code} 个音频，"
          f"标注码非算法类型跳过 {skipped_invalid} 个音频")
    if dry_run:
        print("（dry-run 模式未写入数据库）")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='从音频标注推导回填算法关联')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不写入数据库')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        backfill(dry_run=args.dry_run)
