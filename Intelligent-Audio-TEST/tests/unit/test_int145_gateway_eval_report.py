# -*- coding: utf-8 -*-
"""INT-145 缺陷包 4/5/6 网关段：维度导入导出父子语义 / 报告重新生成元数据 /
重新评估返回计数。

- 缺陷4：Excel/JSON 导出补「维度类型/所属主维度」两列；导入支持父子列
  （父维度ID/所属主维度/维度类型），子维度挂父维度并继承任务关键字。
- 缺陷5：POST /reports/{id}/regenerate 修复前不校验"仅任务报告"、先删再
  生成、name/description 传空——原名称/描述丢失。修复后校验类型 + 捕获
  原名称/描述 + 软删除旧报告（保留历史快照）+ 携带元数据重新生成。
- 缺陷6：task/reevaluate 返回 queued 恒 0 → 取任务详情实际用例数（展示口径）。
"""
import io
import json
import os
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pandas as pd
import pytest

import api_gateway.application.services.evaluation.evaluation_command_service as eval_cmd_mod
import api_gateway.application.services.report.report_command_sevice as report_cmd_mod
from api_gateway.infrastructure.request_adapter import set_current_request


class _StubAcl:
    """替代 EvaluationConfigAclRepositoryImpl 的桩（有状态：create 落入列表）。"""

    def __init__(self, dimensions=None):
        self._next_id = 900
        self.dimensions = list(dimensions or [])
        self.created = []
        self.updated = []

    def list_dimensions(self, **kwargs):
        search = kwargs.get('search') or ''
        items = [d for d in self.dimensions
                 if not search or d.get('name') == search]
        return {'success': True, 'message': '',
                'data': {'items': items, 'total': len(items),
                         'page': kwargs.get('page', 1),
                         'per_page': kwargs.get('per_page', 10)}}

    def get_dimension(self, dim_id):
        for d in self.dimensions:
            if d.get('id') == dim_id:
                return {'success': True, 'message': '', 'data': d}
        return {'success': False, 'message': '未找到评估维度', 'code': 404}

    def create_dimension(self, data):
        self._next_id += 1
        self.created.append(data)
        self.dimensions.append({'id': self._next_id, **data})
        return {'success': True, 'message': '评分维度创建成功',
                'data': {'id': self._next_id}}

    def update_dimension(self, dim_id, data):
        self.updated.append((dim_id, data))
        return {'success': True, 'message': '评分维度更新成功'}

    def batch_action(self, data):
        return {'success': True, 'message': '批量操作执行成功'}


class _StubReevaluationAcl:
    def __init__(self, success=True):
        self.success = success
        self.calls = []

    def submit(self, task_id, reextract_device_output=True, reevaluate_type='all', options=None):
        self.calls.append({'task_id': task_id,
                           'reextract_device_output': reextract_device_output,
                           'reevaluate_type': reevaluate_type,
                           'options': options})
        return SimpleNamespace(success=self.success, message='已提交重新评估',
                               result_data={})


def _fake_request(json_body=None, query=None, files=None, form=None):
    """构造 request_adapter 所需的最小请求替身。"""
    state = SimpleNamespace(_json_body=json_body, _files=files or {},
                            _form_data=form or {})
    return SimpleNamespace(state=state, query_params=query or {})


# ==================== 缺陷4：导出列 ====================

# openpyxl 未安装时跳过 Excel 读写用例（列逻辑由 JSON 导出用例覆盖，分支共用）
try:
    import openpyxl  # noqa: F401
    _HAS_OPENPYXL = True
except ModuleNotFoundError:
    _HAS_OPENPYXL = False

_requires_openpyxl = pytest.mark.skipif(
    not _HAS_OPENPYXL, reason='openpyxl 未安装，Excel 读写用例跳过')

# 共享维度夹具数据：主维度1 + 子维度1（parent=1）
_EXPORT_DIMS = [
    {'id': 1, 'name': '主维度A', 'description': '', 'dimension_type': 'main',
     'parent_dimension_id': None, 'category_id': 1, 'type': 'auto',
     'api_url': '', 'result_type': 1, 'weight': 5, 'score_unit': '',
     'rule': {}, 'api_settings': {}, 'status': True},
    {'id': 2, 'name': '子维度A1', 'description': '', 'dimension_type': 'sub',
     'parent_dimension_id': 1, 'category_id': 1, 'type': 'auto',
     'api_url': '', 'result_type': 1, 'weight': 5, 'score_unit': '',
     'rule': {}, 'api_settings': {}, 'status': True},
]


class TestExportParentChildColumns:
    def test_json_export_has_parent_columns(self, monkeypatch):
        stub = _StubAcl(dimensions=list(_EXPORT_DIMS))
        monkeypatch.setattr(eval_cmd_mod, '_evaluation_acl', stub)
        set_current_request(_fake_request(query={}))

        try:
            result, http_code = eval_cmd_mod.EvaluationCommandService.export_to_file()
        finally:
            set_current_request(None)

        assert http_code == 200
        rows = result['data']
        main_row = next(r for r in rows if r['name'] == '主维度A')
        sub_row = next(r for r in rows if r['name'] == '子维度A1')
        assert main_row['dimension_type'] == 'main'
        assert main_row['parent_name'] == ''
        assert sub_row['dimension_type'] == 'sub'
        assert sub_row['parent_name'] == '主维度A'

    @_requires_openpyxl
    def test_excel_export_has_parent_columns(self, monkeypatch):
        stub = _StubAcl(dimensions=[
            {'id': 1, 'name': '主维度B', 'description': '', 'dimension_type': 'main',
             'parent_dimension_id': None, 'category_id': 1, 'type': 'auto',
             'api_url': '', 'result_type': 1, 'weight': 5, 'score_unit': '',
             'rule': {}, 'api_settings': {}, 'status': True},
            {'id': 2, 'name': '子维度B1', 'description': '', 'dimension_type': 'sub',
             'parent_dimension_id': 1, 'category_id': 1, 'type': 'auto',
             'api_url': '', 'result_type': 1, 'weight': 5, 'score_unit': '',
             'rule': {}, 'api_settings': {}, 'status': True},
        ])
        monkeypatch.setattr(eval_cmd_mod, '_evaluation_acl', stub)
        set_current_request(_fake_request(query={'format': 'excel'}))

        try:
            response = eval_cmd_mod.EvaluationCommandService.export_to_file()
        finally:
            set_current_request(None)

        # excel 分支返回内存字节流 Response：解析表头校验两列
        assert 'spreadsheetml' in response.media_type
        df = pd.read_excel(io.BytesIO(response.body), engine='openpyxl')
        assert '维度类型' in df.columns
        assert '所属主维度' in df.columns
        sub_idx = df.index[df['名称'] == '子维度B1'][0]
        assert df.loc[sub_idx, '维度类型'] == '子'
        assert df.loc[sub_idx, '所属主维度'] == '主维度B'

    def test_export_fetches_full_list(self, monkeypatch):
        """导出请求放大 per_page 取全量（分页默认值会截断）。"""
        stub = _StubAcl(dimensions=[])
        captured = {}
        original_list = stub.list_dimensions

        def _spy(**kwargs):
            captured.update(kwargs)
            return original_list(**kwargs)

        stub.list_dimensions = _spy
        monkeypatch.setattr(eval_cmd_mod, '_evaluation_acl', stub)
        set_current_request(_fake_request(query={}))

        try:
            eval_cmd_mod.EvaluationCommandService.export_to_file()
        finally:
            set_current_request(None)

        assert captured.get('per_page', 0) >= 1000


# ==================== 缺陷4：导入父子列 ====================

class TestExportRouteOrder:
    """F2 回归守卫：GET 静态路径必须注册在 GET 动态路径之前——FastAPI 按
    注册顺序匹配，/dimensions/export、/reports/export 若落在 /{id} 之后，
    'export' 解析 int 失败恒 422（生产不可达）。"""

    @staticmethod
    def _get_paths(router):
        return [r.path for r in router.routes
                if 'GET' in (getattr(r, 'methods', None) or set())]

    def test_evaluation_export_before_dynamic_get(self):
        from api_gateway.routes import evaluation_bp

        paths = self._get_paths(evaluation_bp.router)
        assert paths.index('/dimensions/export') < paths.index('/dimensions/{dim_id}')

    def test_report_export_before_dynamic_get(self):
        from api_gateway.routes import report_bp

        paths = self._get_paths(report_bp.router)
        assert paths.index('/export') < paths.index('/{report_id}')


class TestImportParentChild:
    def _xlsx(self, rows, columns):
        df = pd.DataFrame(rows, columns=columns)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='评估维度')
        buf.seek(0)
        return buf

    @_requires_openpyxl
    def test_import_sub_dimension_resolves_parent(self, monkeypatch):
        columns = ['名称', '描述', '维度类型', '所属主维度', '分类ID', '类型',
                   'Master入口URL', '结果类型', '权重', '分数单位', '规则', 'API配置', '状态']
        rows = [
            ['主维度C', '主描述', '主', '', 1, 'auto', 'http://m', 1, 5, '分',
             '{}', '{}', '启用'],
            ['子维度C1', '子描述', '子', '主维度C', 1, 'auto', '', 1, 5, '分',
             '{}', '{}', '启用'],
        ]
        upload = SimpleNamespace(filename='dims.xlsx',
                                 file=self._xlsx(rows, columns))
        monkeypatch.setattr(eval_cmd_mod, '_evaluation_acl',
                            _StubAcl(dimensions=[]))
        set_current_request(_fake_request(
            files={'file': upload}, form={'update_existing': 'false'}))

        try:
            result, http_code = eval_cmd_mod.EvaluationCommandService.import_from_file()
        finally:
            set_current_request(None)

        assert http_code == 200
        stub = eval_cmd_mod._evaluation_acl
        assert len(stub.created) == 2
        main_payload = stub.created[0]
        sub_payload = stub.created[1]
        assert main_payload['dimension_type'] == 'main'
        assert 'parent_dimension_id' not in main_payload
        assert sub_payload['dimension_type'] == 'sub'
        assert sub_payload['parent_dimension_id'] == 901  # 主维度C创建后分配的 ID
        assert sub_payload['api_endpoints'] == []
        assert sub_payload['api_settings'] == {}
        # 不指定 sort_order：服务端按父段编码
        assert 'sort_order' not in sub_payload

    @_requires_openpyxl
    def test_import_sub_without_parent_row_falls_back_main(self, monkeypatch):
        """标记为子但解析不到父维度 → 按主维度兜底（对齐旧库语义）。"""
        columns = ['名称', '维度类型', '所属主维度']
        rows = [['孤儿维度', '子', '不存在的父维度']]
        upload = SimpleNamespace(filename='dims.xlsx',
                                 file=self._xlsx(rows, columns))
        monkeypatch.setattr(eval_cmd_mod, '_evaluation_acl',
                            _StubAcl(dimensions=[]))
        set_current_request(_fake_request(
            files={'file': upload}, form={'update_existing': 'false'}))

        try:
            eval_cmd_mod.EvaluationCommandService.import_from_file()
        finally:
            set_current_request(None)

        payload = eval_cmd_mod._evaluation_acl.created[0]
        assert payload['dimension_type'] == 'main'

    @_requires_openpyxl
    def test_import_update_syncs_hierarchy(self, monkeypatch):
        """update_existing：文件带层级列时同步 dimension_type/parent。"""
        columns = ['名称', '维度类型', '所属主维度']
        rows = [['已有维度', '子', '主维度C']]
        upload = SimpleNamespace(filename='dims.xlsx',
                                 file=self._xlsx(rows, columns))
        stub = _StubAcl(dimensions=[
            {'id': 7, 'name': '已有维度', 'dimension_type': 'main',
             'parent_dimension_id': None},
            {'id': 8, 'name': '主维度C', 'dimension_type': 'main',
             'parent_dimension_id': None, 'task_type_code': 'wer'},
        ])
        monkeypatch.setattr(eval_cmd_mod, '_evaluation_acl', stub)
        set_current_request(_fake_request(
            files={'file': upload}, form={'update_existing': 'true'}))

        try:
            eval_cmd_mod.EvaluationCommandService.import_from_file()
        finally:
            set_current_request(None)

        assert stub.updated, 'update_existing 应触发更新'
        dim_id, payload = stub.updated[0]
        assert dim_id == 7
        assert payload['dimension_type'] == 'sub'
        assert payload['parent_dimension_id'] == 8


# ==================== 缺陷5：重新生成报告 ====================

class _ReportStub:
    """report_config_service 桩：记录调用并按脚本返回。"""

    def __init__(self, report):
        self.report = report
        self.calls = []

    @property
    def stub(self):
        return self

    def GetReportDetail(self, req):
        self.calls.append(('GetReportDetail', req.report_id))
        if self.report is None:
            return SimpleNamespace(success=False, message='report not found', data='')
        return SimpleNamespace(success=True, message='ok',
                               data=json.dumps(self.report, ensure_ascii=False))

    def DeleteReport(self, req):
        self.calls.append(('DeleteReport', req.report_id))
        return SimpleNamespace(success=True, message='ok',
                               data=json.dumps({'deleted': True, 'task_id': 5}))

    def GenerateTaskReport(self, req):
        self.calls.append(('GenerateTaskReport', req.task_id, req.name, req.description))
        return SimpleNamespace(success=True, message='报告生成中',
                               data=json.dumps({'taskId': req.task_id,
                                                'status': 'generating'}))


class TestRegenerateReport:
    def test_task_report_regenerates_with_metadata(self, monkeypatch):
        stub = _ReportStub({
            'id': 3, 'task_id': 5, 'report_type': 'task',
            'name': '任务报告_原始', 'description': '原始描述',
        })
        monkeypatch.setattr(report_cmd_mod, 'report_config_service', stub)

        result, http_code = report_cmd_mod.ReportCommandService.regenerate_report(3)

        assert http_code == 200
        kinds = [c[0] for c in stub.calls]
        assert kinds == ['GetReportDetail', 'DeleteReport', 'GenerateTaskReport']
        gen_call = stub.calls[2]
        assert gen_call[1] == 5
        assert gen_call[2] == '任务报告_原始'
        assert gen_call[3] == '原始描述'

    def test_comparison_report_rejected_before_delete(self, monkeypatch):
        """非任务报告：不得触发删除（修复前对比报告也被删了）。"""
        stub = _ReportStub({'id': 4, 'task_id': 0, 'report_type': 'comparison',
                            'name': '对比', 'description': ''})
        monkeypatch.setattr(report_cmd_mod, 'report_config_service', stub)

        result, http_code = report_cmd_mod.ReportCommandService.regenerate_report(4)

        assert http_code != 200
        assert stub.calls == [('GetReportDetail', 4)]

    def test_missing_report_rejected(self, monkeypatch):
        stub = _ReportStub(None)
        monkeypatch.setattr(report_cmd_mod, 'report_config_service', stub)

        result, http_code = report_cmd_mod.ReportCommandService.regenerate_report(9)

        assert http_code == 404
        assert stub.calls == [('GetReportDetail', 9)]


# ==================== 缺陷6：重新评估返回计数 ====================

class TestReevaluateQueuedCount:
    def test_queued_count_from_task_total_cases(self, monkeypatch):
        """返回任务实际用例数（修复前恒 0）。"""
        monkeypatch.setattr(
            eval_cmd_mod, '_task_acl',
            SimpleNamespace(get_task_detail=lambda tid: {
                'success': True, 'message': '', 'data': {
                    'id': tid, 'status': 'completed', 'total_cases': 7}}))
        reeval = _StubReevaluationAcl()
        monkeypatch.setattr(eval_cmd_mod, '_reevaluation_acl', reeval)
        set_current_request(_fake_request(json_body={'task_id': 5}))

        try:
            result, http_code = eval_cmd_mod.EvaluationCommandService.reevaluate_task_results()
        finally:
            set_current_request(None)

        assert http_code == 200
        data = result['data']
        assert data['total_cases'] == 7
        assert data['queued_cases'] == 7
        assert reeval.calls == [{'task_id': 5, 'reextract_device_output': False,
                                 'reevaluate_type': 'all', 'options': None}]

    def test_failed_submit_returns_error(self, monkeypatch):
        monkeypatch.setattr(
            eval_cmd_mod, '_task_acl',
            SimpleNamespace(get_task_detail=lambda tid: {
                'success': True, 'message': '', 'data': {
                    'id': tid, 'status': 'completed', 'total_cases': 7}}))
        monkeypatch.setattr(eval_cmd_mod, '_reevaluation_acl',
                            _StubReevaluationAcl(success=False))
        set_current_request(_fake_request(json_body={'task_id': 5}))

        try:
            result, http_code = eval_cmd_mod.EvaluationCommandService.reevaluate_task_results()
        finally:
            set_current_request(None)

        assert http_code != 200
