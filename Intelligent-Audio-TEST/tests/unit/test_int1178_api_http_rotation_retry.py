# -*- coding: utf-8 -*-
"""INT-1178 密钥池 HTTP 内嵌路径：失败降级重试 + 轮换生效单测。

设计依据：INT-1173 密钥池父卡（endpoint 级挂载，api_endpoints[].api_keys）、
INT-1177 阶段A（resolve_rotating 按端点池 + RotationStateStore 端点 keying +
_merge_headers 按当前端点池注入轮换 key）、INT-1178 阶段B（适配器内
api_client.call 重试：401/403/429 切下一非冷却 key；重试上限 = 当前端点池
key 数；池全冷却立即失败不空转；5xx/网络错误不轮换；无池退化单次调用）。

执行器层不感知轮换（Domain 层只见解析结果）——重试完全封闭在 ApiDriverAdapter
内部，覆盖 execute（body_template 渲染路径）与 execute_voice_llm_chat
（INT-1169/1176 迁移后的内嵌 execute 路径）两条 HTTP 调用面。
"""
import os
import tempfile
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + tempfile.mkdtemp(prefix='int1178_') + '/chain.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import shared.utils.api_key_provider as akp
from api_test_service.infrastructure.adapters import api_driver_adapter as ada_mod
from api_test_service.infrastructure.adapters.api_driver_adapter import (
    ApiDriverAdapter,
)


@pytest.fixture(autouse=True)
def _isolate_rotation_state(monkeypatch):
    """隔离轮换状态（每用例独立游标/冷却），并把适配器解析器绑定到新单例。

    ApiDriverAdapter 的模块级 `_key_resolver` 在导入期绑定构造时的单例；替换
    模块全局 `_rotation_store` 后需重建解析器，否则 adapter 侧仍写旧 store。
    """
    fresh_store = akp.InMemoryRotationStateStore()
    monkeypatch.setattr(akp, '_rotation_store', fresh_store)
    fresh_resolver = akp.resolver_from_config(
        lambda section, key, default=None: default)
    monkeypatch.setattr(ada_mod, '_key_resolver', fresh_resolver)
    return fresh_store


def _resp(status_code=200, error=None):
    return {'status_code': status_code, 'latency': 5, 'raw_response': '',
            'json': {}, 'error': error}


def _driver(api_id=41, endpoint='https://ep.example.com/api/create_task',
            keys=None, meta=None, case_cfg=None):
    """ApiDriverAdapter：self.endpoint 含 path，_current_endpoint base 前缀
    匹配回 api_endpoints；keys 挂在 ep 池，ep2 池固定 ['sk-x1','sk-x2']。"""
    api_config = SimpleNamespace(
        id=api_id, meta=meta or {}, max_timeout=30, endpoint=endpoint,
        api_endpoints=[
            {'endpoint': 'https://ep.example.com',
             'api_keys': list(keys or [])},
            {'endpoint': 'https://ep2.example.com',
             'api_keys': ['sk-x1', 'sk-x2']},
        ],
    )
    return ApiDriverAdapter(api_config, case_config=case_cfg or {})


# ── execute（body_template 渲染路径）：失败降级重试 ──────────────

def test_execute_401_switches_key_then_succeeds():
    """mock 401 → 自动切下一非冷却 key；第二次 200 成功。"""
    driver = _driver(keys=['sk-a1', 'sk-b2'])
    calls = []

    def _fake_call(**kwargs):
        calls.append(kwargs)
        return _resp(401) if len(calls) == 1 else _resp(200)

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        result = driver.execute({'case_name': 'c1'})

    assert len(calls) == 2
    assert calls[0]['headers']['Authorization'] == 'Bearer sk-a1'
    assert calls[1]['headers']['Authorization'] == 'Bearer sk-b2'
    assert result['success'] is True


def test_execute_403_switches_key_then_succeeds():
    """403 同样触发轮换（白名单 401/403/429）。"""
    driver = _driver(keys=['sk-a1', 'sk-b2'])
    calls = []

    def _fake_call(**kwargs):
        calls.append(kwargs)
        return _resp(403) if len(calls) == 1 else _resp(200)

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        result = driver.execute({'case_name': 'c1'})

    assert len(calls) == 2
    assert calls[1]['headers']['Authorization'] == 'Bearer sk-b2'
    assert result['success'] is True


def test_execute_429_switches_key_then_succeeds():
    """429 限流同样触发轮换。"""
    driver = _driver(keys=['sk-a1', 'sk-b2'])
    calls = []

    def _fake_call(**kwargs):
        calls.append(kwargs)
        return _resp(429) if len(calls) == 1 else _resp(200)

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        result = driver.execute({'case_name': 'c1'})

    assert len(calls) == 2
    assert calls[1]['headers']['Authorization'] == 'Bearer sk-b2'
    assert result['success'] is True


def test_execute_all_keys_failed_returns_last_error_no_spin():
    """池内每 key 都 401：重试上限 = 池 key 数（2 次），全失败返回最后错误；
    池全冷却后立即失败（不空转等待、不再发请求）。"""
    driver = _driver(keys=['sk-a1', 'sk-b2'])
    calls = []

    def _fake_call(**kwargs):
        calls.append(kwargs)
        return _resp(401)

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        result = driver.execute({'case_name': 'c1'})

    assert len(calls) == 2  # 上限 = 池 key 数，无多余请求
    assert result['success'] is False
    assert result['status_code'] == 401
    assert calls[0]['headers']['Authorization'] == 'Bearer sk-a1'
    assert calls[1]['headers']['Authorization'] == 'Bearer sk-b2'


def test_execute_pool_all_cooled_fails_immediately():
    """池全冷却立即失败：解析不到 key（无 Authorization 注入），单次请求即
    失败，不空转等待冷却。"""
    driver = _driver(keys=['sk-a1', 'sk-b2'])
    rk = akp.endpoint_rotation_key(41, 'https://ep.example.com')
    akp.get_rotation_store().mark_failure(rk, 'sk-a1', 60)
    akp.get_rotation_store().mark_failure(rk, 'sk-b2', 60)
    calls = []

    def _fake_call(**kwargs):
        calls.append(kwargs)
        return _resp(401)

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        result = driver.execute({'case_name': 'c1'})

    assert len(calls) == 1
    assert 'Authorization' not in calls[0]['headers']
    assert result['success'] is False


def test_execute_5xx_no_rotation():
    """5xx 明确不轮换：单次失败即返回，不发下一 key 请求。"""
    driver = _driver(keys=['sk-a1', 'sk-b2'])
    calls = []

    def _fake_call(**kwargs):
        calls.append(kwargs)
        return _resp(500)

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        result = driver.execute({'case_name': 'c1'})

    assert len(calls) == 1
    assert result['status_code'] == 500
    assert calls[0]['headers']['Authorization'] == 'Bearer sk-a1'


def test_execute_network_error_no_rotation():
    """网络错误（status_code 0 / error 非空）明确不轮换。"""
    driver = _driver(keys=['sk-a1', 'sk-b2'])
    calls = []

    def _fake_call(**kwargs):
        calls.append(kwargs)
        return _resp(0, error='connection refused')

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        result = driver.execute({'case_name': 'c1'})

    assert len(calls) == 1
    assert result['success'] is False
    assert result['error'] == 'connection refused'


def test_execute_no_pool_single_value_no_retry():
    """未配置 api_keys（无池）→ 回退单值，401 不轮换，行为与迁移前一致。"""
    driver = _driver(meta={'api_key': 'sk-meta'}, keys=[])
    calls = []

    def _fake_call(**kwargs):
        calls.append(kwargs)
        return _resp(401)

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        result = driver.execute({'case_name': 'c1'})

    assert len(calls) == 1
    assert calls[0]['headers']['Authorization'] == 'Bearer sk-meta'
    assert result['success'] is False


def test_case_level_key_no_rotation():
    """case 层单值最高优先（现状不变）：配置池也不轮换，401 单次失败。"""
    driver = _driver(keys=['sk-a1', 'sk-b2'], case_cfg={'api_key': 'sk-case'})
    calls = []

    def _fake_call(**kwargs):
        calls.append(kwargs)
        return _resp(401)

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        result = driver.execute({'case_name': 'c1'})

    assert len(calls) == 1
    assert calls[0]['headers']['Authorization'] == 'Bearer sk-case'
    assert result['success'] is False


# ── execute：轮换生效（round-robin）与多端点隔离 ─────────────────

def test_execute_round_robin_hits_each_key():
    """连续成功请求按当前端点池轮换：两次调用命中 sk-a1 / sk-b2。"""
    driver = _driver(keys=['sk-a1', 'sk-b2'])
    seen = []

    def _fake_call(**kwargs):
        seen.append(kwargs['headers'].get('Authorization'))
        return _resp(200)

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        driver.execute({'case_name': 'c1'})
        driver.execute({'case_name': 'c2'})

    assert seen == ['Bearer sk-a1', 'Bearer sk-b2']


def test_execute_different_endpoints_separate_pools():
    """多端点各用各池：self.endpoint 匹配 ep2 → 用 ep2 池（sk-x1/sk-x2），
    ep 池不串。"""
    driver = _driver(api_id=42,
                     endpoint='https://ep2.example.com/api/create_task',
                     keys=['sk-a1', 'sk-a2'])
    seen = []

    def _fake_call(**kwargs):
        seen.append(kwargs['headers'].get('Authorization'))
        return _resp(200)

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        driver.execute({'case_name': 'c1'})
        driver.execute({'case_name': 'c2'})

    assert seen == ['Bearer sk-x1', 'Bearer sk-x2']


def test_failed_key_enters_cooldown_and_not_reselected():
    """失败 key 置冷却：冷却期内后续解析不选中（直接命中下一 key）。"""
    driver = _driver(keys=['sk-a1', 'sk-b2', 'sk-c3'])
    calls = []

    def _fake_call(**kwargs):
        calls.append(kwargs)
        return _resp(401) if len(calls) == 1 else _resp(200)

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        result = driver.execute({'case_name': 'c1'})

    assert calls[0]['headers']['Authorization'] == 'Bearer sk-a1'
    assert calls[1]['headers']['Authorization'] == 'Bearer sk-b2'
    assert result['success'] is True
    # 冷却期内的下一次解析跳过 sk-a1（sk-c3 命中）
    h, _ = driver.render_request_parts({})
    assert h['Authorization'] in ('Bearer sk-b2', 'Bearer sk-c3')


# ── execute_voice_llm_chat（迁移后的内嵌 execute 路径）──────────

def test_voice_llm_chat_401_retries_next_key():
    """内嵌 execute 路径：401 → 切下一 key 重试成功，X-Session-Id 等其余头
    重试时保留。"""
    driver = _driver(keys=['sk-a1', 'sk-b2'])
    calls = []

    def _fake_call(**kwargs):
        calls.append(kwargs)
        return _resp(401) if len(calls) == 1 else _resp(200)

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        result = driver.execute_voice_llm_chat(
            session_id='s-1', input_type='text', input_data='hi',
            round_number=1, total_rounds=1, timeout=5)

    assert len(calls) == 2
    assert calls[0]['headers']['Authorization'] == 'Bearer sk-a1'
    assert calls[0]['headers']['X-Session-Id'] == 's-1'
    assert calls[1]['headers']['Authorization'] == 'Bearer sk-b2'
    assert calls[1]['headers']['X-Session-Id'] == 's-1'
    assert result['success'] is True


def test_voice_llm_chat_round_robin_one_key_per_round():
    """内嵌路径每轮只消费一个 key（render_request_parts + execute_voice_llm_chat
    不双推进游标）：连续两轮命中 sk-a1 / sk-b2。"""
    driver = _driver(keys=['sk-a1', 'sk-b2'])
    seen = []

    def _fake_call(**kwargs):
        seen.append(kwargs['headers'].get('Authorization'))
        return _resp(200)

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        driver.execute_voice_llm_chat(
            session_id='s-1', input_type='text', input_data='hi',
            round_number=1, total_rounds=2, timeout=5)
        driver.execute_voice_llm_chat(
            session_id='s-2', input_type='text', input_data='hi',
            round_number=2, total_rounds=2, timeout=5)

    assert seen == ['Bearer sk-a1', 'Bearer sk-b2']


def test_voice_llm_chat_all_keys_failed_returns_last_error():
    """内嵌路径全失败：重试上限 = 池 key 数，返回最后错误，不空转。"""
    driver = _driver(keys=['sk-a1', 'sk-b2'])
    calls = []

    def _fake_call(**kwargs):
        calls.append(kwargs)
        return _resp(403)

    with mock.patch.object(ada_mod.api_client, 'call', side_effect=_fake_call):
        result = driver.execute_voice_llm_chat(
            session_id='s-1', input_type='text', input_data='hi',
            round_number=1, total_rounds=1, timeout=5)

    assert len(calls) == 2
    assert result['success'] is False
    assert result['status_code'] == 403
