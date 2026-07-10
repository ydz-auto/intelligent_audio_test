# -*- coding: utf-8 -*-
"""算法定义 CRUD 测试 - 覆盖 list/get/create/update/delete 及子配置嵌套创建/更新"""
import pytest
from backend.models.database import db
from backend.models.algorithm_models import (
    AlgorithmDefinition, AlgorithmDeviceParam, AlgorithmApiParam,
    CaseAlgorithmParam, ParamMapping, AlgorithmDimensionRelation,
    AlgorithmReferenceParam,
)
from backend.models.models import Dimension

BASE = "/api/v1/algorithm"


# ========== list_algorithms (GET /definitions) ==========

class TestListAlgorithms:
    def test_list_empty(self, client, app):
        """空列表"""
        resp = client.get(f"{BASE}/definitions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["total"] == 0
        assert data["data"]["data"] == []

    def test_list_with_data(self, client, app, algorithm):
        """有数据"""
        resp = client.get(f"{BASE}/definitions")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == 1
        assert data["data"][0]["type"] == "test_algo"

    def test_filter_by_status(self, client, app, algorithm):
        """按状态过滤 - 匹配"""
        resp = client.get(f"{BASE}/definitions?status=online")
        data = resp.get_json()["data"]
        assert data["total"] == 1

    def test_filter_by_status_no_match(self, client, app, algorithm):
        """按状态过滤 - 不匹配"""
        resp = client.get(f"{BASE}/definitions?status=offline")
        data = resp.get_json()["data"]
        assert data["total"] == 0

    def test_filter_by_group_id(self, client, app, algorithm, group):
        """按分组过滤 - 匹配"""
        resp = client.get(f"{BASE}/definitions?groupId={group.id}")
        data = resp.get_json()["data"]
        assert data["total"] == 1

    def test_filter_by_group_id_no_match(self, client, app, algorithm, group):
        """按分组过滤 - 不匹配"""
        resp = client.get(f"{BASE}/definitions?groupId=99999")
        data = resp.get_json()["data"]
        assert data["total"] == 0

    def test_soft_deleted_excluded(self, client, app, algorithm):
        """软删除的不返回"""
        with app.app_context():
            algorithm.deleted = True
            db.session.commit()
        resp = client.get(f"{BASE}/definitions")
        assert resp.get_json()["data"]["total"] == 0


# ========== get_algorithm (GET /definitions/<type>) ==========

class TestGetAlgorithm:
    def test_get_success(self, client, app, algorithm):
        """正常获取"""
        resp = client.get(f"{BASE}/definitions/test_algo")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["type"] == "test_algo"
        assert data["name"] == "测试算法"

    def test_get_not_found(self, client, app):
        """不存在 - error_response 默认 http_code=400"""
        resp = client.get(f"{BASE}/definitions/nonexistent")
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_get_soft_deleted_returns_400(self, client, app, algorithm):
        """软删除的返回 400"""
        with app.app_context():
            algorithm.deleted = True
            db.session.commit()
        resp = client.get(f"{BASE}/definitions/test_algo")
        assert resp.status_code == 400

    def test_get_includes_sub_configs(self, client, app, algorithm, device_param, case_param, reference_param):
        """详情包含子配置"""
        resp = client.get(f"{BASE}/definitions/test_algo")
        data = resp.get_json()["data"]
        assert len(data["deviceParams"]) == 1
        assert len(data["caseParams"]) == 1
        assert len(data["referenceParams"]) == 1
        assert "mappings" in data
        assert "associatedDimensions" in data


# ========== create_algorithm (POST /definitions) ==========

class TestCreateAlgorithm:
    def test_create_minimal(self, client, app):
        """最小字段创建"""
        resp = client.post(f"{BASE}/definitions", json={
            "type": "new_algo",
            "name": "新算法",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["type"] == "new_algo"
        assert data["name"] == "新算法"
        assert data["status"] == "online"
        assert data["display_order"] == 0

    def test_create_name_required(self, client, app):
        """name 为必填字段 - 缺少时返回错误"""
        resp = client.post(f"{BASE}/definitions", json={
            "type": "no_name",
        })
        assert resp.get_json()["success"] is False

    def test_create_with_all_fields(self, client, app, group):
        """全字段创建"""
        resp = client.post(f"{BASE}/definitions", json={
            "type": "full_algo",
            "name": "完整算法",
            "groupId": group.id,
            "description": "描述",
            "status": "offline",
            "icon": "fa-cog",
            "displayOrder": 5,
        })
        data = resp.get_json()["data"]
        assert data["status"] == "offline"
        assert data["display_order"] == 5
        assert data["group_id"] == group.id

    def test_create_duplicate_type(self, client, app, algorithm):
        """重复 type"""
        resp = client.post(f"{BASE}/definitions", json={
            "type": "test_algo",
            "name": "重复",
        })
        assert resp.get_json()["success"] is False

    def test_create_with_device_params(self, client, app):
        """嵌套创建设备参数"""
        resp = client.post(f"{BASE}/definitions", json={
            "type": "with_params",
            "name": "带参数",
            "deviceParams": [
                {"paramCode": "p1", "paramName": "参数1", "paramType": "text", "direction": "input"}
            ],
        })
        data = resp.get_json()["data"]
        assert len(data["deviceParams"]) == 1
        assert data["deviceParams"][0]["param_code"] == "p1"

    def test_create_with_api_params(self, client, app):
        """嵌套创建 API 参数"""
        resp = client.post(f"{BASE}/definitions", json={
            "type": "with_api",
            "name": "带API参数",
            "apiParams": [
                {"paramCode": "a1", "paramName": "API参数1", "paramType": "text", "direction": "output"}
            ],
        })
        data = resp.get_json()["data"]
        assert len(data["apiParams"]) == 1

    def test_create_with_case_params(self, client, app):
        """嵌套创建用例参数"""
        resp = client.post(f"{BASE}/definitions", json={
            "type": "with_case",
            "name": "带用例参数",
            "caseParams": [
                {"paramCode": "c1", "paramName": "用例参数1", "paramType": "text", "scope": "common"}
            ],
        })
        data = resp.get_json()["data"]
        assert len(data["caseParams"]) == 1

    def test_create_with_mappings(self, client, app, dimension):
        """嵌套创建映射 - 有 dimensionId 的归入 evaluation"""
        resp = client.post(f"{BASE}/definitions", json={
            "type": "with_map",
            "name": "带映射",
            "mappings": {
                "device": [
                    {"source": "device", "sourceParam": "p1", "sourceDirection": "output",
                     "dimensionId": dimension.id, "targetParam": "ref", "transformType": "none"}
                ]
            },
        })
        data = resp.get_json()["data"]
        assert len(data["mappings"]["evaluation"]) == 1

    def test_create_with_associated_dimensions(self, client, app, dimension):
        """嵌套创建维度关联"""
        resp = client.post(f"{BASE}/definitions", json={
            "type": "with_dim",
            "name": "带维度",
            "associatedDimensions": [
                {"dimensionId": dimension.id, "weight": 2.0, "isDefault": True}
            ],
        })
        data = resp.get_json()["data"]
        assert len(data["associatedDimensions"]) == 1

    def test_create_with_all_sub_configs(self, client, app, dimension):
        """同时创建所有子配置"""
        resp = client.post(f"{BASE}/definitions", json={
            "type": "all_sub",
            "name": "全子配置",
            "deviceParams": [{"paramCode": "d1", "paramType": "text", "direction": "input"}],
            "apiParams": [{"paramCode": "a1", "paramType": "text", "direction": "output"}],
            "caseParams": [{"paramCode": "c1", "paramType": "text", "scope": "common"}],
            "mappings": {"device": [{"source": "device", "sourceParam": "d1", "dimensionId": dimension.id, "targetParam": "ref"}]},
            "associatedDimensions": [{"dimensionId": dimension.id, "weight": 1.0}],
        })
        data = resp.get_json()["data"]
        assert len(data["deviceParams"]) == 1
        assert len(data["apiParams"]) == 1
        assert len(data["caseParams"]) == 1
        assert len(data["mappings"]["evaluation"]) == 1
        assert len(data["associatedDimensions"]) == 1

    def test_create_invalid_data(self, client, app):
        """无效数据 - 缺少必填字段"""
        resp = client.post(f"{BASE}/definitions", json={})
        assert resp.get_json()["success"] is False


# ========== update_algorithm (PUT /definitions/<type>) ==========

class TestUpdateAlgorithm:
    def test_update_name(self, client, app, algorithm):
        """更新名称"""
        resp = client.put(f"{BASE}/definitions/test_algo", json={"name": "新名称"})
        data = resp.get_json()["data"]
        assert data["name"] == "新名称"

    def test_update_status(self, client, app, algorithm):
        """更新状态"""
        resp = client.put(f"{BASE}/definitions/test_algo", json={"status": "offline"})
        data = resp.get_json()["data"]
        assert data["status"] == "offline"

    def test_update_group_id(self, client, app, algorithm, group):
        """更新分组"""
        resp = client.put(f"{BASE}/definitions/test_algo", json={"groupId": group.id})
        assert resp.get_json()["data"]["group_id"] == group.id

    def test_update_description(self, client, app, algorithm):
        """更新描述"""
        resp = client.put(f"{BASE}/definitions/test_algo", json={"description": "新描述"})
        assert resp.get_json()["data"]["description"] == "新描述"

    def test_update_icon(self, client, app, algorithm):
        """更新图标"""
        resp = client.put(f"{BASE}/definitions/test_algo", json={"icon": "fa-globe"})
        assert resp.get_json()["data"]["icon"] == "fa-globe"

    def test_update_display_order(self, client, app, algorithm):
        """更新排序"""
        resp = client.put(f"{BASE}/definitions/test_algo", json={"displayOrder": 10})
        assert resp.get_json()["data"]["display_order"] == 10

    def test_update_not_found(self, client, app):
        """更新不存在的算法 - error_response 默认 http_code=400"""
        resp = client.put(f"{BASE}/definitions/nonexistent", json={"name": "x"})
        assert resp.status_code == 400

    def test_update_with_device_params_new(self, client, app, algorithm):
        """更新时新增设备参数"""
        resp = client.put(f"{BASE}/definitions/test_algo", json={
            "deviceParams": [
                {"paramCode": "new_p", "paramType": "text", "direction": "input"}
            ]
        })
        data = resp.get_json()["data"]
        assert len(data["deviceParams"]) == 1

    def test_update_with_device_params_update_existing(self, client, app, algorithm, device_param):
        """更新时修改已有设备参数"""
        resp = client.put(f"{BASE}/definitions/test_algo", json={
            "deviceParams": [
                {"id": device_param.id, "paramName": "新名称"}
            ]
        })
        data = resp.get_json()["data"]
        assert data["deviceParams"][0]["param_name"] == "新名称"

    def test_update_with_device_params_soft_delete(self, client, app, algorithm, device_param):
        """更新时删除未提交的设备参数"""
        resp = client.put(f"{BASE}/definitions/test_algo", json={"deviceParams": []})
        data = resp.get_json()["data"]
        assert len(data["deviceParams"]) == 0

    def test_update_with_case_params(self, client, app, algorithm):
        """更新时新增用例参数"""
        resp = client.put(f"{BASE}/definitions/test_algo", json={
            "caseParams": [{"paramCode": "new_c", "scope": "common"}]
        })
        data = resp.get_json()["data"]
        assert len(data["caseParams"]) == 1

    def test_update_with_case_params_invalid_scope(self, client, app, algorithm, case_param):
        """更新用例参数 - 无效 scope 跳过"""
        resp = client.put(f"{BASE}/definitions/test_algo", json={
            "caseParams": [{"id": case_param.id, "scope": "invalid_scope"}]
        })
        assert resp.status_code == 200

    def test_update_with_mappings(self, client, app, algorithm, dimension):
        """更新时新增映射 - 有 dimensionId 的归入 evaluation"""
        resp = client.put(f"{BASE}/definitions/test_algo", json={
            "mappings": {"device": [{"source": "device", "sourceParam": "p1", "dimensionId": dimension.id, "targetParam": "ref"}]}
        })
        data = resp.get_json()["data"]
        assert len(data["mappings"]["evaluation"]) == 1

    def test_update_with_associated_dimensions(self, client, app, algorithm, dimension):
        """更新时新增维度关联"""
        resp = client.put(f"{BASE}/definitions/test_algo", json={
            "associatedDimensions": [{"dimensionId": dimension.id, "weight": 2.0}]
        })
        data = resp.get_json()["data"]
        assert len(data["associatedDimensions"]) == 1

    def test_update_with_associated_dimensions_soft_delete(self, client, app, algorithm, dimension_relation):
        """更新时删除未提交的维度关联"""
        resp = client.put(f"{BASE}/definitions/test_algo", json={"associatedDimensions": []})
        data = resp.get_json()["data"]
        assert len(data["associatedDimensions"]) == 0


# ========== delete_algorithm (DELETE /definitions/<type>) ==========

class TestDeleteAlgorithm:
    def test_delete_success(self, client, app, algorithm):
        """正常删除"""
        resp = client.delete(f"{BASE}/definitions/test_algo")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        # 验证软删除
        with app.app_context():
            algo = AlgorithmDefinition.query.filter_by(type="test_algo").first()
            assert algo.deleted is True

    def test_delete_not_found(self, client, app):
        """删除不存在的 - error_response 默认 http_code=400"""
        resp = client.delete(f"{BASE}/definitions/nonexistent")
        assert resp.status_code == 400

    def test_delete_already_deleted(self, client, app, algorithm):
        """删除已软删除的 - 返回 400"""
        with app.app_context():
            algorithm.deleted = True
            db.session.commit()
        resp = client.delete(f"{BASE}/definitions/test_algo")
        assert resp.status_code == 400


# ========== get_algorithm_options (GET /options) ==========

class TestGetAlgorithmOptions:
    def test_get_options_empty(self, client, app):
        """空列表"""
        resp = client.get(f"{BASE}/options")
        data = resp.get_json()["data"]
        assert len(data["algorithms"]) == 0

    def test_get_options_only_online(self, client, app, algorithm):
        """只返回 online 状态"""
        resp = client.get(f"{BASE}/options")
        data = resp.get_json()["data"]
        assert len(data["algorithms"]) == 1
        assert data["algorithms"][0]["value"] == "test_algo"

    def test_get_options_excludes_offline(self, client, app, algorithm):
        """排除 offline"""
        with app.app_context():
            algorithm.status = "offline"
            db.session.commit()
        resp = client.get(f"{BASE}/options")
        data = resp.get_json()["data"]
        assert len(data["algorithms"]) == 0

    def test_get_options_excludes_deleted(self, client, app, algorithm):
        """排除软删除"""
        with app.app_context():
            algorithm.deleted = True
            db.session.commit()
        resp = client.get(f"{BASE}/options")
        assert len(resp.get_json()["data"]["algorithms"]) == 0
