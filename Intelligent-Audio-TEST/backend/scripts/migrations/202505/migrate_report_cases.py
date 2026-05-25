# -*- coding: utf-8 -*-
"""
数据库迁移脚本：重构 report_cases 表结构

功能：
- 删除旧的 report_cases 表（一个报告一行，cases 字段存储 JSON 数组）
- 创建新的 report_cases 表（一个 case 一行记录）
- 迁移旧数据到新表
- 修复 test_case_id 类型为 VARCHAR(50)（支持 UUID 格式）
- 更新 tags 格式为 [{name: "tag1"}, {name: "tag2"}]

使用方法：
    # 方式1：使用命令行参数
    python migrate_report_cases.py --db-uri "postgresql://user:pass@localhost:5432/dbname"
    
    # 方式2：使用环境变量
    export DATABASE_URI="postgresql://user:pass@localhost:5432/dbname"
    python migrate_report_cases.py
    
    # 方式3：直接修改脚本中的默认值
    python migrate_report_cases.py
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone, timedelta

try:
    from sqlalchemy import create_engine, text
except ImportError:
    print("请安装 sqlalchemy: pip install sqlalchemy")
    sys.exit(1)

DEFAULT_DB_URI = "postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test"


def utc8now():
    return datetime.now(timezone(timedelta(hours=8)))


def get_db_uri():
    parser = argparse.ArgumentParser(description="迁移 report_cases 表结构")
    parser.add_argument(
        "--db-uri",
        type=str,
        default=None,
        help="数据库连接字符串，例如: postgresql://user:pass@localhost:5432/dbname"
    )
    args = parser.parse_args()
    
    if args.db_uri:
        return args.db_uri
    
    env_uri = os.environ.get("DATABASE_URI") or os.environ.get("DATABASE_URL")
    if env_uri:
        return env_uri
    
    return DEFAULT_DB_URI


def convert_tags_to_object_array(tags):
    if tags is None:
        return []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except:
            return []
    if not isinstance(tags, list):
        return []
    
    result = []
    for tag in tags:
        if isinstance(tag, dict):
            if 'name' in tag:
                result.append({'name': tag['name']})
            elif 'tagName' in tag:
                result.append({'name': tag['tagName']})
        elif isinstance(tag, str):
            result.append({'name': tag})
    return result


def migrate_report_cases(db_uri):
    print(f"数据库: {db_uri}")
    
    engine = create_engine(db_uri)
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'report_cases'
        """))
        old_table_exists = result.fetchone() is not None
        
        if old_table_exists:
            result = conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'report_cases' AND column_name = 'cases'
            """))
            has_cases_column = result.fetchone() is not None
            
            if has_cases_column:
                print("检测到旧版 report_cases 表结构，开始迁移...")
                
                old_data = conn.execute(text("""
                    SELECT report_id, cases FROM report_cases
                """)).fetchall()
                
                print(f"找到 {len(old_data)} 条旧记录")
                
                conn.execute(text("DROP TABLE IF EXISTS report_cases CASCADE"))
                conn.commit()
                print("已删除旧表")
            else:
                result = conn.execute(text("""
                    SELECT data_type FROM information_schema.columns
                    WHERE table_name = 'report_cases' AND column_name = 'test_case_id'
                """))
                row = result.fetchone()
                if row and row[0] in ('integer', 'bigint'):
                    print("检测到 test_case_id 为整数类型，需要修改为 VARCHAR(50)")
                    
                    old_data = conn.execute(text("""
                        SELECT id, report_id, test_case_id, name, description, category, 
                               tags, metrics, results, audios, reference_params, 
                               algorithm_results, algorithm_type, logs, created_at, updated_at
                        FROM report_cases
                    """)).fetchall()
                    
                    print(f"备份 {len(old_data)} 条记录")
                    
                    conn.execute(text("DROP TABLE IF EXISTS report_cases CASCADE"))
                    conn.commit()
                    print("已删除旧表，将创建新表")
                    
                    conn.execute(text("""
                        CREATE TABLE report_cases (
                            id SERIAL PRIMARY KEY,
                            report_id INTEGER NOT NULL REFERENCES test_reports(id) ON DELETE CASCADE,
                            test_case_id VARCHAR(50),
                            name VARCHAR(500),
                            description TEXT,
                            category VARCHAR(255),
                            tags JSONB,
                            metrics JSONB,
                            results JSONB,
                            audios JSONB,
                            reference_params JSONB,
                            algorithm_results JSONB,
                            algorithm_type VARCHAR(100),
                            logs TEXT,
                            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                    
                    conn.execute(text("CREATE INDEX idx_report_cases_report_id ON report_cases(report_id)"))
                    conn.execute(text("CREATE INDEX idx_report_cases_test_case_id ON report_cases(test_case_id)"))
                    conn.execute(text("CREATE INDEX idx_report_cases_category ON report_cases(category)"))
                    conn.commit()
                    print("成功创建新 report_cases 表")
                    
                    migrated_count = 0
                    for row in old_data:
                        try:
                            tags = row[6]
                            if isinstance(tags, str):
                                tags = json.loads(tags)
                            tags = convert_tags_to_object_array(tags)
                            
                            conn.execute(text("""
                                INSERT INTO report_cases 
                                (id, report_id, test_case_id, name, description, category, tags, metrics, 
                                 results, audios, reference_params, algorithm_results, algorithm_type, 
                                 logs, created_at, updated_at)
                                VALUES 
                                (:id, :report_id, :test_case_id, :name, :description, :category, 
                                 :tags::jsonb, :metrics::jsonb, :results::jsonb, :audios::jsonb, 
                                 :reference_params::jsonb, :algorithm_results::jsonb, :algorithm_type, 
                                 :logs, :created_at, :updated_at)
                            """), {
                                'id': row[0],
                                'report_id': row[1],
                                'test_case_id': str(row[2]) if row[2] else None,
                                'name': row[3],
                                'description': row[4],
                                'category': row[5],
                                'tags': json.dumps(tags, ensure_ascii=False),
                                'metrics': row[7] if isinstance(row[7], str) else json.dumps(row[7], ensure_ascii=False),
                                'results': row[8] if isinstance(row[8], str) else json.dumps(row[8], ensure_ascii=False),
                                'audios': row[9] if isinstance(row[9], str) else json.dumps(row[9], ensure_ascii=False),
                                'reference_params': row[10] if isinstance(row[10], str) else json.dumps(row[10], ensure_ascii=False) if row[10] else None,
                                'algorithm_results': row[11] if isinstance(row[11], str) else json.dumps(row[11], ensure_ascii=False) if row[11] else None,
                                'algorithm_type': row[12],
                                'logs': row[13],
                                'created_at': row[14] or utc8now(),
                                'updated_at': row[15] or utc8now()
                            })
                            migrated_count += 1
                        except Exception as e:
                            print(f"迁移记录 {row[0]} 时出错: {e}")
                            continue
                    
                    conn.commit()
                    print(f"成功迁移 {migrated_count} 条记录")
                    return
                else:
                    print("report_cases 表结构正确，检查 tags 格式...")
                    
                    old_data = conn.execute(text("""
                        SELECT id, tags FROM report_cases
                    """)).fetchall()
                    
                    updated_count = 0
                    for row in old_data:
                        try:
                            tags = row[1]
                            if isinstance(tags, str):
                                tags = json.loads(tags)
                            
                            if not isinstance(tags, list):
                                continue
                            
                            needs_update = False
                            for tag in tags:
                                if isinstance(tag, str):
                                    needs_update = True
                                    break
                            
                            if needs_update:
                                new_tags = convert_tags_to_object_array(tags)
                                conn.execute(text("""
                                    UPDATE report_cases SET tags = :tags::jsonb WHERE id = :id
                                """), {
                                    'id': row[0],
                                    'tags': json.dumps(new_tags, ensure_ascii=False)
                                })
                                updated_count += 1
                        except Exception as e:
                            print(f"更新记录 {row[0]} tags 时出错: {e}")
                            continue
                    
                    conn.commit()
                    if updated_count > 0:
                        print(f"成功更新 {updated_count} 条记录的 tags 格式")
                    else:
                        print("tags 格式已正确，无需更新")
                    return
        else:
            print("report_cases 表不存在，将创建新表")
        
        conn.execute(text("""
            CREATE TABLE report_cases (
                id SERIAL PRIMARY KEY,
                report_id INTEGER NOT NULL REFERENCES test_reports(id) ON DELETE CASCADE,
                test_case_id VARCHAR(50),
                name VARCHAR(500),
                description TEXT,
                category VARCHAR(255),
                tags JSONB,
                metrics JSONB,
                results JSONB,
                audios JSONB,
                reference_params JSONB,
                algorithm_results JSONB,
                algorithm_type VARCHAR(100),
                logs TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        conn.execute(text("CREATE INDEX idx_report_cases_report_id ON report_cases(report_id)"))
        conn.execute(text("CREATE INDEX idx_report_cases_test_case_id ON report_cases(test_case_id)"))
        conn.execute(text("CREATE INDEX idx_report_cases_category ON report_cases(category)"))
        
        conn.commit()
        print("成功创建新 report_cases 表")
        
        if old_table_exists and has_cases_column and old_data:
            migrated_count = 0
            for report_id, cases_json in old_data:
                if not cases_json:
                    continue
                
                try:
                    if isinstance(cases_json, str):
                        cases = json.loads(cases_json)
                    else:
                        cases = cases_json
                    
                    if not isinstance(cases, list):
                        continue
                    
                    for case_item in cases:
                        if not isinstance(case_item, dict):
                            continue
                        
                        test_case_id = case_item.get('id')
                        name = case_item.get('name')
                        description = case_item.get('description')
                        category = case_item.get('category')
                        tags = convert_tags_to_object_array(case_item.get('tags', []))
                        metrics = case_item.get('metrics', {})
                        results = case_item.get('results', [])
                        audios = case_item.get('audios', [])
                        reference_params = case_item.get('reference_params')
                        algorithm_results = case_item.get('algorithm_results')
                        algorithm_type = case_item.get('algorithm_type')
                        logs = case_item.get('logs')
                        
                        conn.execute(text("""
                            INSERT INTO report_cases 
                            (report_id, test_case_id, name, description, category, tags, metrics, results, audios, 
                             reference_params, algorithm_results, algorithm_type, logs, created_at, updated_at)
                            VALUES 
                            (:report_id, :test_case_id, :name, :description, :category, :tags::jsonb, :metrics::jsonb, 
                             :results::jsonb, :audios::jsonb, :reference_params::jsonb, :algorithm_results::jsonb, 
                             :algorithm_type, :logs, :created_at, :updated_at)
                        """), {
                            'report_id': report_id,
                            'test_case_id': str(test_case_id) if test_case_id else None,
                            'name': name,
                            'description': description,
                            'category': category,
                            'tags': json.dumps(tags, ensure_ascii=False),
                            'metrics': json.dumps(metrics, ensure_ascii=False),
                            'results': json.dumps(results, ensure_ascii=False),
                            'audios': json.dumps(audios, ensure_ascii=False),
                            'reference_params': json.dumps(reference_params, ensure_ascii=False) if reference_params else None,
                            'algorithm_results': json.dumps(algorithm_results, ensure_ascii=False) if algorithm_results else None,
                            'algorithm_type': algorithm_type,
                            'logs': logs,
                            'created_at': utc8now(),
                            'updated_at': utc8now()
                        })
                        migrated_count += 1
                    
                except Exception as e:
                    print(f"迁移报告 {report_id} 时出错: {e}")
                    continue
            
            conn.commit()
            print(f"成功迁移 {migrated_count} 条 case 记录")


if __name__ == "__main__":
    db_uri = get_db_uri()
    migrate_report_cases(db_uri)
    print("迁移完成")
