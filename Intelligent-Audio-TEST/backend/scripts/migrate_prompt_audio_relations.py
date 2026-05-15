# -*- coding: utf-8 -*-
"""
数据库迁移脚本：
1. 创建 prompt_audio_relations 表
2. 修复 prompt_audio_relations 表结构（使用字符串 translation_direction 而非 ID）
"""

import os
import sys

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.db')

from sqlalchemy import create_engine, text, inspect
engine = create_engine(f'sqlite:///{db_path}')


def table_exists(conn, table_name):
    inspector = inspect(conn)
    return table_name in inspector.get_table_names()


def table_has_column(conn, table_name, column_name):
    inspector = inspect(conn)
    columns = inspector.get_columns(table_name)
    return any(col['name'] == column_name for col in columns)


def migrate():
    print("=" * 60)
    print("开始数据库迁移：创建 prompt_audio_relations 表")
    print("=" * 60)

    with engine.connect() as conn:
        if table_exists(conn, 'prompt_audio_relations'):
            print("\n[1/2] 检查 prompt_audio_relations 表结构...")
            
            if table_has_column(conn, 'prompt_audio_relations', 'translation_direction_id'):
                print("  - 发现 translation_direction_id，需要改为 translation_direction...")
                
                conn.execute(text("PRAGMA foreign_keys=OFF"))
                
                conn.execute(text("""
                    CREATE TABLE prompt_audio_relations_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        audio_id INTEGER NOT NULL,
                        device_id INTEGER,
                        algorithm_type VARCHAR(50),
                        source_language VARCHAR(20),
                        target_language VARCHAR(20),
                        translation_direction VARCHAR(50),
                        priority INTEGER DEFAULT 0,
                        deleted BOOLEAN DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (audio_id) REFERENCES audios(id) ON DELETE CASCADE,
                        FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL
                    )
                """))
                                   
                conn.execute(text("""
                    INSERT INTO prompt_audio_relations_new 
                    (id, audio_id, device_id, algorithm_type, source_language, target_language, priority, deleted, created_at, updated_at)
                    SELECT id, audio_id, device_id, algorithm_type, source_language, target_language, priority, deleted, created_at, updated_at
                    FROM prompt_audio_relations
                """))
                
                conn.execute(text("DROP TABLE prompt_audio_relations"))
                conn.execute(text("ALTER TABLE prompt_audio_relations_new RENAME TO prompt_audio_relations"))
                conn.execute(text("PRAGMA foreign_keys=ON"))
                conn.commit()
                print("  ✓ 表结构修复成功")
            else:
                print("  ✓ 表结构正确")
        else:
            print("\n[1/2] 创建 prompt_audio_relations 表...")
            conn.execute(text("""
                CREATE TABLE prompt_audio_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audio_id INTEGER NOT NULL,
                    device_id INTEGER,
                    algorithm_type VARCHAR(50),
                    source_language VARCHAR(20),
                    target_language VARCHAR(20),
                    translation_direction VARCHAR(50),
                    priority INTEGER DEFAULT 0,
                    deleted BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (audio_id) REFERENCES audios(id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL
                )
            """))
            conn.commit()
            print("  ✓ prompt_audio_relations 表创建成功")

        print("\n[2/2] audios.prompt_translation_direction_id 字段保留（模型层已不使用）")

    print("\n" + "=" * 60)
    print("数据库迁移完成！")
    print("=" * 60)


if __name__ == '__main__':
    migrate()
