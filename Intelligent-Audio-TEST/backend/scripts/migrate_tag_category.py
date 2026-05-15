"""
数据库迁移脚本：添加标签分类功能

功能：
1. 创建 tag_categories 表
2. 为 tags 表添加 category_id 外键
3. 迁移现有标签数据（可选：创建默认分类）

使用方法：
    python migrate_tag_category.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import create_app
from backend.models.database import db
from backend.models.models import Tag, TagCategory
from datetime import datetime, timezone, timedelta
from sqlalchemy import text


def utc8now():
    return datetime.now(timezone(timedelta(hours=8)))


def migrate():
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("开始迁移：添加标签分类功能")
        print("=" * 60)
        
        try:
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            if 'tag_categories' not in existing_tables:
                print("\n[1/3] 创建 tag_categories 表...")
                with db.engine.connect() as conn:
                    conn.execute(text("""
                        CREATE TABLE tag_categories (
                            id SERIAL PRIMARY KEY,
                            name VARCHAR(50) UNIQUE NOT NULL,
                            description TEXT,
                            color VARCHAR(20),
                            sort_order INTEGER DEFAULT 0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                    conn.commit()
                print("✓ tag_categories 表创建成功")
            else:
                print("\n[1/3] tag_categories 表已存在，跳过创建")
            
            columns = [col['name'] for col in inspector.get_columns('tags')]
            if 'category_id' not in columns:
                print("\n[2/3] 为 tags 表添加 category_id 字段...")
                with db.engine.connect() as conn:
                    conn.execute(text("""
                        ALTER TABLE tags 
                        ADD COLUMN category_id INTEGER REFERENCES tag_categories(id)
                    """))
                    conn.commit()
                print("✓ category_id 字段添加成功")
            else:
                print("\n[2/3] category_id 字段已存在，跳过添加")
            
            print("\n[3/3] 创建默认标签分类...")
            
            default_categories = [
                {'name': '人数', 'description': '测试场景中的人数', 'color': '#1890ff', 'sort_order': 1},
                {'name': '场景', 'description': '测试场景类型', 'color': '#52c41a', 'sort_order': 2},
                {'name': '语种', 'description': '语言类型', 'color': '#faad14', 'sort_order': 3},
                {'name': '环境', 'description': '测试环境类型', 'color': '#eb2f96', 'sort_order': 4},
                {'name': '其他', 'description': '其他标签分类', 'color': '#722ed1', 'sort_order': 99},
            ]
            
            created_count = 0
            for cat_data in default_categories:
                existing = TagCategory.query.filter_by(name=cat_data['name']).first()
                if not existing:
                    cat = TagCategory(
                        name=cat_data['name'],
                        description=cat_data['description'],
                        color=cat_data['color'],
                        sort_order=cat_data['sort_order']
                    )
                    db.session.add(cat)
                    created_count += 1
                    print(f"  创建分类: {cat_data['name']}")
            
            if created_count > 0:
                db.session.commit()
                print(f"✓ 创建了 {created_count} 个默认分类")
            else:
                print("✓ 默认分类已存在，跳过创建")
            
            print("\n" + "=" * 60)
            print("迁移完成！")
            print("=" * 60)
            
            print("\n当前标签分类列表：")
            categories = TagCategory.query.order_by(TagCategory.sort_order).all()
            for cat in categories:
                tag_count = Tag.query.filter_by(category_id=cat.id).count()
                print(f"  - [{cat.id}] {cat.name}: {tag_count} 个标签")
            
            uncategorized_count = Tag.query.filter_by(category_id=None).count()
            if uncategorized_count > 0:
                print(f"\n提示: 有 {uncategorized_count} 个标签尚未分类，请通过管理界面进行分类")
            
        except Exception as e:
            print(f"\n❌ 迁移失败: {str(e)}")
            db.session.rollback()
            raise


if __name__ == '__main__':
    migrate()
