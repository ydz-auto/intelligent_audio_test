"""
数据库迁移脚本：拆分报告 JSON 字段到新表
解决历史报告页面加载慢的问题

运行方式：
python backend/scripts/migrations/202605/split_report_json_fields.py

或直接执行 SQL：
psql -U intelligent_audio_test -d intelligent_audio_test -c "
-- 创建新表
CREATE TABLE IF NOT EXISTS report_summary_meta (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
    dimension_values JSONB,
    case_categories JSONB,
    all_case_tags JSONB,
    devices JSONB,
    apis JSONB,
    resources JSONB,
    resource_headers JSONB,
    all_metrics JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS report_raw_data (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
    raw_data JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS report_cases (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
    cases JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS report_metric_stats (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
    metric_data JSONB,
    tag_metric_data JSONB,
    tag_category_metric_data JSONB,
    case_type_stats JSONB,
    device_stats JSONB,
    api_stats JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS report_comparison_matrix (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
    comparison_matrix JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_report_summary_meta_report_id ON report_summary_meta (report_id);
CREATE INDEX IF NOT EXISTS idx_report_raw_data_report_id ON report_raw_data (report_id);
CREATE INDEX IF NOT EXISTS idx_report_cases_report_id ON report_cases (report_id);
CREATE INDEX IF NOT EXISTS idx_report_metric_stats_report_id ON report_metric_stats (report_id);
CREATE INDEX IF NOT EXISTS idx_report_comparison_matrix_report_id ON report_comparison_matrix (report_id);

-- 迁移数据
INSERT INTO report_summary_meta (report_id, dimension_values, case_categories, all_case_tags, devices, apis, resources, resource_headers, all_metrics, created_at, updated_at)
SELECT report_id, dimension_values, case_categories, all_case_tags, devices, apis, resources, resource_headers, all_metrics, created_at, updated_at
FROM report_summaries WHERE dimension_values IS NOT NULL OR case_categories IS NOT NULL;

INSERT INTO report_raw_data (report_id, raw_data, created_at, updated_at)
SELECT report_id, raw_data, created_at, updated_at
FROM report_detail_data WHERE raw_data IS NOT NULL;

INSERT INTO report_cases (report_id, cases, created_at, updated_at)
SELECT report_id, cases, created_at, updated_at
FROM report_detail_data WHERE cases IS NOT NULL;

INSERT INTO report_metric_stats (report_id, metric_data, tag_metric_data, tag_category_metric_data, case_type_stats, device_stats, api_stats, created_at, updated_at)
SELECT report_id, metric_data, tag_metric_data, tag_category_metric_data, case_type_stats, device_stats, api_stats, created_at, updated_at
FROM report_detail_data WHERE metric_data IS NOT NULL OR tag_metric_data IS NOT NULL;

INSERT INTO report_comparison_matrix (report_id, comparison_matrix, created_at, updated_at)
SELECT report_id, comparison_matrix, created_at, updated_at
FROM report_detail_data WHERE comparison_matrix IS NOT NULL;

-- 删除旧表的 JSON 字段
ALTER TABLE report_summaries DROP COLUMN IF EXISTS dimension_values;
ALTER TABLE report_summaries DROP COLUMN IF EXISTS case_categories;
ALTER TABLE report_summaries DROP COLUMN IF EXISTS all_case_tags;
ALTER TABLE report_summaries DROP COLUMN IF EXISTS devices;
ALTER TABLE report_summaries DROP COLUMN IF EXISTS apis;
ALTER TABLE report_summaries DROP COLUMN IF EXISTS resources;
ALTER TABLE report_summaries DROP COLUMN IF EXISTS resource_headers;
ALTER TABLE report_summaries DROP COLUMN IF EXISTS all_metrics;

-- 删除 report_detail_data 表（数据已迁移到新表）
DROP TABLE IF EXISTS report_detail_data;

-- 删除 Report 表的旧 JSON 字段
ALTER TABLE test_reports DROP COLUMN IF EXISTS summary;
ALTER TABLE test_reports DROP COLUMN IF EXISTS comparison_data;
ALTER TABLE test_reports DROP COLUMN IF EXISTS test_reports_cases;
"
"""

import os
import psycopg2
from dotenv import load_dotenv


def get_db_config():
    """从环境变量获取数据库配置"""
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    
    return {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'port': int(os.environ.get('DB_PORT', 5432)),
        'database': os.environ.get('DB_NAME', 'intelligent_audio_test'),
        'user': os.environ.get('DB_USER', 'intelligent_audio_test'),
        'password': os.environ.get('DB_PASSWORD', 'intelligent_audio_test666'),
    }


def migrate():
    """执行迁移"""
    config = get_db_config()
    
    print(f"连接数据库: {config['host']}:{config['port']}/{config['database']}")
    
    conn = psycopg2.connect(**config)
    conn.autocommit = True
    cursor = conn.cursor()
    
    add_task_ids_sql = """
    ALTER TABLE report_summaries ADD COLUMN IF NOT EXISTS task_ids JSONB;
    """
    
    try:
        cursor.execute(add_task_ids_sql)
        print("成功添加 report_summaries.task_ids 字段")
    except Exception as e:
        print(f"添加 task_ids 字段失败: {e}")
    
    create_tables_sql = """
    CREATE TABLE IF NOT EXISTS report_summary_meta (
        id BIGSERIAL PRIMARY KEY,
        report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
        dimension_values JSONB,
        case_categories JSONB,
        all_case_tags JSONB,
        devices JSONB,
        apis JSONB,
        resources JSONB,
        resource_headers JSONB,
        all_metrics JSONB,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS report_raw_data (
        id BIGSERIAL PRIMARY KEY,
        report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
        raw_data JSONB,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS report_cases (
        id BIGSERIAL PRIMARY KEY,
        report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
        cases JSONB,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS report_metric_stats (
        id BIGSERIAL PRIMARY KEY,
        report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
        metric_data JSONB,
        tag_metric_data JSONB,
        tag_category_metric_data JSONB,
        case_type_stats JSONB,
        device_stats JSONB,
        api_stats JSONB,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS report_comparison_matrix (
        id BIGSERIAL PRIMARY KEY,
        report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
        comparison_matrix JSONB,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """
    
    try:
        cursor.execute(create_tables_sql)
        print("成功创建新表")
    except Exception as e:
        print(f"创建新表失败: {e}")
    
    create_indexes_sql = """
    CREATE INDEX IF NOT EXISTS idx_report_summary_meta_report_id ON report_summary_meta (report_id);
    CREATE INDEX IF NOT EXISTS idx_report_raw_data_report_id ON report_raw_data (report_id);
    CREATE INDEX IF NOT EXISTS idx_report_cases_report_id ON report_cases (report_id);
    CREATE INDEX IF NOT EXISTS idx_report_metric_stats_report_id ON report_metric_stats (report_id);
    CREATE INDEX IF NOT EXISTS idx_report_comparison_matrix_report_id ON report_comparison_matrix (report_id);
    """
    
    try:
        cursor.execute(create_indexes_sql)
        print("成功创建索引")
    except Exception as e:
        print(f"创建索引失败: {e}")
    
    migrate_summary_meta_sql = """
    INSERT INTO report_summary_meta (report_id, dimension_values, case_categories, all_case_tags, devices, apis, resources, resource_headers, all_metrics, created_at, updated_at)
    SELECT report_id, dimension_values, case_categories, all_case_tags, devices, apis, resources, resource_headers, all_metrics, created_at, updated_at
    FROM report_summaries WHERE dimension_values IS NOT NULL OR case_categories IS NOT NULL
    ON CONFLICT (report_id) DO NOTHING;
    """
    
    try:
        cursor.execute(migrate_summary_meta_sql)
        print("成功迁移 report_summary_meta 数据")
    except Exception as e:
        print(f"迁移 report_summary_meta 数据失败: {e}")
    
    migrate_raw_data_sql = """
    INSERT INTO report_raw_data (report_id, raw_data, created_at, updated_at)
    SELECT report_id, raw_data, created_at, updated_at
    FROM report_detail_data WHERE raw_data IS NOT NULL
    ON CONFLICT (report_id) DO NOTHING;
    """
    
    try:
        cursor.execute(migrate_raw_data_sql)
        print("成功迁移 report_raw_data 数据")
    except Exception as e:
        print(f"迁移 report_raw_data 数据失败: {e}")
    
    migrate_cases_sql = """
    INSERT INTO report_cases (report_id, cases, created_at, updated_at)
    SELECT report_id, cases, created_at, updated_at
    FROM report_detail_data WHERE cases IS NOT NULL
    ON CONFLICT (report_id) DO NOTHING;
    """
    
    try:
        cursor.execute(migrate_cases_sql)
        print("成功迁移 report_cases 数据")
    except Exception as e:
        print(f"迁移 report_cases 数据失败: {e}")
    
    migrate_metric_stats_sql = """
    INSERT INTO report_metric_stats (report_id, metric_data, tag_metric_data, tag_category_metric_data, case_type_stats, device_stats, api_stats, created_at, updated_at)
    SELECT report_id, metric_data, tag_metric_data, tag_category_metric_data, case_type_stats, device_stats, api_stats, created_at, updated_at
    FROM report_detail_data WHERE metric_data IS NOT NULL OR tag_metric_data IS NOT NULL
    ON CONFLICT (report_id) DO NOTHING;
    """
    
    try:
        cursor.execute(migrate_metric_stats_sql)
        print("成功迁移 report_metric_stats 数据")
    except Exception as e:
        print(f"迁移 report_metric_stats 数据失败: {e}")
    
    migrate_comparison_matrix_sql = """
    INSERT INTO report_comparison_matrix (report_id, comparison_matrix, created_at, updated_at)
    SELECT report_id, comparison_matrix, created_at, updated_at
    FROM report_detail_data WHERE comparison_matrix IS NOT NULL
    ON CONFLICT (report_id) DO NOTHING;
    """
    
    try:
        cursor.execute(migrate_comparison_matrix_sql)
        print("成功迁移 report_comparison_matrix 数据")
    except Exception as e:
        print(f"迁移 report_comparison_matrix 数据失败: {e}")
    
    drop_old_columns_sql = """
    ALTER TABLE report_summaries DROP COLUMN IF EXISTS dimension_values;
    ALTER TABLE report_summaries DROP COLUMN IF EXISTS case_categories;
    ALTER TABLE report_summaries DROP COLUMN IF EXISTS all_case_tags;
    ALTER TABLE report_summaries DROP COLUMN IF EXISTS devices;
    ALTER TABLE report_summaries DROP COLUMN IF EXISTS apis;
    ALTER TABLE report_summaries DROP COLUMN IF EXISTS resources;
    ALTER TABLE report_summaries DROP COLUMN IF EXISTS resource_headers;
    ALTER TABLE report_summaries DROP COLUMN IF EXISTS all_metrics;
    """
    
    try:
        cursor.execute(drop_old_columns_sql)
        print("成功删除 report_summaries 的旧 JSON 字段")
    except Exception as e:
        print(f"删除 report_summaries 的旧 JSON 字段失败: {e}")
    
    drop_report_columns_sql = """
    ALTER TABLE test_reports DROP COLUMN IF EXISTS summary;
    ALTER TABLE test_reports DROP COLUMN IF EXISTS comparison_data;
    ALTER TABLE test_reports DROP COLUMN IF EXISTS test_reports_cases;
    """
    
    try:
        cursor.execute(drop_report_columns_sql)
        print("成功删除 test_reports 的旧 JSON 字段")
    except Exception as e:
        print(f"删除 test_reports 的旧 JSON 字段失败: {e}")
    
    cursor.close()
    conn.close()
    
    print("\n迁移完成")


if __name__ == "__main__":
    migrate()