# -*- coding: utf-8 -*-
"""INT-79 二轮修复回归：报告音频口径改配置形态派生 + GetTaskStatus 响应去残留键。

缺陷4：report_helpers._build_audios_list 原读 test_case['test_type']——差异#2
收尾后数据源（ListTestCases items / 用例详情 / BuildReferenceParams 的
SimpleNamespace）均不再携带该键，表达式恒落 'api'，e2e 用例报告音频误标。
修复后改 derive_case_test_type(config, name) 派生，task / compare /
SimpleNamespace 三调用路径同源；传用例名兼容 INT-129 上传双变体
（两变体配置形态相同，靠 _api/_e2e 后缀区分）。

缺陷5：task_service GetTaskStatus 死端点响应残留 "type"（Task.type 列已删
恒 null）与 "error_message": None（Task 无该列的恒定占位）。
"""
import json
import os
import tempfile
from types import SimpleNamespace

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int79_audios_') + '/audios.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.database import (
    Base, get_db_session, get_engine, init_db, remove_db_session,
)
from task_service.infrastructure.persistence.models import Task
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

import report_service.application.services.report_helpers as rh
from report_service.application.services.report_helpers import ReportHelpers


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    return 'INTEGER'


_E2E_ROUND = {
    'roundNumber': 1,
    'audios': [{'audio_id': 11, 'playback_device_id': 7, 'spl': 70, 'play_order': 1}],
}
_API_ROUND = {
    'roundNumber': 1,
    'audios': [{'audio_id': 11, 'spl': 70, 'play_order': 1}],
}


def _case(config, name='回归用例'):
    return {'id': 'tc-1', 'name': name, 'config': config}


@pytest.fixture(autouse=True)
def _stub_grpc_clients(monkeypatch):
    """音频/设备 gRPC 查询打桩：音频恒命中，设备名映射固定。"""
    monkeypatch.setattr(rh, '_grpc_get_audio',
                        lambda audio_id: {'id': audio_id, 'name': f'audio-{audio_id}',
                                          'original_filename': f'a{audio_id}.wav', 'duration': 3.0})
    monkeypatch.setattr(rh, '_grpc_get_playback_devices_by_ids',
                        lambda ids: {i: {'name': f'pb-{i}'} for i in ids})
    monkeypatch.setattr(rh, '_grpc_get_devices_by_ids',
                        lambda ids: {i: {'name': f'dev-{i}'} for i in ids})


def _type_keys(audios_list, key):
    return [item[key] for item in audios_list]


def test_task_mode_e2e_shape_derives_e2e():
    """task 模式：rounds 音频带 playback_device_id（物理执行形态）→ testType='e2e'。

    缺陷4 主场景：修复前该表达式读不存在的 test_type 键恒落 'api'。
    """
    audios = ReportHelpers._build_audios_list(_case({'rounds': [_E2E_ROUND]}), mode='task')
    assert audios, 'e2e 形态应产出音频项'
    assert _type_keys(audios, 'testType') == ['e2e']


def test_task_mode_api_shape_derives_api():
    """task 模式：无播放设备的纯 API 形态 → testType='api'。"""
    audios = ReportHelpers._build_audios_list(_case({'rounds': [_API_ROUND]}), mode='task')
    assert audios
    assert _type_keys(audios, 'testType') == ['api']


def test_compare_mode_audio_type_key_derived():
    """compare 模式：同源派生写入 audio_type 键。

    注：compare 模式 audios_list 存在存量重复 append（round_dry 项在
    165 行无条件 append 后又于 190 行 extend，先于本卡存在），非本卡
    范畴，故此处按集合口径断言派生值。
    """
    audios = ReportHelpers._build_audios_list(_case({'rounds': [_E2E_ROUND]}), mode='compare')
    assert audios
    assert set(_type_keys(audios, 'audio_type')) == {'e2e'}


def test_dual_variant_name_suffix_wins_over_config_shape():
    """上传双变体（INT-129）：两变体配置形态相同，_api/_e2e 后缀区分口径。"""
    config = {'auto_generated': True, 'rounds': [_E2E_ROUND]}
    api_variant = ReportHelpers._build_audios_list(
        _case(config, name='测试用例_素材_api_023604'), mode='task')
    e2e_variant = ReportHelpers._build_audios_list(
        _case(config, name='测试用例_素材_e2e_023604'), mode='task')
    assert _type_keys(api_variant, 'testType') == ['api']
    assert _type_keys(e2e_variant, 'testType') == ['e2e']


def test_simplenamespace_path_no_test_type_attribute():
    """BuildReferenceParams 路径：SimpleNamespace 无 test_type 属性不再 AttributeError。

    修复前 test_case.test_type 触发 AttributeError → 网关任务结果详情页
    增强被 try/except 吞成 warning 静默失败。
    """
    case = SimpleNamespace(id='tc-1', name='测试用例_素材_e2e_023604',
                           config={'auto_generated': True, 'rounds': [_E2E_ROUND]})
    audios = ReportHelpers._build_audios_list(case, mode='task')
    assert audios
    assert _type_keys(audios, 'testType') == ['e2e']


def test_simplenamespace_without_name_falls_back_to_config_shape():
    """SimpleNamespace 无 name 属性时回落配置形态口径（getattr 默认 None）。"""
    case = SimpleNamespace(id='tc-1', config={'rounds': [_E2E_ROUND]})
    audios = ReportHelpers._build_audios_list(case, mode='task')
    assert _type_keys(audios, 'testType') == ['e2e']


@pytest.fixture(scope='module')
def db():
    """初始化共享 sqlite 并种子一条任务，供 GetTaskStatus 查询。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), \
        f'audios sqlite 需要文件型 sqlite，实际绑定 {engine.url}'
    remove_db_session()
    Base.metadata.create_all(bind=engine, tables=[Task.__table__])
    session = get_db_session()
    task = Task(name='int79-status', status='running', total_cases=2,
                completed_cases=1, failed_cases=0)
    session.add(task)
    session.commit()
    task_id = task.id
    session.close()
    yield task_id
    remove_db_session()


def test_get_task_status_response_has_no_residual_keys(db):
    """缺陷5：GetTaskStatus 响应不再含 'type' / 'error_message' 残留键。"""
    from types import SimpleNamespace as _NS
    from task_service.interfaces.grpc.execution import ExecutionServiceServicer

    servicer = ExecutionServiceServicer()
    resp = servicer.GetTaskStatus(_NS(task_id=db))
    assert resp.success
    data = json.loads(resp.data) if resp.data else {}
    assert data.get('status') == 'running'
    assert 'type' not in data, f'GetTaskStatus 响应残留 type 键: {sorted(data)}'
    assert 'error_message' not in data, f'GetTaskStatus 响应残留 error_message 键: {sorted(data)}'
