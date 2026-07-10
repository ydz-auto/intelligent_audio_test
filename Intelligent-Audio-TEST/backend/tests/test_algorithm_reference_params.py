# -*- coding: utf-8 -*-
"""算法参考参数 CRUD 测试 - 覆盖 reference-params 的 list/create/update/delete

注意：
- 请求体键名会被 NamingRequest 中间件统一转为 snake_case，因此发送 camelCase 即可。
- 查询参数由 NamingAliasMiddleware 自动添加 snake_case/camelCase 别名。
- 响应数据为普通 dict（来自 to_dict()），经 _normalize_payload_data() 递归转换后，
  所有含下划线的键名变为 camelCase（如 algorithm_type → algorithmType）。
- to_dict() 返回 'type' 字段（模型列为 param_type，但 to_dict 映射为 type）。
- error_response 的第二位置参数是 code（错误码），不是 http_code；默认 http_code=400。
- update 逻辑：code 和 type 用 truthy 检查（if req.code:），其余字段用 is not None 检查。
- 没有 GET 单个参考参数的接口，只有 list/create/update/delete。
"""
import pytest
from backend.models.database import db
from backend.models.algorithm_models import AlgorithmReferenceParam

BASE = "/api/v1/algorithm/reference-params"


# ============================================================================
# List
# ============================================================================
class TestListReferenceParams:
    """参考参数列表"""

    def test_list_empty(self, client, algorithm):
        """无数据时返回空列表"""
        resp = client.get(f"{BASE}?algorithmType=test_algo")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["parameters"] == []
        assert data["data"]["total"] == 0

    def test_list_with_data(self, client, reference_param):
        """有数据时返回列表"""
        resp = client.get(f"{BASE}?algorithmType=test_algo")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == 1
        param = data["parameters"][0]
        assert param["code"] == "asr_ref"
        assert param["algorithmType"] == "test_algo"
        assert param["type"] == "text"
        assert param["annotationCode"] == "asr_ref"
        assert param["mergeMode"] == "join"

    def test_list_filter_by_algorithm_type(self, client, reference_param):
        """按 algorithmType 过滤"""
        resp = client.get(f"{BASE}?algorithmType=test_algo")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["total"] == 1

    def test_list_filter_no_match(self, client, reference_param):
        """过滤不匹配的 algorithmType 返回空"""
        resp = client.get(f"{BASE}?algorithmType=nonexistent")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == 0
        assert data["parameters"] == []

    def test_list_missing_algorithm_type(self, client, algorithm):
        """缺少 algorithmType 参数返回错误"""
        resp = client.get(BASE)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False

    def test_list_soft_deleted_excluded(self, client, reference_param):
        """软删除的参数不在列表中"""
        reference_param.deleted = True
        db.session.commit()
        resp = client.get(f"{BASE}?algorithmType=test_algo")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["total"] == 0


# ============================================================================
# Create
# ============================================================================
class TestCreateReferenceParam:
    """创建参考参数"""

    def test_create_minimal(self, client, algorithm):
        """仅传必填字段"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "code": "ref_text",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["code"] == "ref_text"
        assert data["algorithmType"] == "test_algo"
        assert data["type"] == "text"  # 默认值
        assert data["mergeMode"] == "join"  # 默认值
        assert data["name"] == ""  # 默认空字符串

    def test_create_all_fields(self, client, algorithm):
        """传所有字段"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "code": "asr_ref",
            "name": "ASR参考",
            "type": "json",
            "annotationCode": "asr_ann",
            "annotationFormat": "json",
            "fieldPath": "model.segments[].text",
            "mergeMode": "collect",
            "helpText": "ASR参考文本",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["code"] == "asr_ref"
        assert data["name"] == "ASR参考"
        assert data["type"] == "json"
        assert data["annotationCode"] == "asr_ann"
        assert data["annotationFormat"] == "json"
        assert data["fieldPath"] == "model.segments[].text"
        assert data["mergeMode"] == "collect"
        assert data["helpText"] == "ASR参考文本"

    def test_create_missing_algorithm_type(self, client, algorithm):
        """缺少 algorithmType 返回错误"""
        resp = client.post(BASE, json={
            "code": "ref_text",
        })
        assert resp.status_code == 400

    def test_create_missing_code(self, client, algorithm):
        """缺少 code 返回错误"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
        })
        assert resp.status_code == 400

    def test_create_duplicate_code(self, client, reference_param):
        """重复 code 返回错误"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "code": "asr_ref",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_create_with_annotation_and_field_path(self, client, algorithm):
        """创建带标注和字段路径的参数"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "code": "rttm_ref",
            "type": "rttm",
            "annotationCode": "rttm_ann",
            "annotationFormat": "rttm",
            "fieldPath": "segments",
            "mergeMode": "first",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["type"] == "rttm"
        assert data["annotationFormat"] == "rttm"
        assert data["mergeMode"] == "first"

    def test_create_default_type_and_merge_mode(self, client, algorithm):
        """不传 type 和 mergeMode 时使用默认值"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "code": "ref1",
            "name": "参考1",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["type"] == "text"
        assert data["mergeMode"] == "join"


# ============================================================================
# Update
# ============================================================================
class TestUpdateReferenceParam:
    """更新参考参数"""

    def test_update_success(self, client, reference_param):
        """更新所有字段"""
        resp = client.put(f"{BASE}/{reference_param.id}", json={
            "code": "updated_ref",
            "name": "更新后的名称",
            "type": "json",
            "annotationCode": "updated_ann",
            "annotationFormat": "json",
            "fieldPath": "updated.path",
            "mergeMode": "collect",
            "helpText": "更新后的帮助",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["code"] == "updated_ref"
        assert data["name"] == "更新后的名称"
        assert data["type"] == "json"
        assert data["annotationCode"] == "updated_ann"
        assert data["annotationFormat"] == "json"
        assert data["fieldPath"] == "updated.path"
        assert data["mergeMode"] == "collect"
        assert data["helpText"] == "更新后的帮助"

    def test_update_partial(self, client, reference_param):
        """部分更新"""
        resp = client.put(f"{BASE}/{reference_param.id}", json={
            "name": "新名称",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["name"] == "新名称"
        # 其他字段不变
        assert data["code"] == "asr_ref"
        assert data["type"] == "text"

    def test_update_code(self, client, reference_param):
        """更新 code"""
        resp = client.put(f"{BASE}/{reference_param.id}", json={
            "code": "new_code",
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["code"] == "new_code"

    def test_update_name_to_empty(self, client, reference_param):
        """name 设为空字符串（is not None 检查，空字符串会更新）"""
        resp = client.put(f"{BASE}/{reference_param.id}", json={
            "name": "",
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["name"] == ""

    def test_update_not_found(self, client, algorithm):
        """更新不存在的参数返回 400"""
        resp = client.put(f"{BASE}/99999", json={
            "name": "test",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_update_soft_deleted_returns_400(self, client, reference_param):
        """更新已软删除的参数返回 400"""
        reference_param.deleted = True
        db.session.commit()
        resp = client.put(f"{BASE}/{reference_param.id}", json={
            "name": "test",
        })
        assert resp.status_code == 400

    def test_update_empty_body(self, client, reference_param):
        """空请求体"""
        resp = client.put(f"{BASE}/{reference_param.id}", json={})
        assert resp.status_code == 200
        # 数据不变
        data = resp.get_json()["data"]
        assert data["code"] == "asr_ref"


# ============================================================================
# Delete
# ============================================================================
class TestDeleteReferenceParam:
    """删除参考参数"""

    def test_delete_success(self, client, reference_param):
        """成功删除"""
        resp = client.delete(f"{BASE}/{reference_param.id}")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        # 验证已软删除
        param = AlgorithmReferenceParam.query.get(reference_param.id)
        assert param.deleted is True

    def test_delete_not_found(self, client, algorithm):
        """删除不存在的参数返回 400"""
        resp = client.delete(f"{BASE}/99999")
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_delete_already_deleted(self, client, reference_param):
        """重复删除返回 400"""
        reference_param.deleted = True
        db.session.commit()
        resp = client.delete(f"{BASE}/{reference_param.id}")
        assert resp.status_code == 400

    def test_delete_then_not_listed(self, client, reference_param):
        """删除后不在列表中"""
        resp = client.delete(f"{BASE}/{reference_param.id}")
        assert resp.status_code == 200
        resp = client.get(f"{BASE}?algorithmType=test_algo")
        assert resp.get_json()["data"]["total"] == 0
