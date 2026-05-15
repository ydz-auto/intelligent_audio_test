"""
数据库迁移脚本：拆分报告 summary 字段到独立表

功能：
- 创建 report_summaries 表（存储小数据量摘要）
- 创建 report_detail_data 表（存储大数据量详情）
- 迁移旧数据从 test_reports.summary 到新表
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, timedelta

engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
Session = sessionmaker(bind=engine)

def utc8now():
    return datetime.now(timezone(timedelta(hours=8)))

def create_tables():
    """创建新表"""
    print(f"数据库: {Config.SQLALCHEMY_DATABASE_URI}")

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'report_summaries'
        """))
        if not result.fetchone():
            conn.execute(text("""
                CREATE TABLE report_summaries (
                    id SERIAL PRIMARY KEY,
                    report_id INTEGER NOT NULL UNIQUE,
                    total_cases INTEGER DEFAULT 0,
                    completed_cases INTEGER DEFAULT 0,
                    failed_cases INTEGER DEFAULT 0,
                    pass_rate REAL DEFAULT 0,
                    dimension_values JSONB,
                    duration REAL DEFAULT 0,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    case_categories JSONB,
                    all_case_tags JSONB,
                    devices JSONB,
                    apis JSONB,
                    resources JSONB,
                    resource_headers JSONB,
                    all_metrics JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("成功创建 report_summaries 表")
        else:
            print("表 report_summaries 已存在，跳过创建")

        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'report_detail_data'
        """))
        if not result.fetchone():
            conn.execute(text("""
                CREATE TABLE report_detail_data (
                    id SERIAL PRIMARY KEY,
                    report_id INTEGER NOT NULL UNIQUE,
                    raw_data JSONB,
                    metric_data JSONB,
                    tag_metric_data JSONB,
                    case_type_stats JSONB,
                    cases JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("成功创建 report_detail_data 表")
        else:
            print("表 report_detail_data 已存在，跳过创建")

        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_name = 'fk_report_summaries_report_id'
                ) THEN
                    ALTER TABLE report_summaries
                    ADD CONSTRAINT fk_report_summaries_report_id
                    FOREIGN KEY (report_id) REFERENCES test_reports(id) ON DELETE CASCADE;
                END IF;
            END $$;
        """))
        conn.commit()
        print("report_summaries 外键约束已添加")

        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_name = 'fk_report_detail_data_report_id'
                ) THEN
                    ALTER TABLE report_detail_data
                    ADD CONSTRAINT fk_report_detail_data_report_id
                    FOREIGN KEY (report_id) REFERENCES test_reports(id) ON DELETE CASCADE;
                END IF;
            END $$;
        """))
        conn.commit()
        print("report_detail_data 外键约束已添加")

    return True

def migrate_data():
    """迁移旧数据"""
    print("开始迁移旧数据...")

    session = Session()
    try:
        result = session.execute(text("""
            SELECT id, summary FROM test_reports WHERE summary IS NOT NULL
        """))
        reports = result.fetchall()

        if not reports:
            print("没有需要迁移的数据")
            return True

        print(f"找到 {len(reports)} 条报告需要迁移")

        for report_id, summary_json in reports:
            try:
                import json

                if isinstance(summary_json, str):
                    summary = json.loads(summary_json)
                else:
                    summary = summary_json or {}

                now = utc8now()

                summary_info_values = {
                    'report_id': report_id,
                    'total_cases': summary.get('total_cases', 0) or summary.get('totalCases', 0) or 0,
                    'completed_cases': summary.get('completed_cases', 0) or summary.get('completedCases', 0) or 0,
                    'failed_cases': summary.get('failed_cases', 0) or summary.get('failedCases', 0) or 0,
                    'pass_rate': summary.get('pass_rate', 0) or summary.get('passRate', 0) or 0,
                    'dimension_values': json.dumps(summary.get('dimension_values', []), ensure_ascii=False),
                    'duration': summary.get('duration', 0) or 0,
                    'started_at': summary.get('started_at'),
                    'completed_at': summary.get('completed_at'),
                    'case_categories': json.dumps(summary.get('case_categories', []), ensure_ascii=False),
                    'all_case_tags': json.dumps(summary.get('all_case_tags', []) or summary.get('all_tags', []), ensure_ascii=False),
                    'devices': json.dumps(summary.get('devices', []), ensure_ascii=False),
                    'apis': json.dumps(summary.get('apis', []), ensure_ascii=False),
                    'resources': json.dumps(summary.get('resources', []), ensure_ascii=False),
                    'resource_headers': json.dumps(summary.get('resource_headers', []) or summary.get('resourceHeaders', []), ensure_ascii=False),
                    'all_metrics': json.dumps(summary.get('all_metrics', []) or summary.get('allMetrics', []), ensure_ascii=False),
                    'created_at': now,
                    'updated_at': now,
                }

                session.execute(
                    text("""
                        INSERT INTO report_summaries (report_id, total_cases, completed_cases, failed_cases,
                            pass_rate, dimension_values, duration, started_at, completed_at,
                            case_categories, all_case_tags, devices, apis, resources,
                            resource_headers, all_metrics, created_at, updated_at)
                        VALUES (:report_id, :total_cases, :completed_cases, :failed_cases,
                            :pass_rate, CAST(:dimension_values AS JSONB), :duration, :started_at, :completed_at,
                            CAST(:case_categories AS JSONB), CAST(:all_case_tags AS JSONB), CAST(:devices AS JSONB), CAST(:apis AS JSONB), CAST(:resources AS JSONB),
                            CAST(:resource_headers AS JSONB), CAST(:all_metrics AS JSONB), :created_at, :updated_at)
                    """),
                    summary_info_values
                )

                detail_data_values = {
                    'report_id': report_id,
                    'raw_data': json.dumps(summary.get('raw_data', []) or summary.get('rawData', []), ensure_ascii=False),
                    'metric_data': json.dumps(summary.get('metric_data', []), ensure_ascii=False),
                    'tag_metric_data': json.dumps(summary.get('tag_metric_data', []) or summary.get('tagMetricData', []), ensure_ascii=False),
                    'case_type_stats': json.dumps(summary.get('case_type_stats', []) or summary.get('caseTypeStats', []), ensure_ascii=False),
                    'cases': json.dumps(summary.get('cases', []), ensure_ascii=False),
                    'created_at': now,
                    'updated_at': now,
                }

                session.execute(
                    text("""
                        INSERT INTO report_detail_data (report_id, raw_data, metric_data,
                            tag_metric_data, case_type_stats, cases, created_at, updated_at)
                        VALUES (:report_id, CAST(:raw_data AS JSONB), CAST(:metric_data AS JSONB),
                            CAST(:tag_metric_data AS JSONB), CAST(:case_type_stats AS JSONB), CAST(:cases AS JSONB), :created_at, :updated_at)
                    """),
                    detail_data_values
                )

                session.commit()
                print(f"  迁移报告 ID={report_id} 成功")

            except Exception as e:
                print(f"  迁移报告 ID={report_id} 失败: {e}")
                session.rollback()
                continue

        print(f"成功迁移 {len(reports)} 条报告")
        return True

    except Exception as e:
        print(f"迁移数据失败: {e}")
        return False
    finally:
        session.close()

if __name__ == '__main__':
    print("=" * 60)
    print("报告 Summary 字段拆分迁移 (PostgreSQL)")
    print("=" * 60)

    success = create_tables()
    if success:
        success = migrate_data()

    if success:
        print("\n迁移完成！")
    else:
        print("\n迁移失败！")
        sys.exit(1)
