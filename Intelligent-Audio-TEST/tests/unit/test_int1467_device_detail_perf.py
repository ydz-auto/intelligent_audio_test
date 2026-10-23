# -*- coding: utf-8 -*-
"""INT-1467 设备详情读侧性能回归：占用态并发注入 + lab_name 去冗余回源。"""
import threading

import api_gateway.application.services.device.device_query_service as dqs
import api_gateway.application.services.device.lab_name_decorator as lnd


def test_get_one_injects_occupancy_and_detail(monkeypatch):
    """详情：占用态与设备详情并发获取，两条链路结果都进 payload。"""
    seen = {}

    class FakeDeviceAcl:
        def get_one(self, device_id):
            seen['device_id'] = device_id
            seen['main_thread'] = threading.current_thread().name
            return {'success': True, 'message': 'ok', 'code': 200,
                    'data': {'id': device_id, 'name': 'd1', 'lab_id': None}}

    def fake_fetch(device_ids):
        seen['occ_device_ids'] = device_ids
        seen['occ_thread'] = threading.current_thread().name
        return {str(device_ids[0]): {'occupied_status': 'testing', 'task_id': 't-1'}}

    monkeypatch.setattr(dqs, '_device_acl', FakeDeviceAcl())
    monkeypatch.setattr(dqs.DeviceQueryService, '_fetch_occupancy', staticmethod(fake_fetch))
    monkeypatch.setattr(lnd, '_fetch_lab_name_map', lambda ids: {})

    payload, code = dqs.DeviceQueryService.get_one(7)

    assert code == 200
    assert seen['device_id'] == 7
    assert seen['occ_device_ids'] == [7]
    # 占用态查询在独立线程执行（与设备详情并发，不再串行两次跨服务 RPC）
    assert seen['occ_thread'] != seen['main_thread']
    assert payload['data']['occupied_status'] == 'testing'
    assert payload['data']['occupied_task_id'] == 't-1'


def test_get_one_without_occupancy_sets_null_fields(monkeypatch):
    """无占用行：occupied_* 字段仍存在且为 null（口径不变）。"""

    class FakeDeviceAcl:
        def get_one(self, device_id):
            return {'success': True, 'message': 'ok', 'code': 200,
                    'data': {'id': device_id, 'name': 'd1', 'lab_id': None}}

    monkeypatch.setattr(dqs, '_device_acl', FakeDeviceAcl())
    monkeypatch.setattr(dqs.DeviceQueryService, '_fetch_occupancy', staticmethod(lambda ids: {}))
    monkeypatch.setattr(lnd, '_fetch_lab_name_map', lambda ids: {})

    payload, code = dqs.DeviceQueryService.get_one(8)

    assert code == 200
    assert payload['data']['occupied_status'] is None
    assert payload['data']['occupied_task_id'] is None


def test_get_one_not_found_skips_decoration(monkeypatch):
    """设备不存在：404 语义透传，且不发起 lab_name 回源。"""
    lab_calls = []

    class FakeDeviceAcl:
        def get_one(self, device_id):
            return {'success': False, 'message': '未找到设备', 'code': 404}

    monkeypatch.setattr(dqs, '_device_acl', FakeDeviceAcl())
    monkeypatch.setattr(dqs.DeviceQueryService, '_fetch_occupancy', staticmethod(lambda ids: {}))
    monkeypatch.setattr(lnd, '_fetch_lab_name_map', lambda ids: lab_calls.append(ids) or {})

    payload, code = dqs.DeviceQueryService.get_one(404)

    assert code == 404
    assert payload['success'] is False
    assert lab_calls == []


def test_decorate_skips_fetch_when_lab_name_present(monkeypatch):
    """device_service 已返回 lab_name：网关不再发起 ListLaboratories 回源。"""
    called = []
    items = [{'id': 1, 'name': 'd1', 'lab_id': 2, 'lab_name': '音频测试实验室1'}]
    monkeypatch.setattr(lnd, '_fetch_lab_name_map', lambda ids: called.append(ids) or {2: 'X'})

    decorated = lnd._decorate_lab_names(items)

    assert called == []
    assert decorated[0]['lab_name'] == '音频测试实验室1'


def test_decorate_fetches_only_missing_lab_name(monkeypatch):
    """缺 lab_name 的 item 才回源，且不覆盖已有值。"""
    called = []
    items = [
        {'id': 1, 'name': 'd1', 'lab_id': 2, 'lab_name': '已有'},
        {'id': 2, 'name': 'd2', 'lab_id': 3},
    ]
    monkeypatch.setattr(lnd, '_fetch_lab_name_map',
                        lambda ids: called.append(set(ids)) or {2: '新2', 3: '新3'})

    decorated = lnd._decorate_lab_names(items)

    assert called == [{3}]
    assert decorated[0]['lab_name'] == '已有'
    assert decorated[1]['lab_name'] == '新3'
