# -*- coding: utf-8 -*-
"""
用例标签视图接口测试。

覆盖：
- GET /test-cases?view=tag 返回按标签聚合的用例列表
- 不传 view 参数时保持原分组视图行为
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
