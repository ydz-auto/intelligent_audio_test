# -*- coding: utf-8 -*-
"""核心 REST API 联调测试 — INT-7。

使用 pytest + httpx 对 api_gateway 路由做接口测试。
后端未运行时自动 skip（通过 conftest.require_backend fixture）。
每个资源至少覆盖 happy path 和一个异常路径。

数据卫生（INT-229 验收补漏）：写入型用例数据携带进程级唯一前缀
`_test_{_RUN}_`，模块级 teardown 按前缀硬删残留（tag_categories 的
DELETE 为软删，直接跑会留残留），口径同 INT-218 / INT-229。
"""
import os
import secrets

import pytest
from tests.api.conftest import API_BASE, PROJECT_ROOT

# 进程级唯一前缀段：xdist 各进程独立取值，teardown 按前缀硬删不会误删
# 并发运行的其它数据。
_RUN = secrets.token_hex(4)

# 本文件写入型用例触达的表（tag_categories 的 DELETE 为软删）。
_PURGE_TABLES = [
    ('tag_categories', 'name'),
]


def _database_url() -> str:
    """实机栈 .env 的 DATABASE_URL（缺省回退本地默认值）。"""
    try:
        with open(os.path.join(PROJECT_ROOT, '.env'), encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('DATABASE_URL='):
                    return line.split('=', 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return ('postgresql://intelligent_audio_test:intelligent_audio_test666'
            '@localhost:5432/intelligent_audio_test')


def _purge_run_rows() -> None:
    """按进程级唯一前缀硬删本文件全部残留行，库中不留本文件测试数据。"""
    import sqlalchemy
    from sqlalchemy import text
    eng = sqlalchemy.create_engine(_database_url(),
                                   connect_args={'connect_timeout': 5})
    pattern = rf'\_test\_{_RUN}\_%'
    with eng.begin() as conn:
        for table, col in _PURGE_TABLES:
            conn.execute(text(f'DELETE FROM {table} WHERE {col} LIKE :p'),
                         {'p': pattern})


@pytest.fixture(scope='module', autouse=True)
def _purge_after_module():
    """模块结束（含用例中途失败）按唯一前缀硬删本文件全部测试数据。"""
    yield
    _purge_run_rows()


# ── 辅助 ──────────────────────────────────────────────────
def _unwrap(resp):
    """解包 {code, data, message, success} 信封，返回 data。"""
    body = resp.json()
    assert body.get('code') in (0, 200, 201) or body.get('success') is True, \
        f'API 返回失败: {resp.status_code} {body}'
    return body.get('data')


# ── Tags ──────────────────────────────────────────────────
class TestTags:
    """标签 CRUD 联调。"""

    def test_tag_category_crud(self, api_client):
        # Create
        resp = api_client.post('/tags/categories', json={'name': f'_test_{_RUN}_category', 'description': 'test'})
        data = _unwrap(resp)
        cat_id = data.get('id')
        assert cat_id is not None

        # Read
        resp = api_client.get(f'/tags/categories/{cat_id}')
        data = _unwrap(resp)
        assert data.get('name') == f'_test_{_RUN}_category'

        # List
        resp = api_client.get('/tags/categories')
        data = _unwrap(resp)
        assert isinstance(data.get('items'), list)

        # Update
        resp = api_client.put(f'/tags/categories/{cat_id}', json={'name': f'_test_{_RUN}_cat_updated'})
        data = _unwrap(resp)
        assert data.get('name') == f'_test_{_RUN}_cat_updated'

        # Delete
        resp = api_client.delete(f'/tags/categories/{cat_id}')
        _unwrap(resp)

    def test_tag_category_not_found(self, api_client):
        resp = api_client.get('/tags/categories/999999')
        body = resp.json()
        assert body.get('code') != 0 or resp.status_code >= 400


# ── Devices ───────────────────────────────────────────────
class TestDevices:
    """设备管理联调。"""

    def test_list_devices(self, api_client):
        resp = api_client.get('/test-devices', params={'page': 1, 'per_page': 10})
        data = _unwrap(resp)
        assert isinstance(data.get('items'), list)

    def test_device_not_found(self, api_client):
        resp = api_client.get('/test-devices/999999')
        body = resp.json()
        assert body.get('code') != 0 or resp.status_code >= 400

    def test_scan_devices(self, api_client):
        resp = api_client.post('/test-devices/scan')
        data = _unwrap(resp)
        assert isinstance(data, list)

    def test_driver_keywords(self, api_client):
        resp = api_client.get('/test-devices/driver-keywords')
        _unwrap(resp)


# ── Test Cases ───────────────────────────────────────────
class TestTestCases:
    """测试用例联调。"""

    def test_list_testcases(self, api_client):
        resp = api_client.get('/testcases', params={'page': 1, 'per_page': 10})
        data = _unwrap(resp)
        assert isinstance(data.get('items'), list)

    def test_testcase_not_found(self, api_client):
        resp = api_client.get('/testcases/999999')
        body = resp.json()
        assert body.get('code') != 0 or resp.status_code >= 400

    def test_testcase_stats(self, api_client):
        resp = api_client.get('/testcases/stats')
        _unwrap(resp)


# ── Tasks ────────────────────────────────────────────────
class TestTasks:
    """任务管理联调。"""

    def test_list_tasks(self, api_client):
        resp = api_client.get('/tasks', params={'page': 1, 'per_page': 10})
        data = _unwrap(resp)
        assert isinstance(data.get('items'), list)

    def test_task_not_found(self, api_client):
        resp = api_client.get('/tasks/999999')
        body = resp.json()
        assert body.get('code') != 0 or resp.status_code >= 400


# ── Algorithm ───────────────────────────────────────────
class TestAlgorithm:
    """算法配置联调。"""

    def test_list_algorithms(self, api_client):
        resp = api_client.get('/algorithm/definitions')
        data = _unwrap(resp)
        # 算法定义列表契约: data 为 {data: [...], total: N}（前端 useAlgorithmConfig 依赖 data.data）
        assert isinstance(data.get('data'), list) or isinstance(data.get('items'), list) or isinstance(data, list)

    def test_list_groups(self, api_client):
        resp = api_client.get('/algorithm/groups')
        _unwrap(resp)


# ── Evaluation ────────────────────────────────────────────
class TestEvaluation:
    """评估维度联调。"""

    def test_list_dimensions(self, api_client):
        resp = api_client.get('/evaluation/dimensions')
        _unwrap(resp)

    def test_dimension_options(self, api_client):
        resp = api_client.get('/evaluation/dimensions/options')
        _unwrap(resp)

    def test_list_categories(self, api_client):
        resp = api_client.get('/evaluation/categories')
        _unwrap(resp)


# ── SPL ──────────────────────────────────────────────────
class TestSPL:
    """SPL 映射联调。"""

    def test_list_spl_mappings(self, api_client):
        resp = api_client.get('/spl', params={'page': 1, 'per_page': 10})
        _unwrap(resp)

    def test_spl_not_found(self, api_client):
        resp = api_client.get('/spl/999999')
        body = resp.json()
        assert body.get('code') != 0 or resp.status_code >= 400


# ── Playback Devices ────────────────────────────────────
class TestPlaybackDevices:
    """播放设备联调。"""

    def test_list_playback_devices(self, api_client):
        resp = api_client.get('/playback-devices', params={'page': 1, 'per_page': 10})
        _unwrap(resp)


# ── Home / Stats ────────────────────────────────────────
class TestHome:
    """首页统计联调。"""

    def test_stats_summary(self, api_client):
        resp = api_client.get('/home/stats/summary')
        _unwrap(resp)

    def test_stats_details(self, api_client):
        resp = api_client.get('/home/stats/details')
        _unwrap(resp)


# ── Logs ────────────────────────────────────────────────
class TestLogs:
    """日志查询联调。"""

    def test_list_logs(self, api_client):
        resp = api_client.get('/logs', params={'page': 1, 'per_page': 10})
        _unwrap(resp)

    def test_log_stats(self, api_client):
        resp = api_client.get('/logs/stats')
        _unwrap(resp)


# ── Groups ──────────────────────────────────────────────
class TestGroups:
    """测试用例分组联调。"""

    def test_list_groups(self, api_client):
        resp = api_client.get('/groups')
        _unwrap(resp)


# ── APIs (被测 API 配置) ────────────────────────────────
class TestApiConfigs:
    """被测 API 配置联调。"""

    def test_list_apis(self, api_client):
        resp = api_client.get('/apis', params={'page': 1, 'per_page': 10})
        _unwrap(resp)

    def test_api_not_found(self, api_client):
        resp = api_client.get('/apis/999999')
        body = resp.json()
        assert body.get('code') != 0 or resp.status_code >= 400
