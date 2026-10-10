# -*- coding: utf-8 -*-
"""迁移脚本：Benchmark 排行 4 表 + 指标映射种子数据（D1 双轨排行，INT-27）

功能：
- 建 benchmark_rankings 表（排行 ReadModel：查询侧只读，写侧整体刷新）
- 建 benchmark_metric_mappings 表（指标映射单一事实源）+ 设计文档 §5.1 默认映射种子
- 建 benchmark_sources 表（外部基线数据源）
- 建 benchmark_baselines 表（外部基线条目，导入即不可变版本快照）

幂等，可重复执行。

用法:
    python scripts/migrations/202610/add_benchmark_tables.py [--dry-run]

依赖:
    pip install psycopg2-binary python-dotenv
"""
import os
import sys
import argparse
import json

from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print('未配置 DATABASE_URL 环境变量（.env 或环境）', file=sys.stderr)
    sys.exit(1)
parsed = urlparse(DATABASE_URL)
DB_HOST = parsed.hostname
DB_PORT = parsed.port or 5432
DB_NAME = parsed.path.lstrip('/')
DB_USER = parsed.username
DB_PASS = parsed.password


def _table_exists(cur, table):
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,)
    )
    return cur.fetchone() is not None


def _index_exists(cur, index):
    cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (index,))
    return cur.fetchone() is not None


# 设计文档 §5.1 指标映射默认种子（dimension_name, metric_code, metric_name, unit, direction, scenario_tags）
DEFAULT_MAPPINGS = [
    ('WER', 'WER', 'Word Error Rate', '%', 'lower_is_better', ['普通话通用', '噪声']),
    ('CER', 'CER', 'Character Error Rate', '%', 'lower_is_better', ['普通话通用', '噪声']),
    ('takeover_latency', 'TTLW', 'TTLW 末字延迟', 'ms', 'lower_is_better', ['通用']),
    ('tor', 'TAKEOVER_RATE', '对话接话率', '%', 'higher_is_better', ['通用']),
    ('interruption_success_rate', 'INTERRUPTION_SUCCESS', '全双工打断成功率', '%', 'higher_is_better', ['打断场景']),
    ('avg_stop_latency_s', 'STOP_LATENCY', '打断时延', 'ms', 'lower_is_better', ['打断场景']),
    ('avg_recovery_latency_s', 'RECOVERY_LATENCY', '恢复时延', 'ms', 'lower_is_better', ['打断场景']),
    ('interruption_coherence', 'INTERRUPTION_COHERENCE', '打断连贯性', '分', 'higher_is_better', ['打断场景']),
    ('interruption_relevance', 'INTERRUPTION_RELEVANCE', '打断相关性', '分', 'higher_is_better', ['打断场景']),
    ('false_takeover', 'FALSE_TAKEOVER', '误接管率', '%', 'lower_is_better', ['通用']),
    ('BLEU', 'BLEU', 'BLEU', '分', 'higher_is_better', ['翻译']),
    ('COMET', 'COMET', 'COMET', '分', 'higher_is_better', ['翻译']),
    ('MOS', 'MOS', 'MOS', '分', 'higher_is_better', ['TTS']),
    # 主链 voice_llm LLM 裁判维度（实机验收主链实测轨）：评估维度名由用户运行期定义，
    # 单位口径跟随维度自身 score_unit（空=无量纲得分），裁判得分默认越高越好
    ('逐轮话轮评估', 'TURN_EVAL', '逐轮话轮评估', '', 'higher_is_better', ['通用']),
    ('拒识场景裁判', 'REFUSAL_JUDGE', '拒识场景裁判', '', 'higher_is_better', ['通用']),
]

TABLE_DDL = {
    'benchmark_rankings': """
        CREATE TABLE benchmark_rankings (
            id BIGSERIAL PRIMARY KEY,
            source VARCHAR(30) NOT NULL,
            published_task_id BIGINT,
            published_task_version INTEGER,
            report_id BIGINT,
            baseline_id BIGINT,
            subject_name VARCHAR(255) NOT NULL,
            subject_type VARCHAR(30),
            device_type VARCHAR(30),
            benchmark_suite VARCHAR(120),
            category VARCHAR(30),
            metric_code VARCHAR(60) NOT NULL,
            metric_name VARCHAR(120),
            metric_value DOUBLE PRECISION NOT NULL,
            unit VARCHAR(20),
            direction VARCHAR(20) NOT NULL,
            rank INTEGER,
            total INTEGER,
            percentile DOUBLE PRECISION,
            score100 DOUBLE PRECISION,
            gap_best DOUBLE PRECISION,
            gap_median DOUBLE PRECISION,
            delta_external DOUBLE PRECISION,
            scenario_key VARCHAR(120),
            computed_at TIMESTAMP NOT NULL DEFAULT NOW(),
            -- 排行行唯一性兜底（并发重算防重复行）：组内每来源每主体至多一行
            CONSTRAINT uq_benchmark_ranking_row
                UNIQUE (category, metric_code, scenario_key, source, subject_name)
        )
    """,
    'benchmark_metric_mappings': """
        CREATE TABLE benchmark_metric_mappings (
            id BIGSERIAL PRIMARY KEY,
            dimension_name VARCHAR(120) NOT NULL,
            metric_code VARCHAR(60) NOT NULL,
            metric_name VARCHAR(120),
            unit VARCHAR(20),
            direction VARCHAR(20) NOT NULL,
            scenario_tags JSONB,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """,
    'benchmark_sources': """
        CREATE TABLE benchmark_sources (
            id BIGSERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            provider VARCHAR(255),
            source_type VARCHAR(30) NOT NULL DEFAULT 'manual',
            url VARCHAR(1024),
            version VARCHAR(60),
            description TEXT,
            created_by VARCHAR(120),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """,
    'benchmark_baselines': """
        CREATE TABLE benchmark_baselines (
            id BIGSERIAL PRIMARY KEY,
            source_id BIGINT NOT NULL,
            category VARCHAR(30) NOT NULL,
            model_name VARCHAR(255) NOT NULL,
            vendor VARCHAR(255),
            metric_code VARCHAR(60) NOT NULL,
            metric_name VARCHAR(120),
            value DOUBLE PRECISION NOT NULL,
            unit VARCHAR(20),
            direction VARCHAR(20) NOT NULL,
            scenario_tags JSONB,
            sample_size INTEGER,
            metric_date VARCHAR(20),
            version INTEGER NOT NULL DEFAULT 1,
            is_current BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """,
}

INDEX_DDL = [
    ('idx_benchmark_ranking_group',
     'CREATE INDEX idx_benchmark_ranking_group ON benchmark_rankings (category, metric_code, scenario_key, source)'),
    ('idx_benchmark_ranking_subject',
     'CREATE INDEX idx_benchmark_ranking_subject ON benchmark_rankings (subject_name)'),
    ('idx_benchmark_ranking_pt',
     'CREATE INDEX idx_benchmark_ranking_pt ON benchmark_rankings (published_task_id)'),
    ('idx_benchmark_ranking_baseline',
     'CREATE INDEX idx_benchmark_ranking_baseline ON benchmark_rankings (baseline_id)'),
    ('idx_benchmark_mapping_dimension',
     'CREATE INDEX idx_benchmark_mapping_dimension ON benchmark_metric_mappings (dimension_name)'),
    ('idx_benchmark_source_type',
     'CREATE INDEX idx_benchmark_source_type ON benchmark_sources (source_type)'),
    ('idx_benchmark_baseline_current',
     'CREATE INDEX idx_benchmark_baseline_current ON benchmark_baselines (source_id, category, is_current)'),
    ('idx_benchmark_baseline_metric',
     'CREATE INDEX idx_benchmark_baseline_metric ON benchmark_baselines (category, metric_code)'),
]


def main(dry_run=False):
    import psycopg2
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    cur = conn.cursor()
    total_steps = 0

    # 1. 建表
    for table, ddl in TABLE_DDL.items():
        if _table_exists(cur, table):
            print(f'SKIP: 表 {table} 已存在')
            continue
        print(f'APPLY: 创建表 {table}')
        if not dry_run:
            cur.execute(ddl)
        total_steps += 1

    # 2. 建索引
    for index, ddl in INDEX_DDL:
        if _index_exists(cur, index):
            print(f'SKIP: 索引 {index} 已存在')
            continue
        print(f'APPLY: 创建索引 {index}')
        if not dry_run:
            cur.execute(ddl)
        total_steps += 1

    # 3. 指标映射默认种子（幂等：按 dimension_name 去重）
    if _table_exists(cur, 'benchmark_metric_mappings'):
        for (dim, code, name, unit, direction, tags) in DEFAULT_MAPPINGS:
            cur.execute(
                "SELECT 1 FROM benchmark_metric_mappings WHERE dimension_name = %s", (dim,))
            if cur.fetchone():
                print(f'SKIP: 指标映射 {dim} 已存在')
                continue
            print(f'APPLY: 指标映射种子 {dim} -> {code}')
            if not dry_run:
                cur.execute(
                    """
                    INSERT INTO benchmark_metric_mappings
                        (dimension_name, metric_code, metric_name, unit, direction, scenario_tags, active)
                    VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                    """,
                    (dim, code, name, unit, direction, json.dumps(tags)),
                )
            total_steps += 1

    if dry_run:
        conn.rollback()
        print(f'[DRY-RUN] 共 {total_steps} 步待执行')
    else:
        conn.commit()
        print(f'完成：共执行 {total_steps} 步')
    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Benchmark 排行 4 表 + 指标映射种子迁移')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    args = parser.parse_args()
    main(dry_run=args.dry_run)
