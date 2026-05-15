"""
音频算法关联数据迁移脚本

功能：
1. 创建 audio_algorithm_relations 表（如果不存在）
2. 从现有测试用例的 algorithm_type 迁移到音频的算法关联
3. 保留原有的测试用例关联

使用方法：
    python -m backend.scripts.migrate_audio_algorithm_relations
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app import create_app
from backend.models.database import db
from backend.models.models import Audio, TestCase, AudioAlgorithmRelation
from backend.models.algorithm_models import AlgorithmDefinition


def create_table_if_not_exists():
    """创建 audio_algorithm_relations 表（如果不存在）"""
    try:
        db.engine.execute("""
            CREATE TABLE IF NOT EXISTS audio_algorithm_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audio_id INTEGER NOT NULL,
                algorithm_type VARCHAR(50) NOT NULL,
                is_primary BOOLEAN DEFAULT FALSE,
                weight FLOAT DEFAULT 1.0,
                params JSON,
                deleted BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        db.engine.execute("""
            CREATE INDEX IF NOT EXISTS idx_audio_algorithm_audio 
            ON audio_algorithm_relations(audio_id)
        """)
        
        db.engine.execute("""
            CREATE INDEX IF NOT EXISTS idx_audio_algorithm_type 
            ON audio_algorithm_relations(algorithm_type)
        """)
        
        print("表 audio_algorithm_relations 创建成功或已存在")
        return True
    except Exception as e:
        print(f"创建表失败: {e}")
        return False


def get_valid_algorithm_types():
    """获取所有有效的算法类型"""
    try:
        algorithms = AlgorithmDefinition.query.filter_by(deleted=False).all()
        return [algo.type for algo in algorithms]
    except Exception as e:
        print(f"获取算法定义失败: {e}")
        return []


def migrate_audio_algorithm_relations():
    """迁移音频算法关联数据"""
    print("=" * 60)
    print("开始迁移音频算法关联数据...")
    print("=" * 60)
    
    valid_algorithm_types = get_valid_algorithm_types()
    print(f"有效的算法类型: {valid_algorithm_types}")
    
    test_cases = TestCase.query.filter(
        TestCase.algorithm_type.isnot(None),
        TestCase.deleted == False
    ).all()
    
    print(f"找到 {len(test_cases)} 个有算法类型的测试用例")
    
    migrated_count = 0
    skipped_count = 0
    error_count = 0
    
    for case in test_cases:
        if not case.algorithm_type:
            continue
            
        if case.algorithm_type not in valid_algorithm_types:
            print(f"跳过无效算法类型: {case.algorithm_type} (测试用例ID: {case.id})")
            skipped_count += 1
            continue
        
        config = case.config or {}
        audios_config = config.get('audios', [])
        
        if not audios_config:
            continue
        
        for audio_config in audios_config:
            audio_id = audio_config.get('audio_id')
            if not audio_id:
                continue
            
            audio = Audio.query.filter_by(id=audio_id, deleted=False).first()
            if not audio:
                print(f"音频不存在或已删除: audio_id={audio_id}")
                skipped_count += 1
                continue
            
            existing = AudioAlgorithmRelation.query.filter_by(
                audio_id=audio_id,
                algorithm_type=case.algorithm_type,
                deleted=False
            ).first()
            
            if existing:
                continue
            
            try:
                relation = AudioAlgorithmRelation(
                    audio_id=audio_id,
                    algorithm_type=case.algorithm_type,
                    is_primary=True,
                    weight=1.0
                )
                db.session.add(relation)
                migrated_count += 1
                
                if migrated_count % 100 == 0:
                    db.session.commit()
                    print(f"已迁移 {migrated_count} 条记录...")
                    
            except Exception as e:
                print(f"创建关联失败: audio_id={audio_id}, algorithm_type={case.algorithm_type}, error={e}")
                error_count += 1
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"提交事务失败: {e}")
        return
    
    print("=" * 60)
    print("迁移完成!")
    print(f"成功迁移: {migrated_count} 条")
    print(f"跳过: {skipped_count} 条")
    print(f"错误: {error_count} 条")
    print("=" * 60)


def verify_migration():
    """验证迁移结果"""
    print("\n验证迁移结果...")
    
    total_relations = AudioAlgorithmRelation.query.filter_by(deleted=False).count()
    print(f"音频算法关联总数: {total_relations}")
    
    algorithm_stats = db.session.execute("""
        SELECT algorithm_type, COUNT(*) as count 
        FROM audio_algorithm_relations 
        WHERE deleted = 0 
        GROUP BY algorithm_type
    """).fetchall()
    
    print("\n各算法关联统计:")
    for algo_type, count in algorithm_stats:
        print(f"  {algo_type}: {count} 条")


if __name__ == '__main__':
    app = create_app()
    
    with app.app_context():
        print("开始执行迁移脚本...")
        
        if create_table_if_not_exists():
            migrate_audio_algorithm_relations()
            verify_migration()
        else:
            print("迁移失败: 无法创建表")
