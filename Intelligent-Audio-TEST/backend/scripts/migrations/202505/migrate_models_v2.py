"""
数据库迁移脚本：模型版本升级 (v20260129 -> v20260423)

功能：
1. 创建新表：tag_categories, report_summaries, report_detail_data, audio_algorithm_relations
2. 修改字段类型：多个主键从 Integer 改为 BigInteger
3. 添加新字段：tags.category_id, tags.sort_order, test_case_groups.algorithm_type
4. 删除字段：task_case_relations.algorithm_type, task_case_relations.algorithm_params
5. 添加索引：test_reports, logs 表
6. 更新外键约束：级联删除
7. 数据迁移：用例分组关联 speaker_diarization，音频关联到 speaker_diarization
"""
import os
import sys
import psycopg2

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

db_config = get_db_config()


def get_connection():
    """获取数据库连接"""
    return psycopg2.connect(**db_config)


def check_table_exists(cursor, table_name):
    """检查表是否存在"""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = %s
        )
    """, (table_name,))
    return cursor.fetchone()[0]


def check_column_exists(cursor, table_name, column_name):
    """检查列是否存在"""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = %s 
            AND column_name = %s
        )
    """, (table_name, column_name))
    return cursor.fetchone()[0]


def check_index_exists(cursor, table_name, index_name):
    """检查索引是否存在"""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM pg_indexes 
            WHERE tablename = %s AND indexname = %s
        )
    """, (table_name, index_name))
    return cursor.fetchone()[0]


def create_tag_categories_table(cursor):
    """创建标签分类表"""
    if check_table_exists(cursor, 'tag_categories'):
        print("  [跳过] tag_categories 表已存在")
        return

    cursor.execute("""
        CREATE TABLE tag_categories (
            id SERIAL PRIMARY KEY,
            name VARCHAR(50) UNIQUE NOT NULL,
            description TEXT,
            color VARCHAR(20),
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("  [完成] 创建 tag_categories 表")


def create_report_summaries_table(cursor):
    """创建报告摘要表"""
    if check_table_exists(cursor, 'report_summaries'):
        print("  [跳过] report_summaries 表已存在")
        return

    cursor.execute("""
        CREATE TABLE report_summaries (
            id BIGSERIAL PRIMARY KEY,
            report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id) ON DELETE CASCADE,
            total_cases INTEGER DEFAULT 0,
            completed_cases INTEGER DEFAULT 0,
            failed_cases INTEGER DEFAULT 0,
            pass_rate FLOAT DEFAULT 0,
            dimension_values JSONB,
            duration FLOAT DEFAULT 0,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            case_categories JSONB,
            all_case_tags JSONB,
            devices JSONB,
            apis JSONB,
            resources JSONB,
            resource_headers JSONB,
            all_metrics JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("  [完成] 创建 report_summaries 表")


def create_report_detail_data_table(cursor):
    """创建报告详情数据表"""
    if check_table_exists(cursor, 'report_detail_data'):
        print("  [跳过] report_detail_data 表已存在")
        return

    cursor.execute("""
        CREATE TABLE report_detail_data (
            id SERIAL PRIMARY KEY,
            report_id INTEGER NOT NULL UNIQUE REFERENCES test_reports(id) ON DELETE CASCADE,
            raw_data JSONB,
            metric_data JSONB,
            tag_metric_data JSONB,
            tag_category_metric_data JSONB,
            case_type_stats JSONB,
            device_stats JSONB,
            api_stats JSONB,
            cases JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("  [完成] 创建 report_detail_data 表")


def create_audio_algorithm_relations_table(cursor):
    """创建音频算法关联表"""
    if check_table_exists(cursor, 'audio_algorithm_relations'):
        print("  [跳过] audio_algorithm_relations 表已存在")
        return

    cursor.execute("""
        CREATE TABLE audio_algorithm_relations (
            id BIGSERIAL PRIMARY KEY,
            audio_id BIGINT NOT NULL REFERENCES audios(id) ON DELETE CASCADE,
            algorithm_type VARCHAR(50) NOT NULL REFERENCES algorithm_definitions(type) ON DELETE CASCADE,
            is_primary BOOLEAN DEFAULT FALSE,
            weight FLOAT DEFAULT 1.0,
            params JSONB,
            deleted BOOLEAN DEFAULT FALSE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_audio_algorithm UNIQUE (audio_id, algorithm_type)
        )
    """)
    cursor.execute("CREATE INDEX idx_audio_algorithm_audio ON audio_algorithm_relations(audio_id)")
    cursor.execute("CREATE INDEX idx_audio_algorithm_type ON audio_algorithm_relations(algorithm_type)")
    print("  [完成] 创建 audio_algorithm_relations 表")


def add_tags_columns(cursor):
    """为 tags 表添加新字段"""
    if check_column_exists(cursor, 'tags', 'category_id'):
        print("  [跳过] tags.category_id 字段已存在")
    else:
        cursor.execute("ALTER TABLE tags ADD COLUMN category_id INTEGER REFERENCES tag_categories(id)")
        print("  [完成] 添加 tags.category_id 字段")

    if check_column_exists(cursor, 'tags', 'sort_order'):
        print("  [跳过] tags.sort_order 字段已存在")
    else:
        cursor.execute("ALTER TABLE tags ADD COLUMN sort_order INTEGER DEFAULT 0")
        print("  [完成] 添加 tags.sort_order 字段")


def add_test_case_groups_column(cursor):
    """为 test_case_groups 表添加 algorithm_type 字段"""
    if check_column_exists(cursor, 'test_case_groups', 'algorithm_type'):
        print("  [跳过] test_case_groups.algorithm_type 字段已存在")
    else:
        cursor.execute("ALTER TABLE test_case_groups ADD COLUMN algorithm_type VARCHAR(50)")
        print("  [完成] 添加 test_case_groups.algorithm_type 字段")


def remove_task_case_columns(cursor):
    """删除 task_case_relations 表的废弃字段"""
    if not check_column_exists(cursor, 'task_case_relations', 'algorithm_type'):
        print("  [跳过] task_case_relations.algorithm_type 字段不存在")
    else:
        cursor.execute("ALTER TABLE task_case_relations DROP COLUMN algorithm_type")
        print("  [完成] 删除 task_case_relations.algorithm_type 字段")

    if not check_column_exists(cursor, 'task_case_relations', 'algorithm_params'):
        print("  [跳过] task_case_relations.algorithm_params 字段不存在")
    else:
        cursor.execute("ALTER TABLE task_case_relations DROP COLUMN algorithm_params")
        print("  [完成] 删除 task_case_relations.algorithm_params 字段")


def add_report_indexes(cursor):
    """为 test_reports 表添加索引"""
    indexes = [
        ("idx_report_task_id", "task_id"),
        ("idx_report_type", "type"),
        ("idx_report_status", "status"),
        ("idx_report_created_at", "created_at"),
        ("idx_report_type_status", "type, status"),
    ]

    for index_name, columns in indexes:
        if check_index_exists(cursor, 'test_reports', index_name):
            print(f"  [跳过] 索引 {index_name} 已存在")
        else:
            cursor.execute(f"CREATE INDEX {index_name} ON test_reports ({columns})")
            print(f"  [完成] 创建索引 {index_name}")


def add_log_indexes(cursor):
    """为 logs 表添加新索引"""
    indexes = [
        ("idx_level", "level"),
        ("idx_category", "category"),
        ("idx_module", "module"),
        ("idx_level_time", "level, time"),
        ("idx_category_time", "category, time"),
    ]

    for index_name, columns in indexes:
        if check_index_exists(cursor, 'logs', index_name):
            print(f"  [跳过] 索引 {index_name} 已存在")
        else:
            cursor.execute(f"CREATE INDEX {index_name} ON logs ({columns})")
            print(f"  [完成] 创建索引 {index_name}")


def alter_column_types_to_bigint(cursor):
    """将多个表的主键类型从 Integer 改为 BigInteger"""
    alterations = [
        ("users", "id", "BIGINT"),
        ("user_permissions", "id", "BIGINT"),
        ("task_tags", "id", "BIGINT"),
        ("test_result_dimensions", "id", "BIGINT"),
        ("upload_chunks", "id", "BIGINT"),
        ("stats_cache", "id", "BIGINT"),
        ("translation_directions", "id", "BIGINT"),
    ]

    for table, column, new_type in alterations:
        try:
            cursor.execute("""
                SELECT data_type FROM information_schema.columns 
                WHERE table_name = %s AND column_name = %s
            """, (table, column))
            result = cursor.fetchone()
            current_type = result[0] if result else None
            
            if current_type and current_type.lower() == 'bigint':
                print(f"  [跳过] {table}.{column} 已是 BIGINT 类型")
            else:
                cursor.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {new_type}")
                print(f"  [完成] {table}.{column} 改为 BIGINT 类型")
        except Exception as e:
            print(f"  [警告] {table}.{column} 类型修改失败: {e}")


def alter_foreign_keys_to_bigint(cursor):
    """修改外键字段类型"""
    alterations = [
        ("test_result_dimensions", "test_result_id", "BIGINT"),
        ("test_result_dimensions", "dimension_id", "BIGINT"),
        ("task_tags", "task_id", "BIGINT"),
        ("task_tags", "tag_id", "BIGINT"),
        ("user_permissions", "user_id", "BIGINT"),
        ("user_permissions", "permission_id", "BIGINT"),
    ]

    for table, column, new_type in alterations:
        try:
            cursor.execute("""
                SELECT data_type FROM information_schema.columns 
                WHERE table_name = %s AND column_name = %s
            """, (table, column))
            result = cursor.fetchone()
            current_type = result[0] if result else None
            
            if current_type and current_type.lower() == 'bigint':
                print(f"  [跳过] {table}.{column} 已是 BIGINT 类型")
            else:
                cursor.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {new_type}")
                print(f"  [完成] {table}.{column} 改为 BIGINT 类型")
        except Exception as e:
            print(f"  [警告] {table}.{column} 类型修改失败: {e}")


def update_algorithm_models_bigint(cursor):
    """更新 algorithm_models 中相关表的 BIGINT 类型"""
    alterations = [
        ("algorithm_definitions", "id", "BIGINT"),
        ("algorithm_dimension_relations", "id", "BIGINT"),
        ("languages", "id", "BIGINT"),
    ]

    for table, column, new_type in alterations:
        try:
            cursor.execute("""
                SELECT data_type FROM information_schema.columns 
                WHERE table_name = %s AND column_name = %s
            """, (table, column))
            result = cursor.fetchone()
            current_type = result[0] if result else None
            
            if current_type and current_type.lower() == 'bigint':
                print(f"  [跳过] {table}.{column} 已是 BIGINT 类型")
            else:
                cursor.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {new_type}")
                print(f"  [完成] {table}.{column} 改为 BIGINT 类型")
        except Exception as e:
            print(f"  [警告] {table}.{column} 类型修改失败: {e}")


def migrate_case_groups_algorithm(cursor):
    """将所有用例分组的 algorithm_type 设置为 speaker_recognition"""
    print("\n迁移用例分组算法类型...")
    
    algorithm_type = 'speaker_recognition'
    
    cursor.execute("""
        SELECT COUNT(*) FROM test_case_groups WHERE algorithm_type IS NULL OR algorithm_type != %s
    """, (algorithm_type,))
    count = cursor.fetchone()[0]
    
    if count == 0:
        print(f"  [跳过] 所有用例分组已设置为 {algorithm_type}")
        return
    
    cursor.execute("""
        UPDATE test_case_groups SET algorithm_type = %s
    """, (algorithm_type,))
    print(f"  [完成] 已将 {count} 个用例分组设置为 {algorithm_type}")


def migrate_audio_algorithm_relations(cursor):
    """将所有音频关联到 speaker_recognition 算法"""
    print("\n迁移音频算法关联...")
    
    algorithm_type = 'speaker_recognition'
    
    cursor.execute("SELECT COUNT(*) FROM audios WHERE deleted = FALSE")
    total_audios = cursor.fetchone()[0]
    
    if total_audios == 0:
        print("  [跳过] 没有音频数据")
        return
    
    cursor.execute("""
        SELECT COUNT(DISTINCT audio_id) FROM audio_algorithm_relations 
        WHERE algorithm_type = %s AND deleted = FALSE
    """, (algorithm_type,))
    existing_count = cursor.fetchone()[0]
    
    if existing_count >= total_audios:
        print(f"  [跳过] 所有音频已关联到 {algorithm_type}")
        return
    
    cursor.execute("""
        INSERT INTO audio_algorithm_relations (audio_id, algorithm_type, is_primary, weight, deleted, created_at, updated_at)
        SELECT id, %s, FALSE, 1.0, FALSE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM audios 
        WHERE deleted = FALSE
        AND id NOT IN (
            SELECT audio_id FROM audio_algorithm_relations 
            WHERE algorithm_type = %s AND deleted = FALSE
        )
        ON CONFLICT (audio_id, algorithm_type) DO NOTHING
    """, (algorithm_type, algorithm_type))
    
    cursor.execute("""
        SELECT COUNT(DISTINCT audio_id) FROM audio_algorithm_relations 
        WHERE algorithm_type = %s AND deleted = FALSE
    """, (algorithm_type,))
    final_count = cursor.fetchone()[0]
    
    print(f"  [完成] 已将 {final_count - existing_count} 个音频关联到 {algorithm_type}")
    print(f"  当前 {algorithm_type} 关联音频数: {final_count}")


def verify_migration(cursor):
    """验证迁移结果"""
    print("\n验证迁移结果...")

    tables_to_check = ['tag_categories', 'report_summaries', 'report_detail_data', 'audio_algorithm_relations']
    for table in tables_to_check:
        exists = check_table_exists(cursor, table)
        status = "✓" if exists else "✗"
        print(f"  {status} 表 {table} {'存在' if exists else '不存在'}")

    indexes_to_check = [
        ('test_reports', 'idx_report_task_id'),
        ('test_reports', 'idx_report_type'),
        ('test_reports', 'idx_report_status'),
        ('logs', 'idx_level'),
        ('logs', 'idx_category'),
    ]
    for table, index in indexes_to_check:
        exists = check_index_exists(cursor, table, index)
        status = "✓" if exists else "✗"
        print(f"  {status} 索引 {index} {'存在' if exists else '不存在'}")
    
    cursor.execute("""
        SELECT COUNT(*) FROM test_case_groups WHERE algorithm_type = 'speaker_recognition'
    """)
    count = cursor.fetchone()[0]
    print(f"  ✓ 用例分组关联 speaker_recognition: {count} 个")
    
    cursor.execute("""
        SELECT COUNT(*) FROM audio_algorithm_relations 
        WHERE algorithm_type = 'speaker_recognition' AND deleted = FALSE
    """)
    count = cursor.fetchone()[0]
    print(f"  ✓ 音频关联 speaker_recognition: {count} 个")


def run_migration():
    """执行迁移"""
    print("=" * 60)
    print("数据库模型迁移 (v20260129 -> v20260423)")
    print(f"数据库: {db_config['host']}:{db_config['port']}/{db_config['database']}")
    print("=" * 60)

    try:
        conn = get_connection()
        conn.autocommit = False
        cursor = conn.cursor()

        print("\n[1/11] 创建新表...")
        create_tag_categories_table(cursor)
        create_report_summaries_table(cursor)
        create_report_detail_data_table(cursor)
        create_audio_algorithm_relations_table(cursor)

        print("\n[2/11] 添加新字段...")
        add_tags_columns(cursor)
        add_test_case_groups_column(cursor)

        print("\n[3/11] 删除废弃字段...")
        remove_task_case_columns(cursor)

        print("\n[4/11] 添加报告索引...")
        add_report_indexes(cursor)

        print("\n[5/11] 添加日志索引...")
        add_log_indexes(cursor)

        print("\n[6/11] 修改主键类型为 BIGINT...")
        alter_column_types_to_bigint(cursor)

        print("\n[7/11] 修改外键类型为 BIGINT...")
        alter_foreign_keys_to_bigint(cursor)

        print("\n[8/11] 更新算法模型 BIGINT 类型...")
        update_algorithm_models_bigint(cursor)

        print("\n[9/11] 迁移用例分组算法类型...")
        migrate_case_groups_algorithm(cursor)

        print("\n[10/11] 迁移音频算法关联...")
        migrate_audio_algorithm_relations(cursor)

        print("\n[11/11] 验证迁移结果...")
        verify_migration(cursor)

        conn.commit()
        cursor.close()
        conn.close()

        print("\n" + "=" * 60)
        print("迁移完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    run_migration()
