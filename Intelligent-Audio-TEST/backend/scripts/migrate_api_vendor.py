import sqlite3
import os
import shutil
from datetime import datetime

def migrate():
    # 数据库路径
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, 'data.db')
    
    if not os.path.exists(db_path):
        print(f"错误: 找不到数据库文件 {db_path}")
        return

    # 1. 备份数据库
    backup_path = f"{db_path}.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
    print(f"正在备份数据库到 {backup_path}...")
    shutil.copy2(db_path, backup_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 2. 预迁移检查：检查 apis 表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='apis'")
        if not cursor.fetchone():
            print("错误: 找不到 apis 表")
            return

        # 3. 检查 vendor 列是否已存在
        cursor.execute("PRAGMA table_info(apis)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'vendor' in columns:
            print("提示: vendor 列已存在，跳过添加")
        else:
            print("正在为 apis 表添加 vendor 列...")
            # 4. 执行迁移：添加 vendor 列
            cursor.execute("ALTER TABLE apis ADD COLUMN vendor VARCHAR(50)")
            print("成功添加 vendor 列")

        # 5. 后迁移校验
        cursor.execute("PRAGMA table_info(apis)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'vendor' in columns:
            print("迁移验证成功: vendor 列已存在")
        else:
            raise Exception("迁移验证失败: vendor 列未找到")

        conn.commit()
        print("迁移任务顺利完成！")

    except Exception as e:
        conn.rollback()
        print(f"迁移失败: {e}")
        print(f"正在尝试从备份恢复...")
        shutil.copy2(backup_path, db_path)
        print("恢复完成。")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
