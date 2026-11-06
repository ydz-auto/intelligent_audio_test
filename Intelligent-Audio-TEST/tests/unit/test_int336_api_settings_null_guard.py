# -*- coding: utf-8 -*-
"""INT-336 守卫：维度 api_settings 显式 null（JSON null → None）时不抛 NoneType。

_get_timeout_from_dim_config / _execute_evaluation 的 api_settings 读取
必须同时兜住「键缺失」与「显式 null」两种形态；既有默认超时语义不变
（普通 default_timeout=30 / llm_judge 120 / 维度配置 timeout 优先）。

纯单测：WorkerManagementMixin 最小宿主，不触 DB/gRPC/线程池。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from evaluation_service.infrastructure.evaluation_api.worker_management import (
    WorkerManagementMixin,
)


class _Host(WorkerManagementMixin):
    """最小宿主：仅真实 _get_timeout_from_dim_config，跳过 __init__ 组合。"""

    def __init__(self, endpoint_workers=None):
        self.endpoint_workers = endpoint_workers or {}

    def _log(self, **kwargs):
        pass


def test_api_settings_none_falls_back_to_default_timeout():
    """api_settings=None（JSON null）→ 不抛 NoneType，走 default_timeout=30"""
    host = _Host()
    dim = {'id': 1, 'dimension_type': 'main', 'api_settings': None,
           'api_endpoints': [], 'api_url': None}
    assert host._get_timeout_from_dim_config(dim) == 30


def test_api_settings_missing_key_falls_back_to_default_timeout():
    """api_settings 键缺失 → 不抛异常，走 default_timeout=30（既有语义）"""
    host = _Host()
    dim = {'id': 1, 'dimension_type': 'main', 'api_endpoints': [], 'api_url': None}
    assert host._get_timeout_from_dim_config(dim) == 30


def test_api_settings_normal_dict_timeout_wins():
    """api_settings 正常 dict 且带 timeout → 取维度配置值"""
    host = _Host()
    dim = {'id': 1, 'dimension_type': 'main',
           'api_settings': {'method': 'POST', 'timeout': 90}}
    assert host._get_timeout_from_dim_config(dim) == 90


def test_llm_judge_api_settings_none_uses_120_default():
    """llm_judge 分支：api_settings=None → 不抛 NoneType，默认 120 秒语义不变"""
    host = _Host()
    dim = {'id': 1, 'dimension_type': 'llm_judge', 'api_settings': None}
    assert host._get_timeout_from_dim_config(dim) == 120


def test_llm_judge_api_settings_missing_key_uses_120_default():
    """llm_judge 分支：api_settings 键缺失 → 默认 120 秒语义不变"""
    host = _Host()
    dim = {'id': 1, 'dimension_type': 'llm_judge'}
    assert host._get_timeout_from_dim_config(dim) == 120


def test_llm_judge_api_settings_timeout_configured():
    """llm_judge 分支：正常 dict 带 timeout → 取维度配置值"""
    host = _Host()
    dim = {'id': 1, 'dimension_type': 'llm_judge',
           'api_settings': {'timeout': 30000}}
    assert host._get_timeout_from_dim_config(dim) == 30000


def test_none_api_settings_still_falls_through_to_endpoint_timeout():
    """api_settings=None 时超时兜底链不变：endpoint max_timeout 优先于 default"""
    host = _Host()
    dim = {'id': 1, 'dimension_type': 'main', 'api_settings': None,
           'api_endpoints': [{'url': 'http://eval:8888', 'max_timeout': 60}],
           'api_url': None}
    assert host._get_timeout_from_dim_config(dim) == 60


def test_none_api_settings_falls_back_to_precreated_worker_timeout():
    """api_settings=None 且无 endpoint 配置 → 兜底链含已预建 worker.max_timeout"""
    class _W:
        max_timeout = 45

    host = _Host(endpoint_workers={'http://eval:8888': _W()})
    dim = {'id': 1, 'dimension_type': 'main', 'api_settings': None,
           'api_endpoints': [], 'api_url': 'http://eval:8888'}
    assert host._get_timeout_from_dim_config(dim) == 45


def test_none_timeout_value_in_dict_treated_as_unconfigured():
    """api_settings={'timeout': None}（键在但值为 null）→ 与缺失同语义，走兜底链"""
    host = _Host()
    dim = {'id': 1, 'dimension_type': 'main',
           'api_settings': {'method': 'POST', 'timeout': None},
           'api_endpoints': [], 'api_url': None}
    assert host._get_timeout_from_dim_config(dim) == 30
