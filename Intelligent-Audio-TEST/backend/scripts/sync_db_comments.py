
import os
import sys
import re
import sqlite3
from sqlalchemy.schema import CreateTable

# 将项目根目录添加到 python 路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.app import create_app
from backend.models.database import db

def sync_comments():
    app = create_app()
    with app.app_context():
        # 获取数据库文件路径
        db_uri = app.config['SQLALCHEMY_DATABASE_URI']
        if not db_uri.startswith('sqlite:///'):
            print("目前仅支持 SQLite 数据库注释同步")
            return
        
        db_path = db_uri.replace('sqlite:///', '')
        if not os.path.isabs(db_path):
            db_path = os.path.join(app.root_path, db_path)
            
        print(f"正在连接数据库: {db_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 禁用外键检查以允许重命名表
        cursor.execute("PRAGMA foreign_keys=OFF;")
        
        # 遍历所有模型表
        for table_name, table in db.metadata.tables.items():
            print(f"--- 正在处理表: {table_name} ---")
            
            # 生成标准的 CREATE TABLE 语句
            create_sql = str(CreateTable(table).compile(db.engine))
            
            # 注入注释
            lines = create_sql.split('\n')
            new_lines = []
            for line in lines:
                strip_line = line.strip()
                # 匹配字段名 (可能有双引号)
                match = re.match(r'^"?([a-zA-Z0-9_]+)"?\s+', strip_line)
                if match:
                    col_name = match.group(1)
                    if col_name in table.columns:
                        comment = table.columns[col_name].comment
                        if comment:
                            # 关键：注释必须在逗号后面，或者该行没有逗号
                            # SQLite 的行格式通常是:  name TYPE,
                            line = line.rstrip()
                            line = f"{line} -- {comment}"
                new_lines.append(line)
            
            commented_sql = "\n".join(new_lines)
            
            try:
                cursor.execute("BEGIN TRANSACTION;")
                
                # 检查旧表是否存在
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}';")
                if cursor.fetchone():
                    # 1. 重命名旧表
                    cursor.execute(f"ALTER TABLE {table_name} RENAME TO {table_name}_old;")
                    
                    # 2. 创建带注释的新表
                    cursor.execute(commented_sql)
                    
                    # 3. 智能迁移数据 (仅迁移两个表都存在的字段)
                    # 获取旧表的字段
                    cursor.execute(f"PRAGMA table_info({table_name}_old);")
                    old_cols = [row[1] for row in cursor.fetchall()]
                    
                    # 获取新表的字段
                    cursor.execute(f"PRAGMA table_info({table_name});")
                    new_cols = [row[1] for row in cursor.fetchall()]
                    
                    # 取交集
                    common_cols = [f'"{c}"' for c in old_cols if c in new_cols]
                    if common_cols:
                        cols_str = ", ".join(common_cols)
                        cursor.execute(f"INSERT INTO {table_name} ({cols_str}) SELECT {cols_str} FROM {table_name}_old;")
                    
                    # 4. 删除旧表
                    cursor.execute(f"DROP TABLE {table_name}_old;")
                    print(f"表 {table_name} 同步成功 (已注入注释，迁移了 {len(common_cols)} 个字段)")
                else:
                    # 表不存在，直接创建
                    cursor.execute(commented_sql)
                    print(f"表 {table_name} 创建成功 (已注入注释)")
                
                cursor.execute("COMMIT;")
            except Exception as e:
                cursor.execute("ROLLBACK;")
                print(f"同步表 {table_name} 失败: {str(e)}")
                # 如果失败了，尝试恢复 (如果重命名成功了)
                try:
                    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}_old';")
                    if cursor.fetchone():
                        cursor.execute(f"ALTER TABLE {table_name}_old RENAME TO {table_name};")
                except:
                    pass
        
        cursor.execute("PRAGMA foreign_keys=ON;")
        conn.close()
        print("\n所有表的数据库注释已同步完成。")

if __name__ == "__main__":
    sync_comments()
