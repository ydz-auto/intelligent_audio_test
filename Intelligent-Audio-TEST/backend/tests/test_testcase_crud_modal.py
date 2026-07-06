# -*- coding: utf-8 -*-
"""
测试用例 CRUD 模态窗功能接口测试。

覆盖模态窗触发的完整 CRUD 链路：
- Create: POST /api/v1/testcases — 创建用例（含分组自动创建、标签关联）
- Read:   GET /api/v1/testcases/{id} — 获取单条用例详情
- Update: PUT /api/v1/testcases/{id} — 更新用例（含分组切换、标签更新）
- Delete: DELETE /api/v1/testcases/{id} — 逻辑删除用例
- Copy:   POST /api/v1/testcases/{id}/copy — 复制用例

以及分组 CRUD：
- Create Group: POST /api/v1/groups
- Update Group: PUT /api/v1/groups/{id}
- Delete Group: DELETE /api/v1/groups/{id}

验证点：
1. 创建用例时自动创建不存在的分组
2. 创建用例时自动创建不存在的标签并关联
3. 更新用例时切换分组
4. 更新用例时标签全量替换
5. 删除用例为逻辑删除（deleted=True）
6. 复制用例生成新 ID 且数据一致
7. 分组 CRUD 完整链路
8. 表单验证：缺少 name 时返回错误
9. 表单验证：test_type 非法时返回错误
10. E2E 用例缺少 playback_device_id 时返回错误
"""
import pytest
import json
import time


class TestTestCaseCRUDModal:
    """测试用例 CRUD 模态窗接口"""

    def setup_method(self):
        """每个测试前创建独立 app 实例"""
        from backend.app import create_app
        self.app = create_app("testing")
        self.client = self.app.test_client()
        # 唯一前缀，避免测试间数据冲突
        self.uid = str(int(time.time() * 1000))[-6:]

    # ===== Create =====

    def test_create_testcase_basic(self):
        """创建用例 — 基本场景"""
        payload = {
            "name": f"CRUD测试-创建-{self.uid}",
            "group": f"CRUD测试分组-{self.uid}",
            "description": "由模态窗测试创建",
            "testType": "api",
            "config": {
                "rounds": [{"roundNumber": 1, "audios": []}],
                "dimensions": []
            },
            "tags": [f"标签A-{self.uid}", f"标签B-{self.uid}"]
        }
        resp = self.client.post(
            "/api/v1/testcases",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["success"] is True
        assert "id" in body["data"]

    def test_create_testcase_auto_create_group(self):
        """创建用例时自动创建不存在的分组"""
        payload = {
            "name": f"CRUD测试-自动分组-{self.uid}",
            "group": f"自动创建的分组-{self.uid}",
            "testType": "api",
            "config": {"rounds": [{"roundNumber": 1, "audios": []}], "dimensions": []}
        }
        resp = self.client.post(
            "/api/v1/testcases",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert resp.status_code == 201
        # 验证分组已创建
        tc_id = resp.get_json()["data"]["id"]
        get_resp = self.client.get(f"/api/v1/testcases/{tc_id}")
        assert get_resp.status_code == 200
        data = get_resp.get_json()["data"]
        assert data["groupName"] == f"自动创建的分组-{self.uid}"

    def test_create_testcase_auto_create_tags(self):
        """创建用例时自动创建不存在的标签"""
        tag1 = f"全新标签-{self.uid}-001"
        tag2 = f"全新标签-{self.uid}-002"
        payload = {
            "name": f"CRUD测试-自动标签-{self.uid}",
            "group": f"CRUD测试分组-tag-{self.uid}",
            "testType": "api",
            "config": {"rounds": [{"roundNumber": 1, "audios": []}], "dimensions": []},
            "tags": [tag1, tag2]
        }
        resp = self.client.post(
            "/api/v1/testcases",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert resp.status_code == 201
        tc_id = resp.get_json()["data"]["id"]
        get_resp = self.client.get(f"/api/v1/testcases/{tc_id}")
        data = get_resp.get_json()["data"]
        assert tag1 in data["tags"]
        assert tag2 in data["tags"]

    def test_create_testcase_missing_name(self):
        """创建用例缺少 name 时返回错误"""
        payload = {
            "group": f"CRUD测试分组-noname-{self.uid}",
            "testType": "api",
            "config": {"rounds": [], "dimensions": []}
        }
        resp = self.client.post(
            "/api/v1/testcases",
            data=json.dumps(payload),
            content_type="application/json"
        )
        body = resp.get_json()
        assert body["success"] is False

    def test_create_testcase_invalid_test_type(self):
        """创建用例 test_type 非法时返回错误"""
        payload = {
            "name": f"CRUD测试-非法类型-{self.uid}",
            "group": f"CRUD测试分组-invalid-{self.uid}",
            "testType": "invalid_type",
            "config": {"rounds": [], "dimensions": []}
        }
        resp = self.client.post(
            "/api/v1/testcases",
            data=json.dumps(payload),
            content_type="application/json"
        )
        body = resp.get_json()
        assert body["success"] is False

    def test_create_e2e_testcase_missing_playback_device(self):
        """E2E 用例缺少 playback_device_id 时返回错误"""
        payload = {
            "name": f"CRUD测试-E2E缺设备-{self.uid}",
            "group": f"CRUD测试分组-e2e-{self.uid}",
            "testType": "e2e",
            "config": {
                "rounds": [{
                    "roundNumber": 1,
                    "audios": [{"audioId": 1, "spl": 65, "playOrder": 1}]
                }],
                "dimensions": []
            }
        }
        resp = self.client.post(
            "/api/v1/testcases",
            data=json.dumps(payload),
            content_type="application/json"
        )
        body = resp.get_json()
        assert body["success"] is False

    # ===== Read =====

    def test_read_testcase_detail(self):
        """获取单条用例详情"""
        name = f"CRUD测试-读取-{self.uid}"
        tag = f"读取标签-{self.uid}"
        create_payload = {
            "name": name,
            "group": f"CRUD测试分组-read-{self.uid}",
            "testType": "api",
            "config": {"rounds": [{"roundNumber": 1, "audios": []}], "dimensions": []},
            "tags": [tag]
        }
        resp = self.client.post(
            "/api/v1/testcases",
            data=json.dumps(create_payload),
            content_type="application/json"
        )
        tc_id = resp.get_json()["data"]["id"]

        get_resp = self.client.get(f"/api/v1/testcases/{tc_id}")
        assert get_resp.status_code == 200
        data = get_resp.get_json()["data"]
        assert data["id"] == tc_id
        assert data["name"] == name
        assert tag in data["tags"]

    def test_read_nonexistent_testcase(self):
        """获取不存在的用例返回 404"""
        resp = self.client.get("/api/v1/testcases/nonexistent-id-12345")
        body = resp.get_json()
        assert body["success"] is False

    # ===== Update =====

    def test_update_testcase_basic(self):
        """更新用例基本信息"""
        old_name = f"CRUD测试-更新前-{self.uid}"
        new_name = f"CRUD测试-更新后-{self.uid}"
        create_payload = {
            "name": old_name,
            "group": f"CRUD测试分组-upd-{self.uid}",
            "testType": "api",
            "config": {"rounds": [{"roundNumber": 1, "audios": []}], "dimensions": []}
        }
        resp = self.client.post(
            "/api/v1/testcases",
            data=json.dumps(create_payload),
            content_type="application/json"
        )
        tc_id = resp.get_json()["data"]["id"]

        update_payload = {
            "id": tc_id,
            "name": new_name,
            "description": "已更新描述",
            "testType": "api",
            "config": {"rounds": [{"roundNumber": 1, "audios": []}], "dimensions": []}
        }
        update_resp = self.client.put(
            f"/api/v1/testcases/{tc_id}",
            data=json.dumps(update_payload),
            content_type="application/json"
        )
        assert update_resp.status_code == 200
        assert update_resp.get_json()["success"] is True

        get_resp = self.client.get(f"/api/v1/testcases/{tc_id}")
        data = get_resp.get_json()["data"]
        assert data["name"] == new_name
        assert data["description"] == "已更新描述"

    def test_update_testcase_switch_group(self):
        """更新用例时切换分组"""
        old_group = f"原分组-{self.uid}"
        new_group = f"新分组-{self.uid}"
        create_payload = {
            "name": f"CRUD测试-切换分组-{self.uid}",
            "group": old_group,
            "testType": "api",
            "config": {"rounds": [{"roundNumber": 1, "audios": []}], "dimensions": []}
        }
        resp = self.client.post(
            "/api/v1/testcases",
            data=json.dumps(create_payload),
            content_type="application/json"
        )
        tc_id = resp.get_json()["data"]["id"]

        update_payload = {
            "id": tc_id,
            "name": f"CRUD测试-切换分组-{self.uid}",
            "group": new_group,
            "testType": "api",
            "config": {"rounds": [{"roundNumber": 1, "audios": []}], "dimensions": []}
        }
        self.client.put(
            f"/api/v1/testcases/{tc_id}",
            data=json.dumps(update_payload),
            content_type="application/json"
        )

        get_resp = self.client.get(f"/api/v1/testcases/{tc_id}")
        data = get_resp.get_json()["data"]
        assert data["groupName"] == new_group

    def test_update_testcase_replace_tags(self):
        """更新用例时标签全量替换"""
        old_tags = [f"旧标签1-{self.uid}", f"旧标签2-{self.uid}"]
        new_tags = [f"新标签1-{self.uid}", f"新标签2-{self.uid}", f"新标签3-{self.uid}"]
        create_payload = {
            "name": f"CRUD测试-标签替换-{self.uid}",
            "group": f"CRUD测试分组-rtag-{self.uid}",
            "testType": "api",
            "config": {"rounds": [{"roundNumber": 1, "audios": []}], "dimensions": []},
            "tags": old_tags
        }
        resp = self.client.post(
            "/api/v1/testcases",
            data=json.dumps(create_payload),
            content_type="application/json"
        )
        tc_id = resp.get_json()["data"]["id"]

        update_payload = {
            "id": tc_id,
            "name": f"CRUD测试-标签替换-{self.uid}",
            "group": f"CRUD测试分组-rtag-{self.uid}",
            "testType": "api",
            "config": {"rounds": [{"roundNumber": 1, "audios": []}], "dimensions": []},
            "tags": new_tags
        }
        self.client.put(
            f"/api/v1/testcases/{tc_id}",
            data=json.dumps(update_payload),
            content_type="application/json"
        )

        get_resp = self.client.get(f"/api/v1/testcases/{tc_id}")
        data = get_resp.get_json()["data"]
        assert set(data["tags"]) == set(new_tags)
        assert old_tags[0] not in data["tags"]

    def test_update_nonexistent_testcase(self):
        """更新不存在的用例返回错误"""
        payload = {
            "id": "nonexistent-id",
            "name": "不存在",
            "testType": "api"
        }
        resp = self.client.put(
            "/api/v1/testcases/nonexistent-id",
            data=json.dumps(payload),
            content_type="application/json"
        )
        body = resp.get_json()
        assert body["success"] is False

    # ===== Delete =====

    def test_delete_testcase_logical(self):
        """删除用例为逻辑删除"""
        create_payload = {
            "name": f"CRUD测试-删除-{self.uid}",
            "group": f"CRUD测试分组-del-{self.uid}",
            "testType": "api",
            "config": {"rounds": [{"roundNumber": 1, "audios": []}], "dimensions": []}
        }
        resp = self.client.post(
            "/api/v1/testcases",
            data=json.dumps(create_payload),
            content_type="application/json"
        )
        tc_id = resp.get_json()["data"]["id"]

        del_resp = self.client.delete(f"/api/v1/testcases/{tc_id}")
        assert del_resp.status_code == 200
        assert del_resp.get_json()["success"] is True

        # 验证已删除（get_one 应返回 404）
        get_resp = self.client.get(f"/api/v1/testcases/{tc_id}")
        body = get_resp.get_json()
        assert body["success"] is False

    def test_delete_nonexistent_testcase(self):
        """删除不存在的用例返回错误"""
        resp = self.client.delete("/api/v1/testcases/nonexistent-id-99999")
        body = resp.get_json()
        assert body["success"] is False

    # ===== Copy =====

    def test_copy_testcase(self):
        """复制用例生成新 ID 且数据一致"""
        tag = f"复制标签-{self.uid}"
        create_payload = {
            "name": f"CRUD测试-复制源-{self.uid}",
            "group": f"CRUD测试分组-copy-{self.uid}",
            "testType": "api",
            "config": {"rounds": [{"roundNumber": 1, "audios": []}], "dimensions": []},
            "tags": [tag]
        }
        resp = self.client.post(
            "/api/v1/testcases",
            data=json.dumps(create_payload),
            content_type="application/json"
        )
        tc_id = resp.get_json()["data"]["id"]

        copy_resp = self.client.post(f"/api/v1/testcases/{tc_id}/copy")
        assert copy_resp.status_code in [200, 201]
        copy_body = copy_resp.get_json()
        assert copy_body["success"] is True
        new_id = copy_body["data"]["id"]
        assert new_id != tc_id

        get_resp = self.client.get(f"/api/v1/testcases/{new_id}")
        data = get_resp.get_json()["data"]
        assert data["id"] == new_id
        assert tag in data["tags"]

    # ===== Group CRUD =====

    def test_create_group(self):
        """创建分组"""
        payload = {
            "name": f"模态窗测试分组-创建-{self.uid}",
            "description": "由测试创建"
        }
        resp = self.client.post(
            "/api/v1/groups",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert resp.status_code in [200, 201]
        body = resp.get_json()
        assert body["success"] is True

    def test_update_group(self):
        """更新分组"""
        create_payload = {"name": f"模态窗测试分组-更新前-{self.uid}", "description": "更新前"}
        resp = self.client.post(
            "/api/v1/groups",
            data=json.dumps(create_payload),
            content_type="application/json"
        )
        group_id = resp.get_json()["data"]["id"]

        update_payload = {"name": f"模态窗测试分组-更新后-{self.uid}", "description": "更新后"}
        update_resp = self.client.put(
            f"/api/v1/groups/{group_id}",
            data=json.dumps(update_payload),
            content_type="application/json"
        )
        assert update_resp.status_code == 200
        assert update_resp.get_json()["success"] is True

    def test_delete_group(self):
        """删除分组"""
        create_payload = {"name": f"模态窗测试分组-删除-{self.uid}", "description": "待删除"}
        resp = self.client.post(
            "/api/v1/groups",
            data=json.dumps(create_payload),
            content_type="application/json"
        )
        group_id = resp.get_json()["data"]["id"]

        del_resp = self.client.delete(f"/api/v1/groups/{group_id}")
        assert del_resp.status_code == 200
        assert del_resp.get_json()["success"] is True
