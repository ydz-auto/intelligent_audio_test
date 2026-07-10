# -*- coding: utf-8 -*-
"""维度关联 CRUD 测试 - 覆盖 dimension-relations 的 create/update/delete，
以及 dimensions/<algo_type> 的 GET（获取关联维度）和 POST（批量关联）

注意：
- 请求体键名会被 NamingRequest 中间件统一转为 snake_case，因此发送 camelCase 即可。
- 响应数据为普通 dict（来自 to_dict()），经 _normalize_payload_data() 递归转换后，
  所有含下划线的键名变为 camelCase（如 algorithm_type → algorithmType）。
- error_response 的第二位置参数是 code（错误码），不是 http_code；默认 http_code=400。
- 重要差异：update_dimension_relation 和 delete_dimension_relation 使用 query.get()，
  不过滤 deleted=False，因此对已软删除的记录操作不会返回 400。
- get_algorithm_dimensions 过滤 deleted=False，所以软删除的关联不会显示。
- associate_dimensions 会先软删除所有已有关联，再创建新的。
"""
import pytest
from backend.models.database import db
from backend.models.algorithm_models import AlgorithmDimensionRelation

BASE = "/api/v1/algorithm/dimension-relations"
DIM_BASE = "/api/v1/algorithm/dimensions"


# ============================================================================
# Create
# ============================================================================
class TestCreateDimensionRelation:
    """创建维度关联"""

    def test_create_minimal(self, client, algorithm, dimension):
        """仅传必填字段"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "dimensionId": dimension.id,
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["algorithmType"] == "test_algo"
        assert data["dimensionId"] == dimension.id
        assert data["isDefault"] is False  # 默认值
        assert data["weight"] == 1.0  # 默认值
        assert data["dimensionName"] is not None

    def test_create_all_fields(self, client, algorithm, dimension):
        """传所有字段"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "dimensionId": dimension.id,
            "isDefault": True,
            "weight": 2.5,
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["isDefault"] is True
        assert data["weight"] == 2.5

    def test_create_missing_algorithm_type(self, client, dimension):
        """缺少 algorithmType 返回错误"""
        resp = client.post(BASE, json={
            "dimensionId": dimension.id,
        })
        assert resp.status_code == 400

    def test_create_missing_dimension_id(self, client, algorithm):
        """缺少 dimensionId 返回错误"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
        })
        assert resp.status_code == 400

    def test_create_duplicate(self, client, dimension_relation):
        """重复关联返回错误"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "dimensionId": dimension_relation.dimension_id,
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_create_default_values(self, client, algorithm, dimension):
        """默认 isDefault=False, weight=1.0"""
        resp = client.post(BASE, json={
            "algorithmType": "test_algo",
            "dimensionId": dimension.id,
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["isDefault"] is False
        assert data["weight"] == 1.0


# ============================================================================
# Update
# ============================================================================
class TestUpdateDimensionRelation:
    """更新维度关联"""

    def test_update_success(self, client, dimension_relation, dimension):
        """更新所有字段"""
        resp = client.put(f"{BASE}/{dimension_relation.id}", json={
            "weight": 3.0,
            "isDefault": False,
            "dimensionId": dimension.id,
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["weight"] == 3.0
        assert data["isDefault"] is False

    def test_update_partial_weight(self, client, dimension_relation):
        """部分更新 - 仅 weight"""
        resp = client.put(f"{BASE}/{dimension_relation.id}", json={
            "weight": 5.0,
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["weight"] == 5.0

    def test_update_is_default(self, client, dimension_relation):
        """更新 isDefault"""
        resp = client.put(f"{BASE}/{dimension_relation.id}", json={
            "isDefault": False,
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["isDefault"] is False

    def test_update_not_found(self, client, algorithm):
        """更新不存在的关联返回 400"""
        resp = client.put(f"{BASE}/99999", json={
            "weight": 1.0,
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_update_soft_deleted_succeeds(self, client, dimension_relation):
        """更新已软删除的关联也能成功（query.get 不过滤 deleted）"""
        dimension_relation.deleted = True
        db.session.commit()
        resp = client.put(f"{BASE}/{dimension_relation.id}", json={
            "weight": 9.0,
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["weight"] == 9.0

    def test_update_empty_body(self, client, dimension_relation):
        """空请求体"""
        resp = client.put(f"{BASE}/{dimension_relation.id}", json={})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["weight"] == 1.0  # 不变


# ============================================================================
# Delete
# ============================================================================
class TestDeleteDimensionRelation:
    """删除维度关联"""

    def test_delete_success(self, client, dimension_relation):
        """成功删除"""
        resp = client.delete(f"{BASE}/{dimension_relation.id}")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        # 验证已软删除
        r = AlgorithmDimensionRelation.query.get(dimension_relation.id)
        assert r.deleted is True

    def test_delete_not_found(self, client, algorithm):
        """删除不存在的关联返回 400"""
        resp = client.delete(f"{BASE}/99999")
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_delete_already_deleted_succeeds(self, client, dimension_relation):
        """重复删除也能成功（query.get 不过滤 deleted）"""
        dimension_relation.deleted = True
        db.session.commit()
        resp = client.delete(f"{BASE}/{dimension_relation.id}")
        assert resp.status_code == 200

    def test_delete_then_not_in_dimensions(self, client, dimension_relation):
        """删除后不在 dimensions 列表中"""
        resp = client.delete(f"{BASE}/{dimension_relation.id}")
        assert resp.status_code == 200
        resp = client.get(f"{DIM_BASE}/test_algo")
        data = resp.get_json()["data"]
        assert dimension_relation.dimension_id not in data["dimensionIds"]


# ============================================================================
# Get Algorithm Dimensions
# ============================================================================
class TestGetAlgorithmDimensions:
    """获取算法关联的评估维度"""

    def test_get_empty(self, client, algorithm):
        """无关联维度时返回空"""
        resp = client.get(f"{DIM_BASE}/test_algo")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["dimensions"] == []
        assert data["dimensionIds"] == []
        assert data["defaultDimensionId"] is None
        assert data["weights"] == {}

    def test_get_with_data(self, client, dimension_relation):
        """有关联维度时返回列表"""
        resp = client.get(f"{DIM_BASE}/test_algo")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert len(data["dimensions"]) == 1
        assert data["dimensions"][0]["id"] == dimension_relation.dimension_id
        assert data["dimensions"][0]["isDefault"] is True
        assert data["dimensions"][0]["weight"] == 1.0
        assert data["defaultDimensionId"] == dimension_relation.dimension_id
        # weights 的键是字符串（JSON 序列化）
        assert str(dimension_relation.dimension_id) in data["weights"]

    def test_get_soft_deleted_excluded(self, client, dimension_relation):
        """软删除的关联不在列表中"""
        dimension_relation.deleted = True
        db.session.commit()
        resp = client.get(f"{DIM_BASE}/test_algo")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["dimensions"] == []
        assert data["dimensionIds"] == []

    def test_get_nonexistent_algorithm(self, client, algorithm):
        """不存在的算法返回空列表"""
        resp = client.get(f"{DIM_BASE}/nonexistent")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["dimensions"] == []


# ============================================================================
# Associate Dimensions
# ============================================================================
class TestAssociateDimensions:
    """批量关联评估维度"""

    def test_associate_new(self, client, algorithm, dimension):
        """关联新维度"""
        resp = client.post(f"{DIM_BASE}/test_algo", json={
            "dimensions": [
                {"dimensionId": dimension.id, "weight": 2.0, "isDefault": True}
            ]
        })
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        # 验证关联已创建
        resp = client.get(f"{DIM_BASE}/test_algo")
        data = resp.get_json()["data"]
        assert len(data["dimensions"]) == 1
        assert data["dimensions"][0]["weight"] == 2.0
        assert data["defaultDimensionId"] == dimension.id

    def test_associate_replaces_existing(self, client, dimension_relation, dimension):
        """关联会替换已有关联（旧的被软删除）

        注意：uq_algorithm_dimension 唯一约束不包含 deleted 字段，
        所以不能用相同的 dimension_id 重新关联，需要用不同的维度。
        """
        from backend.models.models import Dimension
        # 创建第二个维度
        dim2 = Dimension(name="CER_test", type="auto", result_type=1, weight=1)
        db.session.add(dim2)
        db.session.commit()
        db.session.refresh(dim2)

        # 先确认已有一条关联
        assert len(client.get(f"{DIM_BASE}/test_algo").get_json()["data"]["dimensions"]) == 1

        # 重新关联（用不同的维度）
        resp = client.post(f"{DIM_BASE}/test_algo", json={
            "dimensions": [
                {"dimensionId": dim2.id, "weight": 3.0, "isDefault": True}
            ]
        })
        assert resp.status_code == 200
        # 验证只有一条关联
        data = client.get(f"{DIM_BASE}/test_algo").get_json()["data"]
        assert len(data["dimensions"]) == 1
        assert data["dimensions"][0]["weight"] == 3.0

    def test_associate_empty_clears_all(self, client, dimension_relation):
        """空列表清除所有关联"""
        resp = client.post(f"{DIM_BASE}/test_algo", json={
            "dimensions": []
        })
        assert resp.status_code == 200
        data = client.get(f"{DIM_BASE}/test_algo").get_json()["data"]
        assert data["dimensions"] == []

    def test_associate_multiple(self, client, algorithm, dimension):
        """关联多个维度"""
        from backend.models.models import Dimension
        dim2 = Dimension(name="CER_test", type="auto", result_type=1, weight=1)
        db.session.add(dim2)
        db.session.commit()
        db.session.refresh(dim2)

        resp = client.post(f"{DIM_BASE}/test_algo", json={
            "dimensions": [
                {"dimensionId": dimension.id, "weight": 1.0, "isDefault": True},
                {"dimensionId": dim2.id, "weight": 2.0, "isDefault": False},
            ]
        })
        assert resp.status_code == 200
        data = client.get(f"{DIM_BASE}/test_algo").get_json()["data"]
        assert len(data["dimensions"]) == 2
        assert data["defaultDimensionId"] == dimension.id
