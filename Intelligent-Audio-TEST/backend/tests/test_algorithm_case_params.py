# -*- coding: utf-8 -*-
"""用例专属参数 CRUD 测试 - 覆盖 case-params 的 list/get/create/update/delete

注意：
- 请求体键名会被 NamingRequest 中间件统一转为 snake_case。
- 查询参数由 NamingAliasMiddleware 自动添加 snake_case/camelCase 别名。
- 响应数据为普通 dict（来自 to_dict()），经 _normalize_payload_data() 递归转换后，
  所有含下划线的键名变为 camelCase。
- error_response 的第二位置参数是 code（错误码），不是 http_code；默认 http_code=400。
- update_case_param 的逻辑：字段在请求体中存在就更新（即使值为 None 也更新）。
"""
import pytest
from backend.models.database import db
from backend.models.algorithm_models import CaseAlgorithmParam

BASE = "/api/v1/algorithm"


# ========== list_case_params (GET /case-params) ==========

class TestListCaseParams:
    def test_list_empty(self, client, app):
        """空列表"""
        resp = client.get(f"{BASE}/case-params")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == 0
        assert data["parameters"] == []

    def test_list_with_data(self, client, app, case_param):
        """有数据"""
        resp = client.get(f"{BASE}/case-params")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == 1
        assert data["parameters"][0]["paramCode"] == "translation_direction"

    def test_list_filter_by_algorithm_type(self, client, app, case_param):
        """按算法类型过滤 - 匹配"""
        resp = client.get(f"{BASE}/case-params?algorithmType=test_algo")
        data = resp.get_json()["data"]
        assert data["total"] == 1

    def test_list_filter_by_algorithm_type_no_match(self, client, app, case_param):
        """按算法类型过滤 - 不匹配"""
        resp = client.get(f"{BASE}/case-params?algorithmType=nonexistent")
        data = resp.get_json()["data"]
        assert data["total"] == 0

    def test_list_filter_by_scope_includes_common(self, client, app, case_param):
        """按 scope=api 过滤 - common 始终包含"""
        resp = client.get(f"{BASE}/case-params?scope=api")
        data = resp.get_json()["data"]
        assert data["total"] == 1  # common scope 始终返回

    def test_list_filter_by_scope_specific(self, client, app, case_param):
        """按 scope 过滤 - 只返回 common + 指定 scope"""
        with app.app_context():
            p = CaseAlgorithmParam(
                algorithm_type="test_algo",
                param_code="api_only_param",
                param_name="API专用",
                param_type="text",
                scope="api",
                ui_order=1,
            )
            db.session.add(p)
            db.session.commit()
        resp = client.get(f"{BASE}/case-params?scope=api")
        data = resp.get_json()["data"]
        assert data["total"] == 2  # common + api

    def test_list_filter_by_scope_excludes_other(self, client, app, case_param):
        """按 scope=api 过滤 - 不包含 e2e 专属参数"""
        with app.app_context():
            p = CaseAlgorithmParam(
                algorithm_type="test_algo",
                param_code="e2e_only_param",
                param_name="E2E专用",
                param_type="text",
                scope="e2e",
                ui_order=1,
            )
            db.session.add(p)
            db.session.commit()
        resp = client.get(f"{BASE}/case-params?scope=api")
        data = resp.get_json()["data"]
        assert data["total"] == 1  # 只有 common，不含 e2e

    def test_list_invalid_scope(self, client, app):
        """无效 scope - 返回错误"""
        resp = client.get(f"{BASE}/case-params?scope=invalid")
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_list_soft_deleted_excluded(self, client, app, case_param):
        """软删除的不返回"""
        with app.app_context():
            case_param.deleted = True
            db.session.commit()
        resp = client.get(f"{BASE}/case-params")
        data = resp.get_json()["data"]
        assert data["total"] == 0


# ========== get_case_param (GET /case-params/<id>) ==========

class TestGetCaseParam:
    def test_get_success(self, client, app, case_param):
        """正常获取"""
        resp = client.get(f"{BASE}/case-params/{case_param.id}")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramCode"] == "translation_direction"
        assert data["algorithmType"] == "test_algo"
        assert data["paramType"] == "text"
        assert data["scope"] == "common"

    def test_get_not_found(self, client, app):
        """不存在 - error_response 默认 http_code=400"""
        resp = client.get(f"{BASE}/case-params/99999")
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_get_soft_deleted_returns_400(self, client, app, case_param):
        """软删除的不返回"""
        with app.app_context():
            case_param.deleted = True
            db.session.commit()
        resp = client.get(f"{BASE}/case-params/{case_param.id}")
        assert resp.status_code == 400


# ========== create_case_param (POST /case-params) ==========

class TestCreateCaseParam:
    def test_create_minimal(self, client, app, algorithm):
        """创建 - 最少字段（paramType 默认 text, scope 默认 common）"""
        resp = client.post(f"{BASE}/case-params", json={
            "algorithmType": "test_algo",
            "paramCode": "case_p1",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramCode"] == "case_p1"
        assert data["algorithmType"] == "test_algo"
        assert data["paramType"] == "text"      # 默认
        assert data["scope"] == "common"         # 默认
        assert data["required"] is False         # 默认
        assert data["uiOrder"] == 0              # 默认
        assert data["hidden"] is False           # 默认

    def test_create_all_fields(self, client, app, algorithm):
        """创建 - 全字段（CaseAlgorithmParam 模型不支持 optionsSource/optionsField/optionsLabelField）"""
        resp = client.post(f"{BASE}/case-params", json={
            "algorithmType": "test_algo",
            "paramCode": "case_full",
            "paramName": "完整参数",
            "label": "标签",
            "paramType": "slider",
            "required": True,
            "defaultValue": '{"default": 50}',
            "helpText": "帮助",
            "uiOrder": 3,
            "hidden": True,
            "scope": "api",
            "minValue": 0.0,
            "maxValue": 100.0,
            "step": 1.0,
            "unit": "dB",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramCode"] == "case_full"
        assert data["paramName"] == "完整参数"
        assert data["label"] == "标签"
        assert data["paramType"] == "slider"
        assert data["required"] is True
        assert data["defaultValue"] == {"default": 50}
        assert data["helpText"] == "帮助"
        assert data["uiOrder"] == 3
        assert data["hidden"] is True
        assert data["scope"] == "api"
        assert data["minValue"] == 0.0
        assert data["maxValue"] == 100.0
        assert data["step"] == 1.0
        assert data["unit"] == "dB"

    def test_create_missing_algorithm_type(self, client, app, algorithm):
        """缺少 algorithmType - 验证失败"""
        resp = client.post(f"{BASE}/case-params", json={
            "paramCode": "no_algo",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_create_missing_param_code(self, client, app, algorithm):
        """缺少 paramCode - 验证失败"""
        resp = client.post(f"{BASE}/case-params", json={
            "algorithmType": "test_algo",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_create_empty_param_code(self, client, app, algorithm):
        """paramCode 为空字符串 - min_length=1"""
        resp = client.post(f"{BASE}/case-params", json={
            "algorithmType": "test_algo",
            "paramCode": "",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_create_invalid_scope(self, client, app, algorithm):
        """无效 scope - pattern 验证失败"""
        resp = client.post(f"{BASE}/case-params", json={
            "algorithmType": "test_algo",
            "paramCode": "bad_scope",
            "scope": "invalid",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_create_duplicate_param_code(self, client, app, case_param):
        """重复创建 - 同 algorithm_type + param_code"""
        resp = client.post(f"{BASE}/case-params", json={
            "algorithmType": "test_algo",
            "paramCode": "translation_direction",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_create_with_e2e_scope(self, client, app, algorithm):
        """创建 e2e scope 参数"""
        resp = client.post(f"{BASE}/case-params", json={
            "algorithmType": "test_algo",
            "paramCode": "e2e_param",
            "scope": "e2e",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["scope"] == "e2e"


# ========== update_case_param (PUT /case-params/<id>) ==========

class TestUpdateCaseParam:
    def test_update_success(self, client, app, case_param):
        """更新 - 多字段"""
        resp = client.put(f"{BASE}/case-params/{case_param.id}", json={
            "paramName": "更新名称",
            "label": "新标签",
            "required": True,
            "uiOrder": 5,
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramName"] == "更新名称"
        assert data["label"] == "新标签"
        assert data["required"] is True
        assert data["uiOrder"] == 5

    def test_update_partial(self, client, app, case_param):
        """部分更新 - 只更新 param_name"""
        resp = client.put(f"{BASE}/case-params/{case_param.id}", json={
            "paramName": "仅名称",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramName"] == "仅名称"
        assert data["paramCode"] == "translation_direction"  # 不变

    def test_update_scope(self, client, app, case_param):
        """更新 scope"""
        resp = client.put(f"{BASE}/case-params/{case_param.id}", json={
            "scope": "api",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["scope"] == "api"

    def test_update_invalid_scope(self, client, app, case_param):
        """更新无效 scope - pattern 验证失败"""
        resp = client.put(f"{BASE}/case-params/{case_param.id}", json={
            "scope": "invalid",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_update_min_max_step(self, client, app, case_param):
        """更新 min/max/step/unit"""
        resp = client.put(f"{BASE}/case-params/{case_param.id}", json={
            "minValue": 10.0,
            "maxValue": 90.0,
            "step": 5.0,
            "unit": "ms",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["minValue"] == 10.0
        assert data["maxValue"] == 90.0
        assert data["step"] == 5.0
        assert data["unit"] == "ms"

    def test_update_not_found(self, client, app):
        """更新不存在的参数"""
        resp = client.put(f"{BASE}/case-params/99999", json={
            "paramName": "不存在",
        })
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_update_soft_deleted_returns_400(self, client, app, case_param):
        """更新软删除的参数"""
        with app.app_context():
            case_param.deleted = True
            db.session.commit()
        resp = client.put(f"{BASE}/case-params/{case_param.id}", json={
            "paramName": "已删除",
        })
        assert resp.status_code == 400

    def test_update_empty_body(self, client, app, case_param):
        """空请求体 - 不改变任何字段"""
        resp = client.put(f"{BASE}/case-params/{case_param.id}", json={})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["paramCode"] == "translation_direction"
        assert data["paramType"] == "text"


# ========== delete_case_param (DELETE /case-params/<id>) ==========

class TestDeleteCaseParam:
    def test_delete_success(self, client, app, case_param):
        """删除成功"""
        resp = client.delete(f"{BASE}/case-params/{case_param.id}")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        with app.app_context():
            p = CaseAlgorithmParam.query.filter_by(id=case_param.id).first()
            assert p.deleted is True

    def test_delete_not_found(self, client, app):
        """删除不存在的参数"""
        resp = client.delete(f"{BASE}/case-params/99999")
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_delete_already_deleted(self, client, app, case_param):
        """删除已软删除的参数"""
        with app.app_context():
            case_param.deleted = True
            db.session.commit()
        resp = client.delete(f"{BASE}/case-params/{case_param.id}")
        assert resp.status_code == 400

    def test_delete_then_not_listed(self, client, app, case_param):
        """删除后不在列表中"""
        resp = client.delete(f"{BASE}/case-params/{case_param.id}")
        assert resp.status_code == 200
        resp = client.get(f"{BASE}/case-params")
        data = resp.get_json()["data"]
        assert data["total"] == 0
