# -*- coding: utf-8 -*-
"""INT-274 审计 P2 修复回归：导出条件（format/log_ids/level/module）必须真正到达后端。

审计发现：导出弹窗的 format/范围选择被后端静默忽略——前端走 GET 空 body，
后端 LogExportRequest.model_validate(request.get_json() or {}) 落默认
format='excel'、log_ids=None，弹窗默认「.json / 选中数据」与实际产出
（.xlsx / 全量）不符，对用户撒谎。

修复口径（doc/接口文档 6. 导出日志本就声明 POST body 契约）：
- 前端导出改 POST 携带 body（format/log_ids 经 body 到达）；
- 后端 LogExportRequest 增加 level/module，export_logs 从 body 或 query
  （GET 兼容）均可读取，body 优先。

INT-1812 更新：导出改为「与全局列表同源同筛选」后，带 log_ids 仍走
`get_logs_for_export`（legacy id 反查），不带的筛选式导出改走与列表相同的
`list_logs`（level 大小写不敏感、默认 30 天窗口、扫描上界一致）。本文件
保留原回归意图——body/query 的 format 与 level/module 必须真正到达后端。
"""
import os
from types import SimpleNamespace

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402

from api_gateway.application.services.log.log_query_service import LogQueryService
from api_gateway.infrastructure.request_adapter import set_current_request


@pytest.fixture()
def export_env(tmp_path, monkeypatch):
    """fake gRPC 代理 + 导出目录重定向到临时目录。"""
    calls = {}
    db_rows = [
        {'id': 1, 'time': '2026-10-01T10:00:00', 'level': 'ERROR',
         'module': 'exec', 'content': 'boom', 'mark': ''},
        {'id': 2, 'time': '2026-10-01T10:00:01', 'level': 'INFO',
         'module': 'gw', 'content': 'ok', 'mark': ''},
    ]

    class _FakeProxy:
        def get_logs_for_export(self, log_ids=None, level=None, module=None,
                                reraise=False):
            calls['args'] = (log_ids, level, module)
            calls['reraise'] = reraise
            return {'items': list(db_rows)}

        def list_logs(self, **kwargs):
            calls['list'] = kwargs
            return {'items': list(db_rows), 'total': len(db_rows)}

    monkeypatch.setattr('api_gateway.infrastructure.grpc_proxies.task_data_service',
                        _FakeProxy())
    # 导出文件落 pytest 临时目录，不污染仓库 exports/
    monkeypatch.setattr('os.getcwd', lambda: str(tmp_path))

    yield SimpleNamespace(calls=calls, tmp_path=tmp_path)

    set_current_request(None)


def _invoke_export(body=None, query=None):
    """body: 请求体 dict 或 None；query: query 参数字典（GET 兼容场景）。"""
    set_current_request(SimpleNamespace(
        state=SimpleNamespace(_json_body=body),
        query_params=query or {},
        method='POST',
    ))
    try:
        return LogQueryService.export_logs()
    finally:
        set_current_request(None)


class TestExportLogsContract:
    """POST body 的 format/log_ids 与 level/module 到达 gRPC 代理，format 决定产物。"""

    def test_post_body_format_and_log_ids_reach_backend(self, export_env):
        """弹窗「选中数据 + .json」：log_ids 数组 + format 均到后端，产物为 .json。"""
        _invoke_export({'log_ids': [1, 2], 'format': 'json',
                        'level': 'error', 'module': 'exec'})

        # gRPC 代理收到完整导出条件（修复前 log_ids=None / level/module 只认 query）
        assert export_env.calls['args'] == ([1, 2], 'error', 'exec')
        # format 生效：生成 .json 文件（修复前 GET 空 body 恒为 .xlsx）
        json_files = list(export_env.tmp_path.glob('exports/*.json'))
        assert len(json_files) == 1
        assert json_files[0].suffix == '.json'

    def test_post_body_format_csv(self, export_env):
        _invoke_export({'format': 'csv'})
        csv_files = list(export_env.tmp_path.glob('exports/*.csv'))
        assert len(csv_files) == 1
        assert csv_files[0].suffix == '.csv'

    def test_format_defaults_excel_without_log_ids(self, export_env):
        """范围=全部、未选格式：不携带 log_ids，format 落后端默认 excel。"""
        _invoke_export({})
        # INT-1812：筛选式导出与列表同源，条件走 list_logs（此处两端皆空）
        assert export_env.calls['list']['level'] is None
        assert export_env.calls['list']['module'] is None
        xlsx_files = list(export_env.tmp_path.glob('exports/*.xlsx'))
        assert len(xlsx_files) == 1

    def test_get_query_level_module_fallback(self, export_env):
        """GET 兼容：body 为空时 level/module 从 query 读取。"""
        _invoke_export(None, query={'level': 'warning', 'module': 'gw'})
        assert export_env.calls['list']['level'] == 'warning'
        assert export_env.calls['list']['module'] == 'gw'

    def test_body_level_module_overrides_query(self, export_env):
        """body 优先于 query：两端同传时 body 的 level/module 生效。"""
        _invoke_export({'level': 'error', 'module': 'exec'},
                       query={'level': 'warning', 'module': 'gw'})
        assert export_env.calls['list']['level'] == 'error'
        assert export_env.calls['list']['module'] == 'exec'
