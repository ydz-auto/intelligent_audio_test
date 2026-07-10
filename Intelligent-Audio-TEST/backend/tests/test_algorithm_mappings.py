# -*- coding: utf-8 -*-
"""参数映射 CRUD 测试 - 覆盖 mappings 的 list/create/update/delete

注意：
- 请求体键名会被 NamingRequest 中间件统一转为 snake_case，因此发送 camelCase 即可。
- 查询参数由 NamingAliasMiddleware 自动添加 snake_case/camelCase 别名。
- 响应数据为普通 dict（控制器内联构建），经 _normalize_payload_data() 递归转换后，
  所有含下划线的键名变为 camelCase（如 algorithm_type → algorithmType）。
- schema 中 source_type 字段映射到模型 source 列。
- 没有 GET 单个映射的接口，只有 list/create/update/delete。
- error_response 的第二位置参数是 code（错误码），不是 http_code；默认 http_code=400。
"""
import pytest
from backend.models.database import db
from backend.models.algorithm_models import ParamMapping

BASE = "/api/v1/algorithm/mappings"


# ============================================================================
# List
# ============================================================================
class TestListMappings:
    """参数映射列表"""

    def test_list_empty(self, client, algorithm):
        """无数据时返回空列表"""
        resp = client.get(BASE)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["mappings"] == []
        assert data["data"]["total"] == 0

    def test_list_with_data(self, client, mapping):
        """有数据时返回列表"""
        resp = client.get(BASE)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == 1
        m = data["mappings"][0]
        assert m["algorithmType"] == "test_algo"
        assert m["source"] == "device"
        assert m["sourceParam"] == "input_text"
        assert m["sourceDirection"] == "output"
        assert m["targetParam"] == "ref_text"
        assert m["transformType"] == "none"
        assert m["dimensionId"] is not None
        assert m["dimensionName"] is not None

    def test_list_filter_by_algorithm_type(self, client, mapping):
        """按 algorithmType 过滤"""
        resp = client.get(f"{BASE}?algorithmType=test_algo")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["total"] == 1

    def test_list_filter_by_algorithm_type_no_match(self, client, mapping):
        """过滤不匹配的 algorithmType"""
        resp = client.get(f"{BASE}?algorithmType=nonexistent")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["total"] == 0

    def test_list_filter_by_source_type(self, client, mapping):
        """按 sourceType 过滤"""
        resp = client.get(f"{BASE}?sourceType=device")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["total"] == 1

    def test_list_filter_by_source_type_no_match(self, client, mapping):
        """过滤不匹配的 sourceType"""
        resp = client.get(f"{BASE}?sourceType=api")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["total"] == 0

    def test_list_filter_by_dimension_id(self, client, mapping, dimension):
        """按 dimensionId 过滤"""
        resp = client.get(f"{BASE}?dimensionId={dimension.id}")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["total"] == 1

    def test_list_soft_deleted_excluded(self, client, mapping):
        """软删除的映射不在列表中"""
        mapping.deleted = True
        db.session.commit()
        resp = client.get(BASE)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["total"] == 0


# ============================================================================
# Create
# ============================================================================
class TestCreateMapping:
    """创建参数映射"""

    def test_create_minimal(self, client, algorithm):
        """仅传必填字段"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "sourceType": "device",
            "sourceParam": "input_text",
            "targetParam": "ref_text",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["algorithmType"] == "test_algo"
        assert data["source"] == "device"
        assert data["sourceParam"] == "input_text"
        assert data["sourceDirection"] == "output"  # 默认值
        assert data["transformType"] == "none"  # 默认值
        assert data["targetParam"] == "ref_text"
        assert data["dimensionId"] is None

    def test_create_all_fields(self, client, algorithm, dimension):
        """传所有字段"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "sourceType": "api",
            "sourceParam": "api_result",
            "sourceDirection": "input",
            "dimensionId": dimension.id,
            "targetParam": "eval_param",
            "transformType": "uppercase",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["source"] == "api"
        assert data["sourceParam"] == "api_result"
        assert data["sourceDirection"] == "input"
        assert data["dimensionId"] == dimension.id
        assert data["targetParam"] == "eval_param"
        assert data["transformType"] == "uppercase"

    def test_create_without_dimension_id(self, client, algorithm):
        """不传 dimensionId（可为空）"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "sourceType": "case",
            "sourceParam": "case_param",
            "targetParam": "target",
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["dimensionId"] is None

    def test_create_missing_algorithm_type(self, client, algorithm):
        """缺少 algorithmType 返回错误"""
        resp = client.post(BASE, json={
            "sourceType": "device",
            "sourceParam": "input_text",
            "targetParam": "ref_text",
        })
        assert resp.status_code == 400

    def test_create_missing_source_type(self, client, algorithm):
        """缺少 sourceType 返回错误"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "sourceParam": "input_text",
            "targetParam": "ref_text",
        })
        assert resp.status_code == 400

    def test_create_missing_source_param(self, client, algorithm):
        """缺少 sourceParam 返回错误"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "sourceType": "device",
            "targetParam": "ref_text",
        })
        assert resp.status_code == 400

    def test_create_missing_target_param(self, client, algorithm):
        """缺少 targetParam 返回错误"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "sourceType": "device",
            "sourceParam": "input_text",
        })
        assert resp.status_code == 400

    def test_create_default_values(self, client, algorithm):
        """默认 sourceDirection 和 transformType"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "sourceType": "reference",
            "sourceParam": "ref",
            "targetParam": "target",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["sourceDirection"] == "output"
        assert data["transformType"] == "none"


# ============================================================================
# Update
# ============================================================================
class TestUpdateMapping:
    """更新参数映射"""

    def test_update_success(self, client, mapping, dimension):
        """更新所有字段"""
        resp = client.put(f"{BASE}/{mapping.id}", json={
            "sourceType": "api",
            "sourceParam": "updated_param",
            "sourceDirection": "input",
            "dimensionId": dimension.id,
            "targetParam": "updated_target",
            "transformType": "lowercase",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["source"] == "api"
        assert data["sourceParam"] == "updated_param"
        assert data["sourceDirection"] == "input"
        assert data["dimensionId"] == dimension.id
        assert data["targetParam"] == "updated_target"
        assert data["transformType"] == "lowercase"

    def test_update_partial(self, client, mapping):
        """部分更新"""
        resp = client.put(f"{BASE}/{mapping.id}", json={
            "transformType": "json_parse",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["transformType"] == "json_parse"
        # 其他字段不变
        assert data["source"] == "device"
        assert data["sourceParam"] == "input_text"

    def test_update_source_type(self, client, mapping):
        """更新 sourceType"""
        resp = client.put(f"{BASE}/{mapping.id}", json={
            "sourceType": "case",
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["source"] == "case"

    def test_update_not_found(self, client, algorithm):
        """更新不存在的映射返回 400"""
        resp = client.put(f"{BASE}/99999", json={
            "transformType": "none",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_update_soft_deleted_returns_400(self, client, mapping):
        """更新已软删除的映射返回 400"""
        mapping.deleted = True
        db.session.commit()
        resp = client.put(f"{BASE}/{mapping.id}", json={
            "transformType": "none",
        })
        assert resp.status_code == 400

    def test_update_empty_body(self, client, mapping):
        """空请求体"""
        resp = client.put(f"{BASE}/{mapping.id}", json={})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["source"] == "device"
        assert data["targetParam"] == "ref_text"


# ============================================================================
# Delete
# ============================================================================
class TestDeleteMapping:
    """删除参数映射"""

    def test_delete_success(self, client, mapping):
        """成功删除"""
        resp = client.delete(f"{BASE}/{mapping.id}")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        # 验证已软删除
        m = ParamMapping.query.get(mapping.id)
        assert m.deleted is True

    def test_delete_not_found(self, client, algorithm):
        """删除不存在的映射返回 400"""
        resp = client.delete(f"{BASE}/99999")
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_delete_already_deleted(self, client, mapping):
        """重复删除返回 400"""
        mapping.deleted = True
        db.session.commit()
        resp = client.delete(f"{BASE}/{mapping.id}")
        assert resp.status_code == 400

    def test_delete_then_not_listed(self, client, mapping):
        """删除后不在列表中"""
        resp = client.delete(f"{BASE}/{mapping.id}")
        assert resp.status_code == 200
        resp = client.get(BASE)
        assert resp.get_json()["data"]["total"] == 0
