#!/usr/bin/env python3
"""
数据库清理脚本

该脚本用于清理数据库中除了播放设备表(playback_devices)之外的所有表的数据。
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# 设置当前目录为Python路径，以便直接导入models包
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入数据库和模型
from models import db
from models.models import Base


def clean_database():
    """
    清理数据库中除播放设备表外的所有表数据
    """
    print("开始清理数据库...")
    
    # 获取所有表对象
    all_tables = Base.metadata.tables.values()
    
    # 要保留的表名
    preserve_table = 'playback_devices'
    
    # 要清理的表列表
    tables_to_clean = [table for table in all_tables if table.name != preserve_table]
    
    print(f"找到 {len(all_tables)} 个表，将清理其中 {len(tables_to_clean)} 个表，保留表: {preserve_table}")
    
    try:
        # 创建数据库会话
        session = db.session
        
        # 开启事务
        session.begin()
        
        # 禁用外键约束检查，以便可以删除数据
        session.execute(text('PRAGMA foreign_keys = OFF'))
        
        # 按相反的依赖顺序清理表，避免外键约束错误
        # 先清理关联表，再清理主表
        tables_order = [
            'user_permissions', 'test_case_tags', 'test_case_audios', 'test_case_dimensions',
            'device_tags', 'audio_translations', 'audio_tags', 'task_tags', 
            'task_case_relations', 'task_device_relations', 'task_api_relations',
            'test_result_dimensions', 'calibration_history',
            'logs', 'test_result_dimensions', 'test_results', 'reports',
            'task_case_relations', 'task_device_relations', 'task_api_relations',
            'test_tasks', 'apis', 'test_cases', 'test_case_groups',
            'audios', 'translation_directions', 'devices', 'categories',
            'dimensions', 'spl_mappings', 'tags', 'permissions', 'users'
        ]
        
        # 确保所有要清理的表都在order列表中，如果不在则添加到末尾
        for table in tables_to_clean:
            if table.name not in tables_order:
                tables_order.append(table.name)
        
        # 清理每个表
        for table_name in tables_order:
            # 检查该表是否需要清理
            if table_name != preserve_table:
                print(f"清理表: {table_name}")
                # 使用TRUNCATE（SQLite不支持TRUNCATE with foreign keys，所以使用DELETE）
                session.execute(text(f'DELETE FROM {table_name}'))
        
        # 重新启用外键约束检查
        session.execute(text('PRAGMA foreign_keys = ON'))
        
        # 提交事务
        session.commit()
        
        print("\n数据库清理完成！")
        print(f"保留了表 {preserve_table} 的数据")
        
    except Exception as e:
        # 回滚事务
        session.rollback()
        print(f"\n清理过程中发生错误: {e}")
        raise
    finally:
        # 关闭会话
        session.close()


if __name__ == '__main__':
    clean_database()
