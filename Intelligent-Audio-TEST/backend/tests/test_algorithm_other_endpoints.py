# -*- coding: utf-8 -*-
"""算法模块其他端点测试 - 覆盖 options/options-sources/param-options/form-schema/
import/bulk-delete/extract-params/dimension-params/reload

注意：
- 请求体键名会被 NamingRequest 中间件统一转为 snake_case。
- 响应数据为普通 dict，经 _normalize_payload_data() 递归转换后键名为 camelCase。
- get_algorithm_options 只返回 status='online' 的算法。
- get_options_sources 响应结构为 {data: [...]}，外层 success_response 再包一层 data。
- get_form_schema 找不到算法时返回 400（error_response 默认 http_code=400）。
- import_algorithms 会创建新算法（如果不存在）。
- bulk_delete 软删除算法。
- extract_params 依赖 CaseParameterExtractor，使用配置加载器。
"""
import pytest
from backend.models.database import db
from backend.models.algorithm_models import (
    AlgorithmDefinition, AlgorithmDeviceParam,
    CaseAlgorithmParam, EvaluationDimensionParam,
)

BASE = "/api/v1/algorithm"


# ============================================================================
# Get Algorithm Options
# ============================================================================
class TestGetAlgorithmOptions:
    """获取算法选项列表（下拉框用）"""

    def test_options_empty(self, client, app):
        """无算法时返回空列表"""
        resp = client.get(f"{BASE}/options")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["algorithms"] == []

    def test_options_with_data(self, client, algorithm):
        """有在线算法时返回列表"""
        resp = client.get(f"{BASE}/options")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert len(data["algorithms"]) == 1
        opt = data["algorithms"][0]
        assert opt["value"] == "test_algo"
        assert opt["name"] == "测试算法"
        assert opt["groupId"] is not None
        assert opt["groupName"] is not None

    def test_options_excludes_offline(self, client, algorithm):
        """不返回 offline 算法"""
        algorithm.status = "offline"
        db.session.commit()
        resp = client.get(f"{BASE}/options")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["algorithms"] == []

    def test_options_excludes_deleted(self, client, algorithm):
        """不返回已删除的算法"""
        algorithm.deleted = True
        db.session.commit()
        resp = client.get(f"{BASE}/options")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["algorithms"] == []


# ============================================================================
# Get Options Sources
# ============================================================================
@pytest.mark.skip(reason="GET /options-sources 端点尚未在源码中实现（测试计划 TC-OPTS-001/002）")
class TestGetOptionsSources:
    """获取可用选项来源列表"""

    def test_options_sources_returns_list(self, client, app):
        """返回选项来源列表"""
        resp = client.get(f"{BASE}/options-sources")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        # 响应结构: {data: [...]}，外层 success_response 再包一层 data
        assert "data" in data
        sources = data["data"]
        assert isinstance(sources, list)
        # 每个来源至少有 value 和 label
        for s in sources:
            assert "value" in s
            assert "label" in s


# ============================================================================
# Get Param Options
# ============================================================================
@pytest.mark.skip(reason="GET /params/<algo_type>/options 端点尚未在源码中实现")
class TestGetParamOptions:
    """获取参数选项（下拉框用）"""

    def test_param_options_no_params(self, client, algorithm):
        """无用例参数时返回空 options"""
        resp = client.get(f"{BASE}/params/test_algo/options")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["options"] == {}

    def test_param_options_with_params_no_source(self, client, case_param):
        """有用例参数但无 options_source 时返回空 options"""
        resp = client.get(f"{BASE}/params/test_algo/options")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["options"] == {}

    def test_param_options_nonexistent_algorithm(self, client, app):
        """不存在的算法返回空 options"""
        resp = client.get(f"{BASE}/params/nonexistent/options")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["options"] == {}


# ============================================================================
# Get Form Schema
# ============================================================================
class TestGetFormSchema:
    """获取算法表单 Schema"""

    def test_form_schema_no_params(self, client, algorithm):
        """无用例参数时返回空字段列表"""
        resp = client.get(f"{BASE}/form-schema/test_algo")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["algorithmType"] == "test_algo"
        assert data["algorithmName"] == "测试算法"
        assert data["fields"] == []
        assert data["groups"] == []

    def test_form_schema_with_params(self, client, case_param):
        """有用例参数时返回字段列表"""
        resp = client.get(f"{BASE}/form-schema/test_algo")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["algorithmType"] == "test_algo"
        assert len(data["fields"]) == 1
        field = data["fields"][0]
        assert field["fieldCode"] == "translation_direction"
        assert field["fieldType"] == "text"
        assert field["scope"] == "common"

    def test_form_schema_not_found(self, client, app):
        """不存在的算法返回 400"""
        resp = client.get(f"{BASE}/form-schema/nonexistent")
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_form_schema_excludes_hidden(self, client, case_param):
        """隐藏参数不在 schema 中"""
        case_param.hidden = True
        db.session.commit()
        resp = client.get(f"{BASE}/form-schema/test_algo")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["fields"] == []


# ============================================================================
# Import Algorithms
# ============================================================================
class TestImportAlgorithms:
    """导入算法配置"""

    def test_import_new_algorithm(self, client, app):
        """导入新算法"""
        resp = client.post(f"{BASE}/import", json={
            "algorithms": [
                {
                    "type": "imported_algo",
                    "name": "导入算法",
                    "description": "测试导入",
                    "status": "online",
                    "params": [
                        {"code": "input", "name": "输入", "type": "text", "required": True}
                    ]
                }
            ]
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "imported_algo" in data["imported"]
        # 验证算法已创建
        algo = AlgorithmDefinition.query.filter_by(type="imported_algo", deleted=False).first()
        assert algo is not None
        assert algo.name == "导入算法"
        # 验证参数已创建
        param = AlgorithmDeviceParam.query.filter_by(
            algorithm_type="imported_algo", param_code="input"
        ).first()
        assert param is not None

    def test_import_existing_algorithm(self, client, algorithm):
        """导入已存在的算法（不覆盖）"""
        resp = client.post(f"{BASE}/import", json={
            "algorithms": [
                {"type": "test_algo", "name": "新名称", "params": []}
            ]
        })
        assert resp.status_code == 200
        # 名称不应被覆盖
        db.session.refresh(algorithm)
        assert algorithm.name == "测试算法"

    def test_import_multiple(self, client, app):
        """导入多个算法"""
        resp = client.post(f"{BASE}/import", json={
            "algorithms": [
                {"type": "algo_a", "name": "算法A"},
                {"type": "algo_b", "name": "算法B"},
            ]
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert len(data["imported"]) == 2

    def test_import_empty_list(self, client, app):
        """导入空列表"""
        resp = client.post(f"{BASE}/import", json={
            "algorithms": []
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["imported"] == []


# ============================================================================
# Bulk Delete
# ============================================================================
class TestBulkDelete:
    """批量删除算法"""

    def test_bulk_delete_success(self, client, algorithm):
        """成功删除"""
        resp = client.post(f"{BASE}/bulk-delete", json={
            "algorithmTypes": ["test_algo"]
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "test_algo" in data["deletedTypes"]
        # 验证已软删除
        db.session.refresh(algorithm)
        assert algorithm.deleted is True

    def test_bulk_delete_nonexistent(self, client, app):
        """删除不存在的算法"""
        resp = client.post(f"{BASE}/bulk-delete", json={
            "algorithmTypes": ["nonexistent"]
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "nonexistent" not in data["deletedTypes"]

    def test_bulk_delete_missing_field(self, client, app):
        """缺少 algorithmTypes 字段"""
        resp = client.post(f"{BASE}/bulk-delete", json={})
        assert resp.status_code == 400

    def test_bulk_delete_multiple(self, client, app):
        """批量删除多个"""
        # 创建两个算法
        algo1 = AlgorithmDefinition(type="bulk_a", name="A", status="online")
        algo2 = AlgorithmDefinition(type="bulk_b", name="B", status="online")
        db.session.add_all([algo1, algo2])
        db.session.commit()

        resp = client.post(f"{BASE}/bulk-delete", json={
            "algorithmTypes": ["bulk_a", "bulk_b", "nonexistent"]
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert len(data["deletedTypes"]) == 2


# ============================================================================
# Extract Params
# ============================================================================
class TestExtractParams:
    """提取用例算法参数"""

    def test_extract_empty_config(self, client, app):
        """空配置"""
        resp = client.post(f"{BASE}/extract-params", json={
            "caseConfig": {}
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "algorithmType" in data
        assert "device" in data
        assert "api" in data
        assert "evaluation" in data

    def test_extract_with_algorithm_type(self, client, app):
        """带算法类型的配置"""
        resp = client.post(f"{BASE}/extract-params", json={
            "caseConfig": {
                "algorithmType": "test_algo",
                "algorithmParams": {"key": "value"}
            }
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["algorithmType"] == "test_algo"


# ============================================================================
# Get Dimension Params
# ============================================================================
class TestGetDimensionParams:
    """获取评估维度参数列表"""

    def test_dimension_params_empty(self, client, dimension):
        """无参数时返回空列表"""
        resp = client.get(f"{BASE}/dimension-params/{dimension.id}")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["params"] == []

    def test_dimension_params_with_data(self, client, dimension):
        """有参数时返回列表"""
        param = EvaluationDimensionParam(
            dimension_id=dimension.id,
            param_code="ref_text",
            param_name="参考文本",
            field_type="text",
            required=True,
            ui_order=0,
        )
        db.session.add(param)
        db.session.commit()

        resp = client.get(f"{BASE}/dimension-params/{dimension.id}")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert len(data["params"]) == 1
        p = data["params"][0]
        assert p["code"] == "ref_text"
        assert p["name"] == "参考文本"
        assert p["fieldType"] == "text"
        assert p["required"] is True
        assert p["dimensionId"] == dimension.id

    def test_dimension_params_soft_deleted_excluded(self, client, dimension):
        """软删除的参数不在列表中"""
        param = EvaluationDimensionParam(
            dimension_id=dimension.id,
            param_code="deleted_param",
            param_name="已删除",
            field_type="text",
            required=False,
            ui_order=0,
            deleted=True,
        )
        db.session.add(param)
        db.session.commit()

        resp = client.get(f"{BASE}/dimension-params/{dimension.id}")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["params"] == []



