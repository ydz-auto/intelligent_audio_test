# -*- coding: utf-8 -*-
"""
创建语言表并插入数据
"""

import os
import sys

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.db')

from sqlalchemy import create_engine, text
engine = create_engine(f'sqlite:///{db_path}')


def create_table():
    """创建语言表"""
    with engine.connect() as conn:
        # 检查表是否已存在
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='languages'"))
        if result.fetchone():
            print("语言表已存在")
            return False
        
        # 创建表
        conn.execute(text("""
            CREATE TABLE languages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code VARCHAR(10) NOT NULL UNIQUE,
                name VARCHAR(50) NOT NULL,
                name_en VARCHAR(50),
                deleted BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
        print("语言表创建成功！")
        return True


def insert_languages():
    """插入语言数据"""
    languages_data = [
        ('zh', '中文', 'Chinese'),
        ('en', '英语', 'English'),
        ('ja', '日语', 'Japanese'),
        ('ko', '韩语', 'Korean'),
        ('es', '西班牙语', 'Spanish'),
        ('fr', '法语', 'French'),
        ('de', '德语', 'German'),
        ('it', '意大利语', 'Italian'),
        ('pt', '葡萄牙语', 'Portuguese'),
        ('ru', '俄语', 'Russian'),
        ('ar', '阿拉伯语', 'Arabic'),
        ('hi', '印地语', 'Hindi'),
        ('th', '泰语', 'Thai'),
        ('vi', '越南语', 'Vietnamese'),
        ('id', '印尼语', 'Indonesian'),
        ('ms', '马来语', 'Malay'),
        ('tr', '土耳其语', 'Turkish'),
        ('pl', '波兰语', 'Polish'),
        ('nl', '荷兰语', 'Dutch'),
        ('sv', '瑞典语', 'Swedish'),
    ]
    
    with engine.connect() as conn:
        for code, name, name_en in languages_data:
            conn.execute(text("""
                INSERT INTO languages (code, name, name_en) VALUES (:code, :name, :name_en)
            """), {'code': code, 'name': name, 'name_en': name_en})
        conn.commit()
        print(f"成功插入 {len(languages_data)} 条语言数据")


if __name__ == '__main__':
    if create_table():
        insert_languages()
    else:
        # 检查是否已有数据
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM languages"))
            count = result.fetchone()[0]
            if count == 0:
                insert_languages()
            else:
                print(f"语言表已有 {count} 条数据")
