# -*- coding: utf-8 -*-
"""INT-2323：用例导出 `include_deleted` 恢复契约（§3.7.5「回收站用例不导出」）。

INT-2322 审计发现：INT-2313 的批量详情 RPC 把请求里的 `include_deleted` 原样
下传，带 `include_deleted: true` 时软删用例会被导出。本卡恢复契约，两处恒不生效：

1. 网关导出链路不再把该字段下传（服务端收不到 `True`）；
2. task_service 批量详情（详情取数通道）恒按 `deleted=False` 取数，软删 id 落
   `missing[].reason=not_found`——与 INT-2312 及以前逐条 `GetTestCaseDetail` 一致。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.application.services.testcase import (
    testcase_export_service as module,
)
from api_gateway.application.services.testcase.testcase_export_service import (
    MISSING_REASON_NOT_FOUND,
    ExportSpec,
    TestCaseExportService,
)
from api_gateway.domain.dto import CommandResultDTO

DELETED_ID = 'del-1'
LIVE_ID = 'live-1'


def _case_row(case_id):
    """详情行的最小可用形状（与 `_build_detail_data` 的键一致）。"""
    return {
        'id': case_id,
        'name': f'用例{case_id}',
        'description': None,
        'group_id': None,
        'group_name': None,
        'tags': [],
        'config': {},
        'algorithm_params': None,
        'reference_params': None,
        'algorithm_type': None,
        'strategy_id': None,
        'strategy_overrides': None,
        'audios': [],
        'dimensions': [],
        'created_at': None,
        'updated_at': None,
    }


class _FakeTestCaseAcl:
    """只有收到 include_deleted=True 才会把软删行漏出来（模拟旧缺陷行为）。"""

    def __init__(self):
        self.calls = []

    def get_testcases_by_ids(self, ids, include_deleted=False):
        self.calls.append((list(ids), include_deleted))
        returned = {LIVE_ID, DELETED_ID} if include_deleted else {LIVE_ID}
        cases = [_case_row(i) for i in ids if i in returned]
        missing = [i for i in ids if i not in returned]
        return CommandResultDTO(
            success=True, data={'test_cases': cases, 'missing_ids': missing})


def _spec(ids, **kwargs):
    return ExportSpec(ids=list(ids), format=kwargs.pop('format', 'json'), **kwargs)


def _patch_export_side_lookups(monkeypatch, acl):
    monkeypatch.setattr(module, '_testcase_acl', acl)
    # 设备名与评估维度与口径无关，替身掉避免触发额外 gRPC
    monkeypatch.setattr(
        TestCaseExportService, '_load_playback_device_names', staticmethod(lambda: {}))
    monkeypatch.setattr(
        TestCaseExportService, '_fetch_dimension_map', staticmethod(lambda dim_ids: {}))


# ----------------------------------------------------------------------
# 1. 网关：导出请求带 include_deleted=true 也不下传、软删用例落 missing
# ----------------------------------------------------------------------
def test_export_does_not_pass_include_deleted_and_deleted_goes_missing(monkeypatch):
    acl = _FakeTestCaseAcl()
    _patch_export_side_lookups(monkeypatch, acl)

    export_data, missing = TestCaseExportService._fetch_export_data(
        _spec([LIVE_ID, DELETED_ID], include_deleted=True))

    assert [row['id'] for row in export_data] == [LIVE_ID], '回收站用例不得导出'
    assert missing == [{'id': DELETED_ID, 'reason': MISSING_REASON_NOT_FOUND}]
    assert acl.calls == [([LIVE_ID, DELETED_ID], False)], \
        '导出链路不得把 include_deleted 下传给批量详情 RPC'


def test_export_sync_json_path_filters_deleted(monkeypatch):
    """同步 JSON 入口（`_fetch_testcases_by_ids`）同口径。"""
    acl = _FakeTestCaseAcl()
    _patch_export_side_lookups(monkeypatch, acl)

    test_cases = TestCaseExportService._fetch_testcases_by_ids([LIVE_ID, DELETED_ID])

    assert [tc['id'] for tc in test_cases] == [LIVE_ID]
    assert acl.calls == [([LIVE_ID, DELETED_ID], False)]


def test_request_field_still_accepted_for_echo():
    """`include_deleted` 仍被接收（回显进作业记录），但只是回显、不是控制开关。"""
    spec, err = TestCaseExportService.parse_request(
        {'ids': [LIVE_ID], 'format': 'json', 'include_deleted': True})
    assert err is None
    assert spec.include_deleted is True
    # 作业记录回显：`ExportSpec.to_dict` 保留该键（老作业记录仍可反序列化）
    assert spec.to_dict()['include_deleted'] is True


# ----------------------------------------------------------------------
# 2. task_service：批量详情是详情通道，接收但无效——恒不下传 include_deleted
# ----------------------------------------------------------------------
class _FakeQueryRepo:
    """只有被下传 include_deleted=True 时才会漏出软删行。"""

    def __init__(self):
        self.calls = []

    def list_testcases_by_ids_visible(self, ids, include_deleted=False):
        self.calls.append((list(ids), include_deleted))
        # 服务端契约：软删行取不到
        return []


def test_batch_detail_server_ignores_include_deleted():
    from task_service.application.testcase.testcase_query_service import (
        TestCaseQueryService,
    )

    repo = _FakeQueryRepo()
    result = TestCaseQueryService(repo).get_testcase_details_by_ids(
        [DELETED_ID], include_deleted=True)

    assert result['success'] is True
    assert result['data']['test_cases'] == []
    assert result['data']['missing_ids'] == [DELETED_ID]
    assert repo.calls == [([DELETED_ID], False)], \
        '详情通道恒按 deleted=False 取数，include_deleted 不得下传'
