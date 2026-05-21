"""
PostgreSQL INTEGER 到 BIGINT 迁移执行脚本

执行 migrate_integer_to_biginteger.sql 文件中的所有迁移操作
"""
import os
import sys
import psycopg2
from pathlib import Path

def get_db_config():
    """获取数据库配置"""
    db_user = os.environ.get('DB_USER', 'intelligent_audio_test')
    db_password = os.environ.get('DB_PASSWORD', 'intelligent_audio_test666')
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_port = os.environ.get('DB_PORT', '5432')
    db_name = os.environ.get('DB_NAME', 'intelligent_audio_test')
    
    return {
        'host': db_host,
        'port': db_port,
        'database': db_name,
        'user': db_user,
        'password': db_password
    }

def read_migration_sql():
    """读取迁移SQL文件"""
    migration_file = Path(__file__).parent / 'migrate_integer_to_biginteger.sql'
    if not migration_file.exists():
        raise FileNotFoundError(f"迁移文件不存在: {migration_file}")
    
    with open(migration_file, 'r', encoding='utf-8') as f:
        return f.read()

def execute_migration():
    """执行迁移"""
    config = get_db_config()
    
    print("=" * 60)
    print("PostgreSQL INTEGER 到 BIGINT 迁移")
    print("=" * 60)
    print(f"数据库: {config['host']}:{config['port']}/{config['database']}")
    print(f"用户: {config['user']}")
    print("=" * 60)
    
    try:
        conn = psycopg2.connect(**config)
        conn.autocommit = False
        cursor = conn.cursor()
        
        print("\n正在连接数据库...")
        
        sql_content = read_migration_sql()
        
        statements = []
        current_statement = []
        
        for line in sql_content.split('\n'):
            line = line.strip()
            if line.startswith('--') or line == '':
                continue
            
            current_statement.append(line)
            
            if line.endswith(';'):
                full_statement = ' '.join(current_statement)
                if full_statement and not full_statement.startswith('--'):
                    statements.append(full_statement)
                current_statement = []
        
        print(f"\n共需要执行 {len(statements)} 条SQL语句")
        print("\n开始执行迁移...\n")
        
        success_count = 0
        error_count = 0
        
        for i, statement in enumerate(statements, 1):
            try:
                if 'SELECT sequence_name' in statement:
                    cursor.execute(statement)
                    rows = cursor.fetchall()
                    print(f"[{i}/{len(statements)}] 查询序列状态:")
                    for row in rows:
                        print(f"  - {row[0]}: {row[1]} (范围: {row[3]} ~ {row[4]})")
                else:
                    cursor.execute(statement)
                    print(f"[{i}/{len(statements)}] 执行成功")
                success_count += 1
            except psycopg2.Error as e:
                error_msg = str(e).split('\n')[0]
                print(f"[{i}/{len(statements)}] 执行失败: {error_msg}")
                error_count += 1
                if 'already exists' in error_msg or 'does not exist' in error_msg:
                    continue
                else:
                    conn.rollback()
                    raise
        
        conn.commit()
        
        print("\n" + "=" * 60)
        print("迁移完成!")
        print(f"成功: {success_count} 条")
        print(f"跳过/失败: {error_count} 条")
        print("=" * 60)
        
        print("\n验证迁移结果...")
        
        verify_sql = """
        SELECT table_name, column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND column_name = 'id' 
        AND table_name NOT LIKE 'test_case%' 
        AND table_name NOT LIKE 'upload_%'
        ORDER BY table_name;
        """
        
        cursor.execute(verify_sql)
        rows = cursor.fetchall()
        
        print("\n所有表的 id 字段类型:")
        all_bigint = True
        for row in rows:
            table_name, column_name, data_type = row
            status = "✓" if data_type == 'bigint' else "✗"
            print(f"  {status} {table_name}.{column_name}: {data_type}")
            if data_type != 'bigint':
                all_bigint = False
        
        if all_bigint:
            print("\n✓ 所有 id 字段已成功转换为 BIGINT!")
        else:
            print("\n✗ 部分 id 字段未成功转换，请检查!")
        
        cursor.close()
        conn.close()
        
        return True
        
    except psycopg2.OperationalError as e:
        print(f"\n数据库连接失败: {e}")
        return False
    except Exception as e:
        print(f"\n迁移执行失败: {e}")
        return False

if __name__ == '__main__':
    print("\n警告: 此迁移将修改数据库表结构，建议先备份数据库!")
    print("按 Ctrl+C 取消，或等待5秒后自动开始...\n")
    
    try:
        import time
        time.sleep(5)
    except KeyboardInterrupt:
        print("\n用户取消操作")
        sys.exit(0)
    
    success = execute_migration()
    sys.exit(0 if success else 1)