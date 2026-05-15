#!/usr/bin/env python3
"""
简单数据库清理脚本

该脚本用于清理数据库中除了播放设备表(playback_devices)之外的所有表的数据。
直接连接数据库，不依赖于现有模型导入。
"""

import os
import sys
from sqlalchemy import create_engine, text

# 获取数据库路径
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.db')

# 创建数据库引擎
engine = create_engine(f'sqlite:///{db_path}')

# 要保留的表名
preserve_table = 'playback_devices'

def clean_database():
    """
    清理数据库中除播放设备表外的所有表数据
    """
    print("开始清理数据库...")
    print(f"数据库路径: {db_path}")
    
    try:
        # 连接数据库
        with engine.connect() as connection:
            # 开启事务
            with connection.begin():
                # 禁用外键约束检查
                connection.execute(text('PRAGMA foreign_keys = OFF'))
                
                # 获取所有表名
                result = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
                all_tables = [row[0] for row in result]
                
                # 要清理的表列表
                tables_to_clean = [table for table in all_tables if table != preserve_table]
                
                print(f"找到 {len(all_tables)} 个表，将清理其中 {len(tables_to_clean)} 个表，保留表: {preserve_table}")
                
                # 按相反的依赖顺序清理表，避免外键约束错误
                tables_order = [
                    'user_permissions', 'test_case_tags', 'test_case_audios', 'test_case_dimensions',
                    'device_tags', 'audio_translations', 'audio_tags', 'task_tags', 
                    'task_case_relations', 'task_device_relations', 'task_api_relations',
                    'test_result_dimensions', 'calibration_history',
                    'logs', 'test_results', 'reports',
                    'test_tasks', 'apis', 'test_cases', 'test_case_groups',
                    'audios', 'translation_directions', 'devices', 'categories',
                    'dimensions', 'spl_mappings', 'tags', 'permissions', 'users'
                ]
                
                # 确保所有要清理的表都在order列表中，如果不在则添加到末尾
                for table in tables_to_clean:
                    if table not in tables_order:
                        tables_order.append(table)
                
                # 清理每个表
                for table_name in tables_order:
                    if table_name != preserve_table and table_name in all_tables:
                        print(f"清理表: {table_name}")
                        connection.execute(text(f'DELETE FROM {table_name}'))
                
                # 重新启用外键约束检查
                connection.execute(text('PRAGMA foreign_keys = ON'))
        
        print("\n数据库清理完成！")
        print(f"保留了表 {preserve_table} 的数据")
        
    except Exception as e:
        print(f"\n清理过程中发生错误: {e}")
        raise


if __name__ == '__main__':
    clean_database()
