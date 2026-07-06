# -*- coding: utf-8 -*-
"""
用例标签视图接口测试。

覆盖：
- GET /test-cases?view=tag 返回按标签聚合的用例列表
- 不传 view 参数时保持原分组视图行为
- 筛选参数 keyword/type/algorithm_type 透传
- 用例字段包含 totalDuration（camelCase）
- 分页参数 page/per_page 正确返回
"""
import pytest


class TestTestCaseTagView:
    """用例标签视图"""

    def test_tag_view_returns_grouped_by_tag(self):
        """view=tag 时返回按标签聚合的用例列表"""
        from backend.app import create_app

        app = create_app("testing")
        client = app.test_client()

        resp = client.get("/api/v1/testcases?view=tag")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        # 标签视图返回 { items: [{ tag, testCases: [...] }] } 结构
        data = body["data"]
        assert "items" in data
        # 每项至少有 tag 和 testCases 字段
        if data["items"]:
            item = data["items"][0]
            assert "tag" in item
            assert "testCases" in item

    def test_default_view_unchanged(self):
        """不传 view 参数时保持原有行为"""
        from backend.app import create_app

        app = create_app("testing")
        client = app.test_client()

        resp = client.get("/api/v1/testcases")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        # 默认视图不返回 tag 聚合结构
        data = body["data"]
        assert "items" in data

    def test_tag_view_pagination(self):
        """view=tag 支持分页参数"""
        from backend.app import create_app

        app = create_app("testing")
        client = app.test_client()

        resp = client.get("/api/v1/testcases?view=tag&page=1&per_page=5")
        assert resp.status_code == 200
        body = resp.get_json()
        data = body["data"]
        assert data["page"] == 1
        assert data["perPage"] == 5
        assert "pages" in data
        assert "total" in data

    def test_tag_view_filter_params(self):
        """view=tag 支持筛选参数 keyword/type/algorithm_type 透传"""
        from backend.app import create_app

        app = create_app("testing")
        client = app.test_client()

        # 传入筛选参数不应报错
        resp = client.get(
            "/api/v1/testcases?view=tag&keyword=test&type=api&algorithm_type=translation"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        data = body["data"]
        assert "items" in data

    def test_tag_view_case_fields_camel_case(self):
        """view=tag 返回的用例字段使用 camelCase（与 TestCaseListItem 一致）"""
        from backend.app import create_app

        app = create_app("testing")
        client = app.test_client()

        resp = client.get("/api/v1/testcases?view=tag")
        assert resp.status_code == 200
        body = resp.get_json()
        data = body["data"]
        if data["items"]:
            item = data["items"][0]
            if item["testCases"]:
                tc = item["testCases"][0]
                # 关键字段应为 camelCase
                assert "groupId" in tc
                assert "groupName" in tc
                assert "algorithmType" in tc
                assert "createdAt" in tc
                assert "updatedAt" in tc
                assert "totalDuration" in tc
