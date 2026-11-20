# -*- coding: utf-8 -*-
"""INT-2568 专项：task_service 配置热更新不得把重载失败遮蔽成成功。

背景：``shared.clients.algo_reload_config`` 在 algorithm_service 返回
success=False（含 gRPC 异常）时返回 None；旧实现仍组装
``{"success": true, "data": {"success": true, "reload_time": null}}``，
网关 200 / Agent 工具据此误判成功。本文件锁定修复后的口径：

- 只有上游 success=True 且给出 reload_time 才算成功；
- None / 空 dict / success=False / 缺 reload_time → 外层 success=False，业务码 502；
- 走 gRPC 的 AlgorithmConfigServiceServicer 也按真实结果回 success 字段。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace

from task_service.application.algorithm.algorithm_param_query_service import (
    AlgorithmParamQueryService,
)


def _service(return_value=None, raises=None):
    service = AlgorithmParamQueryService.__new__(AlgorithmParamQueryService)

    def _reload():
        if raises is not None:
            raise raises
        return return_value

    service.repo = SimpleNamespace(algo_reload_config=_reload)
    return service


def test_success_passthrough():
    out = _service({'success': True, 'reload_time': '2026-11-13T20:00:00'}).reload_config()

    assert out['success'] is True
    assert out['data']['success'] is True
    assert out['data']['reload_time'] == '2026-11-13T20:00:00'
    assert 'code' not in out


def test_grpc_failure_returns_none_is_not_success():
    """上游 gRPC 失败时 shared client 返回 None，不能再包装成成功。"""
    out = _service(None).reload_config()

    assert out['success'] is False
    assert out['code'] == 502
    assert out['data'] == {
        'success': False,
        'message': 'Config reloaded: False',
        'reload_time': None,
    }


def test_upstream_success_false_is_failure():
    out = _service({'success': False, 'reload_time': None}).reload_config()

    assert out['success'] is False
    assert out['code'] == 502
    assert out['data']['success'] is False


def test_success_flag_without_reload_time_is_failure():
    """只有 success=True 没有时间戳，说明缓存并未真正重建。"""
    out = _service({'success': True, 'reload_time': None}).reload_config()

    assert out['success'] is False
    assert out['data']['success'] is False
    assert out['code'] == 502


def test_empty_payload_is_failure():
    out = _service({}).reload_config()

    assert out['success'] is False
    assert out['code'] == 502


def test_exception_is_failure():
    out = _service(raises=RuntimeError('boom')).reload_config()

    assert out['success'] is False
    assert out['code'] == 500
    assert 'boom' in out['message']


def test_grpc_servicer_envelope_reflects_failure():
    """gRPC 信封 success 字段跟随真实结果（网关据此判失败）。"""
    from task_service.interfaces.grpc.algorithm_config import (
        AlgorithmConfigServiceServicer,
    )

    servicer = AlgorithmConfigServiceServicer()
    servicer._svc = SimpleNamespace(reload_config=lambda: {
        'success': False,
        'message': '重载失败: 算法服务未返回有效的重载结果',
        'data': {'success': False, 'message': 'Config reloaded: False',
                 'reload_time': None},
        'code': 502,
    })

    resp = servicer.ReloadAlgorithmConfig(None)

    assert resp.success is False
    assert '重载失败' in resp.message
    assert '"success": false' in resp.data


def test_grpc_servicer_envelope_reflects_success():
    from task_service.interfaces.grpc.algorithm_config import (
        AlgorithmConfigServiceServicer,
    )

    servicer = AlgorithmConfigServiceServicer()
    servicer._svc = SimpleNamespace(reload_config=lambda: {
        'success': True,
        'message': 'Config reloaded',
        'data': {'success': True, 'message': 'Config reloaded: True',
                 'reload_time': '2026-11-13T20:00:00'},
    })

    resp = servicer.ReloadAlgorithmConfig(None)

    assert resp.success is True
    assert '"reload_time": "2026-11-13T20:00:00"' in resp.data


# ==================== 网关：失败不得再回 200 success ====================

def test_gateway_maps_reload_failure_to_error_response(monkeypatch):
    from api_gateway.application.services.algorithm import (
        algorithm_command_service as command_service,
    )
    from api_gateway.domain.dto.api_gateway_acl_dto import CommandResultDTO

    monkeypatch.setattr(
        command_service._algorithm_acl, 'reload_config',
        lambda: CommandResultDTO(
            success=False,
            message='重载失败: 算法服务未返回有效的重载结果',
            data=None,
            code=502,
        ),
    )

    body, http_code = command_service.AlgorithmCommandService.reload_config()

    assert body['success'] is False
    assert body['code'] == 502
    assert '重载失败' in body['message']


def test_gateway_passes_through_reload_success(monkeypatch):
    from api_gateway.application.services.algorithm import (
        algorithm_command_service as command_service,
    )
    from api_gateway.domain.dto.api_gateway_acl_dto import CommandResultDTO

    payload = {'success': True, 'message': 'Config reloaded: True',
               'reload_time': '2026-11-13T20:00:00'}
    monkeypatch.setattr(
        command_service._algorithm_acl, 'reload_config',
        lambda: CommandResultDTO(success=True, message='Config reloaded',
                                 data=payload, code=None),
    )

    body, http_code = command_service.AlgorithmCommandService.reload_config()

    assert body['success'] is True
    assert body['data']['reload_time'] == '2026-11-13T20:00:00'
    assert body['data']['success'] is True
