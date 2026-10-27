# -*- coding: utf-8 -*-
"""INT-2100 验收③：进程内真实链路生成新报告，快照 all_case_tags 条目含分类。

环境口径（2026-10-23 起）：禁本地栈；docker :15000 只跑 V9.7.31 分支（无本卡
代码）。故在隔离 sqlite 库 + 进程内 gRPC 回环（真实 task_service TagConfigService
servicer）下，走真实 report_service 代码链生成报告快照：

1. 建全量表（scripts.create_all_tables._import_all_models → Base.metadata.create_all）；
2. 种子：标签分类 + 带分类标签（含「未分类」标签）+ 字符串 tags 用例；
3. 起进程内 gRPC 回环，挂真实 task_service TagConfigServiceServicer
   （GetTagsByCategory 走真实 query handler → 隔离库）；
4. report_service 的 _grpc_get_tags_by_category 保持真实实现（不替换），
   经真实 gRPC 客户端 → 回环 servicer → 隔离库，字符串 tag 按名解析分类；
5. 报告主生成链（_prepare_report_data → _build_task_summary → 落库
   report_summary_meta）生成一份新报告，读回 all_case_tags 断言含
   category_id/category_name；解析不到的字符串 tag 不丢、分类 null。

跑完停掉回环 gRPC server、关 session、删除隔离库文件与缓存。
"""
import json
import os
import sys
import traceback

# ---- 环境前置（shared config 类属性 import 即冻结）----
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRATCH = os.path.join(BASE, 'scratch_int2100')
os.makedirs(SCRATCH, exist_ok=True)

# 隔离库：docker postgres（真实 PG schema，BigInteger 自增正常；sqlite 的
# BigInteger PK 不自增会 NOT NULL constraint failed，见 report_summaries.id）。
# 若 INT2100_VERIFY_DB_URL 未提供则默认本地映射 15432。
DB_NAME = 'int2100_verify'
_DB_URL = os.environ.get(
    'INT2100_VERIFY_DB_URL',
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:15432/' + DB_NAME)
_MAINT_URL = _DB_URL.rsplit('/', 1)[0] + '/postgres'

import sqlalchemy  # noqa: E402

def _create_isolated_db():
    """在 docker postgres 上创建隔离库（幂等）。"""
    eng = sqlalchemy.create_engine(
        _MAINT_URL, isolation_level='AUTOCOMMIT')
    with eng.connect() as conn:
        exists = conn.execute(
            sqlalchemy.text(
                "SELECT 1 FROM pg_database WHERE datname = :n"),
            {'n': DB_NAME}).scalar()
        if not exists:
            conn.execute(
                sqlalchemy.text('CREATE DATABASE ' + DB_NAME))
    eng.dispose()

_create_isolated_db()

os.environ['DATABASE_URL'] = _DB_URL
os.environ['OSS_ACCESS_KEY'] = 'test'
os.environ['OSS_SECRET_KEY'] = 'test'
# report_service 的 task 通道 → 本进程回环 gRPC（真实 TagConfigService servicer）
os.environ['TASK_SERVICE_HOST'] = '127.0.0.1'
os.environ['TASK_SERVICE_GRPC_PORT'] = '54210'

if BASE not in sys.path:
    sys.path.insert(0, BASE)

from shared.models.database import (  # noqa: E402
    Base, init_db, get_engine, get_db_session, remove_db_session,
)


def _main():
    init_db(pool_size=2)
    import scripts.create_all_tables as cat
    cat._import_all_models()
    Base.metadata.create_all(bind=get_engine())

    # ---- 种子：分类 / 标签 / 字符串 tags 用例 ----
    from task_service.infrastructure.persistence.models import (  # noqa: F401
        Tag, TagCategory, TestCase, TestCaseGroup,
    )
    session = get_db_session()
    try:
        session.add(TagCategory(id=1, name='标签分类X'))
        session.add(Tag(id=1, name='冒烟', category_id=1))
        session.add(Tag(id=2, name='回归', category_id=1))
        session.add(Tag(id=3, name='未分类标签', category_id=None))
        session.add(TestCaseGroup(id='g1', name='分组1'))
        session.commit()
    finally:
        remove_db_session()

    # ---- 进程内 gRPC 回环：真实 TagConfigService servicer ----
    import grpc
    from concurrent import futures
    from shared.proto import task_service_pb2_grpc
    from task_service.interfaces.grpc.tag_config import TagConfigServiceServicer

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    task_service_pb2_grpc.add_TagConfigServiceServicer_to_server(
        TagConfigServiceServicer(), server)
    bound = server.add_insecure_port('127.0.0.1:54210')
    assert bound == 54210, f'loopback bind failed: {bound}'
    server.start()

    try:
        # ---- 报告生成链：真实 extract + 真实 GetTagsByCategory（回环）----
        import report_service.application.services.report_task_generator as gen_mod
        import report_service.application.services.report_utils as utils_mod

        captured = {}
        results = [{'id': 101, 'test_case_id': 'TC-1',
                    'execution_status': 'completed'}]

        def _dim_batch(ids, **_):
            dim_map = {rid: [{'dimension_id': 1, 'dimension_value': 80.0,
                              'evaluation_status': 'completed'}]
                       for rid in ids}
            return dim_map, [{'id': 1, 'name': '准确率'}]

        builder_stubs = {
            '_get_source_task_ids': lambda t: [],
            '_get_dimension_results_batch': staticmethod(_dim_batch),
            '_calculate_summary_dimensions': lambda stats: [],
            '_get_task_test_cases': lambda ids: (
                [{'id': 'TC-1', 'name': '字符串标签用例', 'config': {},
                  'group': {'id': 'g1', 'name': '分组1'},
                  'tags': ['冒烟', '回归', '未知标签']}],
                ['TC-1']),
            '_get_task_resources': lambda ids: (['dev'], [], [1], []),
            '_get_resource_result_types_batch': lambda *a, **k: ({}, {}),
            '_build_resources_list': lambda *a, **k: ['dev-1'],
            '_build_all_metrics': lambda dims: [{'id': 1, 'name': '准确率'}],
            '_build_case_data': lambda *a, **k: [],
        }
        gen_stubs = {
            '_collect_field_mappings_snapshot': lambda *a, **k: {},
        }
        utils_stubs = {
            'calculate_core_metrics': lambda **k: (
                captured.__setitem__('core_results', k['results']),
                {'metric_data': [], 'tag_metric_data': [], 'raw_data': [],
                 'case_type_stats': [], 'resources': []})[1],
            'build_resource_headers': lambda **k: [],
            'calculate_device_api_stats': lambda **k: ([], []),
        }

        originals_builder = {k: getattr(gen_mod.ReportDataBuilder, k)
                             for k in builder_stubs}
        originals_gen = {k: getattr(gen_mod.ReportTaskGenerator, k)
                         for k in gen_stubs}
        originals_utils = {k: getattr(utils_mod.ReportUtils, k)
                           for k in utils_stubs}
        originals_mod = {
            '_grpc_list_dimensions_all': getattr(gen_mod, '_grpc_list_dimensions_all'),
            '_grpc_get_devices_by_ids': getattr(gen_mod, '_grpc_get_devices_by_ids'),
            '_grpc_get_apis_by_ids': getattr(gen_mod, '_grpc_get_apis_by_ids'),
        }

        task = {'id': 1, 'name': 'INT2100验收任务', 'status': 'completed',
                'total_cases': 1, 'completed_cases': 1, 'failed_cases': 0}

        try:
            for name, fn in builder_stubs.items():
                setattr(gen_mod.ReportDataBuilder, name, fn)
            for name, fn in gen_stubs.items():
                setattr(gen_mod.ReportTaskGenerator, name, staticmethod(fn))
            for name, fn in {
                '_grpc_list_dimensions_all': lambda: [{'id': 1, 'name': '准确率'}],
                '_grpc_get_devices_by_ids': lambda ids: {},
                '_grpc_get_apis_by_ids': lambda ids: {},
            }.items():
                setattr(gen_mod, name, fn)
            for name, fn in utils_stubs.items():
                setattr(utils_mod.ReportUtils, name, staticmethod(fn))
            # 注意：此处不替换 _grpc_get_tags_by_category —— 字符串 tag 按名解析
            # 走真实 gRPC 客户端 → 回环 servicer → 隔离库（种子带分类）。

            data = gen_mod.ReportTaskGenerator._prepare_report_data(task, 1, results)
            assert data is not None, '_prepare_report_data returned None'

            print('=== data.case_tags_list (字符串 tag 按名解析，真实 GetTagsByCategory 回环) ===')
            print(json.dumps(data['case_tags_list'], ensure_ascii=False, indent=2))

            # 断言：冒烟/回归按名命中分类；未知标签不丢、分类 null
            tag_list = data['case_tags_list']
            by_name = {t['name']: t for t in tag_list}
            assert by_name['冒烟']['category_id'] == 1, \
                f"冒烟 category_id={by_name['冒烟']['category_id']}"
            assert by_name['冒烟']['category_name'] == '标签分类X', \
                f"冒烟 category_name={by_name['冒烟']['category_name']}"
            assert by_name['回归']['category_id'] == 1
            assert by_name['回归']['category_name'] == '标签分类X'
            assert by_name['未知标签']['id'] is None, \
                f"未知标签不应解析出 id: {by_name['未知标签']}"
            assert by_name['未知标签']['category_id'] is None
            assert by_name['未知标签']['category_name'] is None
            # 分组快照不受影响
            assert data['case_categories_list'] == [{'id': 'g1', 'name': '分组1'}]

            # ---- 生成一份新报告：summary → 落库 report_summary_meta ----
            summary = gen_mod.ReportTaskGenerator._build_task_summary(
                task, 1, results, data)
            assert summary['all_case_tags'] == data['case_tags_list']
            print('=== summary.all_case_tags ===')
            print(json.dumps(summary['all_case_tags'], ensure_ascii=False, indent=2))

            new_report_id = gen_mod.ReportDataBuilder._create_report_record(
                'INT2100验收报告', 1, '')
            gen_mod.ReportDataBuilder._create_report_summary(new_report_id, task, summary)
            gen_mod.ReportDataBuilder._create_report_detail_data(new_report_id, summary)

            # ---- 读回快照：load_full_report_data 的 all_case_tags ----
            from report_service.infrastructure.persistence.report_repository import report_repository
            full = report_repository.load_full_report_data(new_report_id)
            assert full is not None, 'load_full_report_data returned None'
            print('=== 落库后读回 full.all_case_tags（report_summary_meta）===')
            print(json.dumps(full['all_case_tags'], ensure_ascii=False, indent=2))
            back_tags = {t['name']: t for t in full['all_case_tags']}
            assert back_tags['冒烟']['category_id'] == 1
            assert back_tags['冒烟']['category_name'] == '标签分类X'
            assert back_tags['回归']['category_id'] == 1
            assert back_tags['未知标签']['id'] is None
            assert back_tags['未知标签']['category_id'] is None
            assert back_tags['未知标签']['category_name'] is None

            print('\nRESULT: PASS —— 新报告快照 all_case_tags 条目含 category_id/category_name')
            print(f'new_report_id={new_report_id}')
        finally:
            for name, fn in originals_builder.items():
                setattr(gen_mod.ReportDataBuilder, name, fn)
            for name, fn in originals_gen.items():
                setattr(gen_mod.ReportTaskGenerator, name, fn)
            for name, fn in originals_utils.items():
                setattr(utils_mod.ReportUtils, name, fn)
            for name, fn in originals_mod.items():
                setattr(gen_mod, name, fn)
    finally:
        server.stop(0)


if __name__ == '__main__':
    try:
        _main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    finally:
        remove_db_session()
        # 删除隔离库（先断开：process 已退出时引擎连接自动释放）
        try:
            eng = sqlalchemy.create_engine(
                _MAINT_URL, isolation_level='AUTOCOMMIT')
            with eng.connect() as conn:
                conn.execute(
                    sqlalchemy.text('DROP DATABASE IF EXISTS ' + DB_NAME))
            eng.dispose()
        except Exception as _drop_err:
            print('WARN: drop isolated db failed:', _drop_err)
