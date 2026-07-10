# -*- coding: utf-8 -*-
"""算法参数 CRUD 测试 - 覆盖设备参数和API参数的 list/get/create/update/delete

注意：
- 请求体键名会被 NamingRequest 中间件统一转为 snake_case，因此发送 camelCase 即可。
- 响应数据为普通 dict（来自 to_dict()），经 _normalize_payload_data() 递归转换后，
  所有含下划线的键名变为 camelCase（如 param_code → paramCode）。
- error_response 的第二位置参数是 code（错误码），不是 http_code；默认 http_code=400。
"""
import pytest
from backend.models.database import db
from backend.models.algorithm_models import (
    AlgorithmDeviceParam, AlgorithmApiParam,
)

BASE = "/api/v1/algorithm"


# ========== list_params (GET /params) ==========

class TestListParams:
    def test_list_device_empty(self, client, app):
        """空列表 - 设备参数"""
        resp = client.get(f"{BASE}/params?paramType=device")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == 0
        assert data["parameters"] == []

    def test_list_api_empty(self, client, app):
        """空列表 - API参数"""
        resp = client.get(f"{BASE}/params?paramType=api")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == 0
        assert data["parameters"] == []

    def test_list_device_with_data(self, client, app, device_param):
        """有数据 - 设备参数"""
        resp = client.get(f"{BASE}/params?paramType=device")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == 1
        assert data["parameters"][0]["paramCode"] == "input_text"

    def test_list_api_with_data(self, client, app, api_param):
        """有数据 - API参数"""
        resp = client.get(f"{BASE}/params?paramType=api")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == 1
        assert data["parameters"][0]["paramCode"] == "api_result"

    def test_list_default_param_type_is_device(self, client, app, device_param, api_param):
        """不传 paramType 时默认为 device"""
        resp = client.get(f"{BASE}/params")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == 1  # 仅设备参数
        assert data["parameters"][0]["paramCode"] == "input_text"

    def test_list_filter_by_algorithm_type(self, client, app, device_param):
        """按算法类型过滤 - 匹配"""
        resp = client.get(f"{BASE}/params?paramType=device&algorithmType=test_algo")
        data = resp.get_json()["data"]
        assert data["total"] == 1

    def test_list_filter_by_algorithm_type_no_match(self, client, app, device_param):
        """按算法类型过滤 - 不匹配"""
        resp = client.get(f"{BASE}/params?paramType=device&algorithmType=nonexistent")
        data = resp.get_json()["data"]
        assert data["total"] == 0

    def test_list_soft_deleted_excluded(self, client, app, device_param):
        """软删除的不返回"""
        with app.app_context():
            device_param.deleted = True
            db.session.commit()
        resp = client.get(f"{BASE}/params?paramType=device")
        data = resp.get_json()["data"]
        assert data["total"] == 0


# ========== get_param (GET /params/<id>) ==========

class TestGetParam:
    def test_get_device_param_success(self, client, app, device_param):
        """正常获取设备参数"""
        resp = client.get(f"{BASE}/params/{device_param.id}")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramCode"] == "input_text"
        assert data["algorithmType"] == "test_algo"
        assert data["paramType"] == "text"
        assert data["direction"] == "input"
        assert data["required"] is True

    def test_get_api_param_success(self, client, app, api_param):
        """正常获取API参数"""
        resp = client.get(f"{BASE}/params/{api_param.id}")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramCode"] == "api_result"
        assert data["algorithmType"] == "test_algo"
        assert data["paramType"] == "text"
        assert data["direction"] == "output"

    def test_get_not_found(self, client, app):
        """不存在 - error_response 默认 http_code=400"""
        resp = client.get(f"{BASE}/params/99999")
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_get_soft_deleted_returns_400(self, client, app, device_param):
        """软删除的不返回"""
        with app.app_context():
            device_param.deleted = True
            db.session.commit()
        resp = client.get(f"{BASE}/params/{device_param.id}")
        assert resp.status_code == 400


# ========== create_param (POST /params) ==========

class TestCreateParam:
    def test_create_device_param_minimal(self, client, app, algorithm):
        """创建设备参数 - 最少字段"""
        resp = client.post(f"{BASE}/params", json={
            "paramTypeSource": "device",
            "algorithmType": "test_algo",
            "paramCode": "dev_param_1",
            "paramType": "text",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramCode"] == "dev_param_1"
        assert data["algorithmType"] == "test_algo"
        assert data["paramType"] == "text"
        assert data["direction"] == "input"       # 默认
        assert data["required"] is False           # 默认
        assert data["uiOrder"] == 0                # 默认
        assert data["hidden"] is False             # 默认

    def test_create_api_param_minimal(self, client, app, algorithm):
        """创建API参数 - 最少字段"""
        resp = client.post(f"{BASE}/params", json={
            "paramTypeSource": "api",
            "algorithmType": "test_algo",
            "paramCode": "api_param_1",
            "paramType": "text",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramCode"] == "api_param_1"
        assert data["algorithmType"] == "test_algo"

    def test_create_device_param_all_fields(self, client, app, algorithm):
        """创建设备参数 - 全字段"""
        resp = client.post(f"{BASE}/params", json={
            "paramTypeSource": "device",
            "algorithmType": "test_algo",
            "paramCode": "dev_full",
            "paramName": "设备参数完整",
            "label": "设备参数标签",
            "paramType": "audio_file",
            "direction": "output",
            "required": True,
            "defaultValue": '{"key": "val"}',
            "validationRules": '{"min": 1, "max": 10}',
            "helpText": "帮助文字",
            "uiOrder": 5,
            "hidden": True,
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramCode"] == "dev_full"
        assert data["paramName"] == "设备参数完整"
        assert data["label"] == "设备参数标签"
        assert data["paramType"] == "audio_file"
        assert data["direction"] == "output"
        assert data["required"] is True
        assert data["defaultValue"] == {"key": "val"}
        assert data["validation"] == {"min": 1, "max": 10}
        assert data["helpText"] == "帮助文字"
        assert data["uiOrder"] == 5
        assert data["hidden"] is True

    def test_create_default_param_type_source(self, client, app, algorithm):
        """不传 paramTypeSource 时默认为 device"""
        resp = client.post(f"{BASE}/params", json={
            "algorithmType": "test_algo",
            "paramCode": "default_source",
            "paramType": "text",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramCode"] == "default_source"

    def test_create_missing_algorithm_type(self, client, app, algorithm):
        """缺少 algorithmType - 验证失败"""
        resp = client.post(f"{BASE}/params", json={
            "paramTypeSource": "device",
            "paramCode": "no_algo",
            "paramType": "text",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_create_missing_param_code(self, client, app, algorithm):
        """缺少 paramCode - 验证失败"""
        resp = client.post(f"{BASE}/params", json={
            "paramTypeSource": "device",
            "algorithmType": "test_algo",
            "paramType": "text",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_create_missing_param_type(self, client, app, algorithm):
        """缺少 paramType - 验证失败"""
        resp = client.post(f"{BASE}/params", json={
            "paramTypeSource": "device",
            "algorithmType": "test_algo",
            "paramCode": "no_type",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_create_empty_param_code(self, client, app, algorithm):
        """paramCode 为空字符串 - min_length=1 验证失败"""
        resp = client.post(f"{BASE}/params", json={
            "paramTypeSource": "device",
            "algorithmType": "test_algo",
            "paramCode": "",
            "paramType": "text",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_create_duplicate_device_param(self, client, app, device_param):
        """重复创建设备参数 - 同 algorithm_type + param_code + direction"""
        resp = client.post(f"{BASE}/params", json={
            "paramTypeSource": "device",
            "algorithmType": "test_algo",
            "paramCode": "input_text",
            "paramType": "text",
            "direction": "input",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_create_duplicate_api_param(self, client, app, api_param):
        """重复创建API参数"""
        resp = client.post(f"{BASE}/params", json={
            "paramTypeSource": "api",
            "algorithmType": "test_algo",
            "paramCode": "api_result",
            "paramType": "text",
            "direction": "output",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_create_same_code_different_direction(self, client, app, device_param):
        """相同 paramCode 但不同 direction - 允许创建"""
        resp = client.post(f"{BASE}/params", json={
            "paramTypeSource": "device",
            "algorithmType": "test_algo",
            "paramCode": "input_text",
            "paramType": "text",
            "direction": "output",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["direction"] == "output"


# ========== update_param (PUT /params/<id>) ==========

class TestUpdateParam:
    def test_update_device_param_success(self, client, app, device_param):
        """更新设备参数 - 多字段"""
        resp = client.put(f"{BASE}/params/{device_param.id}", json={
            "paramName": "更新后的名称",
            "label": "新标签",
            "required": False,
            "uiOrder": 10,
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramName"] == "更新后的名称"
        assert data["label"] == "新标签"
        assert data["required"] is False
        assert data["uiOrder"] == 10

    def test_update_api_param_success(self, client, app, api_param):
        """更新API参数"""
        resp = client.put(f"{BASE}/params/{api_param.id}", json={
            "paramName": "更新API名称",
            "hidden": True,
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramName"] == "更新API名称"
        assert data["hidden"] is True

    def test_update_partial_only_param_name(self, client, app, device_param):
        """部分更新 - 只更新 param_name"""
        resp = client.put(f"{BASE}/params/{device_param.id}", json={
            "paramName": "仅更新名称",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramName"] == "仅更新名称"
        # 其他字段不变
        assert data["paramCode"] == "input_text"
        assert data["paramType"] == "text"

    def test_update_not_found(self, client, app):
        """更新不存在的参数"""
        resp = client.put(f"{BASE}/params/99999", json={
            "paramName": "不存在",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_update_soft_deleted_returns_400(self, client, app, device_param):
        """更新软删除的参数"""
        with app.app_context():
            device_param.deleted = True
            db.session.commit()
        resp = client.put(f"{BASE}/params/{device_param.id}", json={
            "paramName": "已删除",
        })
        assert resp.status_code == 400

    def test_update_direction(self, client, app, device_param):
        """更新 direction"""
        resp = client.put(f"{BASE}/params/{device_param.id}", json={
            "direction": "output",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["direction"] == "output"

    def test_update_default_value(self, client, app, device_param):
        """更新 default_value（JSON 字符串）"""
        resp = client.put(f"{BASE}/params/{device_param.id}", json={
            "defaultValue": '{"updated": true}',
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["defaultValue"] == {"updated": True}

    def test_update_empty_body(self, client, app, device_param):
        """空请求体 - 不改变任何字段"""
        resp = client.put(f"{BASE}/params/{device_param.id}", json={})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramCode"] == "input_text"
        assert data["paramType"] == "text"


# ========== delete_param (DELETE /params/<id>) ==========

class TestDeleteParam:
    def test_delete_device_param_success(self, client, app, device_param):
        """删除设备参数"""
        resp = client.delete(f"{BASE}/params/{device_param.id}")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        # 验证软删除
        with app.app_context():
            p = AlgorithmDeviceParam.query.filter_by(id=device_param.id).first()
            assert p.deleted is True

    def test_delete_api_param_success(self, client, app, api_param):
        """删除API参数"""
        resp = client.delete(f"{BASE}/params/{api_param.id}")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        with app.app_context():
            p = AlgorithmApiParam.query.filter_by(id=api_param.id).first()
            assert p.deleted is True

    def test_delete_not_found(self, client, app):
        """删除不存在的参数"""
        resp = client.delete(f"{BASE}/params/99999")
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_delete_already_deleted(self, client, app, device_param):
        """删除已软删除的参数"""
        with app.app_context():
            device_param.deleted = True
            db.session.commit()
        resp = client.delete(f"{BASE}/params/{device_param.id}")
        assert resp.status_code == 400

    def test_delete_then_not_listed(self, client, app, device_param):
        """删除后不在列表中"""
        resp = client.delete(f"{BASE}/params/{device_param.id}")
        assert resp.status_code == 200
        resp = client.get(f"{BASE}/params?paramType=device")
        data = resp.get_json()["data"]
        assert data["total"] == 0
