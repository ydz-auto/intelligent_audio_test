# -*- coding: utf-8 -*-
"""INT-1772 API 响应解析预览端点单测。

卡面验收：
1. ``result_parser`` 指向 ``a.b[0].c``、样例响应嵌套数组 → 返回正确值；
2. 解析不到的路径进 ``unresolved``，接口 200 不报错；
3. 空请求体 / 非法 JSON → 400（派发补充：非法 path 同样 400 且报错可读）；
4. 缺 ``api_config:read`` → 403。

外加口径断言：路径提取与执行期同源（``extract_by_path``），文本/结束标志
映射在 ``resp['data']`` 解包后取值、错误码映射在完整响应上取值
（``api_driver_adapter._parse_response``）。
"""
import os

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.utils.path_extractor import is_valid_path  # noqa: E402
from api_gateway.application.services.api.parse_preview import (  # noqa: E402
    ParsePreviewError,
    build_preview,
)

NESTED_RAW = {
    'a': {
        'b': [
            {'c': 'zero'},
            {'c': 'one'},
        ],
    },
    'code': 0,
    'msg': 'ok',
}


def _preview(**kwargs):
    payload = {'sample_response': NESTED_RAW}
    payload.update(kwargs)
    return build_preview(payload)


# ──────────────────── 验收 1：[n] 下标与嵌套取值 ────────────────────

def test_result_parser_bracket_index_nested_array():
    """验收 1：result_parser 指向 a.b[0].c，样例响应嵌套数组 → 正确值"""
    out = _preview(result_parser={'asr_text_path': 'a.b[0].c'})
    assert out['extracted'] == {'asr_text_path': 'zero'}
    assert out['unresolved'] == []
    # 越界下标换一个值，证明确实按数组下标取
    out = _preview(result_parser={'asr_text_path': 'a.b[1].c'})
    assert out['extracted'] == {'asr_text_path': 'one'}


def test_result_parser_dot_index_equivalent():
    """点号数字下标与方括号等价（与执行期 extract_by_path 同一份实现）"""
    out = _preview(result_parser={'asr_text_path': 'a.b.0.c'})
    assert out['extracted'] == {'asr_text_path': 'zero'}


def test_result_parser_all_execution_keys():
    """voice_llm 三个解析键原样回显（键名 = result_parser 内部键）"""
    sample = {'result': {'asr_text': '你好', 'trans_text': 'hello',
                         'session_id': 's-1'}}
    out = build_preview({
        'sample_response': sample,
        'result_parser': {
            'asr_text_path': 'result.asr_text',
            'trans_text_path': 'result.trans_text',
            'session_id_path': 'result.session_id',
        },
    })
    assert out['extracted'] == {
        'asr_text_path': '你好',
        'trans_text_path': 'hello',
        'session_id_path': 's-1',
    }


# ──────────────────── 验收 2：解析不到 → unresolved ────────────────────

def test_unresolved_paths_reported_not_dropped():
    """验收 2：解析不到的路径进 unresolved，其余正常提取，不报错"""
    out = _preview(
        result_parser={'asr_text_path': 'a.b[9].c'},   # 下标越界
        asr_mapping='a.missing.text',                  # 键不存在
        trans_mapping='a.b.0.c',                       # 命中
    )
    assert out['extracted'] == {'trans_mapping': 'zero'}
    assert out['unresolved'] == ['a.b[9].c', 'a.missing.text']


def test_unresolved_dedup_and_order():
    """同一路径多次未命中只记一条，按配置顺序保序"""
    out = _preview(
        result_parser={'asr_text_path': 'nope', 'trans_text_path': 'nope'},
        asr_mapping='nope',
        trans_mapping='other',
    )
    assert out['unresolved'] == ['nope', 'other']


def test_empty_path_means_not_configured():
    """空串/None 路径 = 未配置：不提取、也不进 unresolved"""
    out = _preview(
        result_parser={'asr_text_path': '', 'trans_text_path': None},
        asr_mapping='',
        error_code_mapping=None,
    )
    assert out == {'extracted': {}, 'unresolved': []}


def test_raw_text_sample_all_unresolved():
    """原始文本样例：没有可提取结构 → 全部进 unresolved，不报错"""
    out = build_preview({
        'sample_response': 'not a json body',
        'asr_mapping': 'asr_result',
    })
    assert out['extracted'] == {}
    assert out['unresolved'] == ['asr_result']


def test_json_text_sample_is_parsed():
    """字符串形式的 JSON 样例先解析再提取"""
    out = build_preview({
        'sample_response': '{"data": {"text": "hi"}}',
        'asr_mapping': 'text',
    })
    assert out['extracted'] == {'asr_mapping': 'hi'}


# ──────────────── 执行期口径：data 解包 / 错误码取全量 ────────────────

def test_text_mapping_unwraps_data_envelope_like_executor():
    """asr/trans/结束标志映射与 _parse_response 同口径：先解包 .data"""
    sample = {'code': 0, 'msg': 'ok',
              'data': {'asr_result': 'hi', 'is_sentence_end': True}}
    out = build_preview({
        'sample_response': sample,
        'asr_mapping': 'asr_result',
        'sentence_end_mapping': 'is_sentence_end',
    })
    assert out['extracted'] == {
        'asr_mapping': 'hi',
        'sentence_end_mapping': True,
    }


def test_error_mapping_reads_root_like_executor():
    """error_code/error_msg 映射与 _parse_response 同口径：在完整响应上取"""
    sample = {'code': 1001, 'msg': 'bad request',
              'data': {'asr_result': 'hi'}}
    out = build_preview({
        'sample_response': sample,
        'error_code_mapping': 'code',
        'error_msg_mapping': 'msg',
    })
    assert out['extracted'] == {
        'error_code_mapping': 1001,
        'error_msg_mapping': 'bad request',
    }


def test_empty_string_value_is_resolved():
    """取到空串是「命中」（执行期空串不是 None），不进 unresolved"""
    out = build_preview({
        'sample_response': {'asr_result': ''},
        'asr_mapping': 'asr_result',
    })
    assert out['extracted'] == {'asr_mapping': ''}
    assert out['unresolved'] == []


# ──────────────── 与执行期同源：直接对拍适配器解析结果 ────────────────

def _make_adapter(meta):
    from types import SimpleNamespace
    from api_test_service.infrastructure.adapters.api_driver_adapter import (
        ApiDriverAdapter,
    )
    cfg = SimpleNamespace(
        endpoint='http://127.0.0.1:1', meta=meta, max_timeout=5,
        api_endpoints=[{'endpoint': 'http://127.0.0.1:1'}], id=7,
        vendor='probe', default_max_process=1)
    return ApiDriverAdapter(cfg, case_config={}, test_case_id='c1', task_id=7)


def test_preview_matches_executor_mapping_parse():
    """预览结果与 ApiDriverAdapter._parse_response 逐键一致（同源不同实现即失败）"""
    meta = {
        'asr_mapping': 'asr_result',
        'trans_mapping': 'translation_result',
        'sentence_end_mapping': 'is_sentence_end',
        'session_end_mapping': 'session_finished',
        'error_code_mapping': 'code',
        'error_msg_mapping': 'msg',
    }
    sample = {
        'code': 0, 'msg': 'ok',
        'data': {'asr_result': 'hi', 'translation_result': '你好',
                 'is_sentence_end': True, 'session_finished': False},
    }
    executor = _make_adapter(meta)._parse_response({'json': sample})
    preview = build_preview({'sample_response': sample, **meta})
    assert preview['extracted'] == {
        'asr_mapping': executor['asr'],
        'trans_mapping': executor['trans'],
        'sentence_end_mapping': executor['is_sentence_end'],
        'session_end_mapping': executor['is_session_end'],
        'error_code_mapping': executor['biz_code'],
        'error_msg_mapping': executor['biz_msg'],
    }
    assert preview['unresolved'] == []


def test_preview_matches_executor_result_parser():
    """result_parser 预览与 _parse_voice_llm_response 同键同值"""
    meta = {'result_parser': {
        'asr_text_path': 'result.asr_text',
        'trans_text_path': 'result.trans_text',
        'session_id_path': 'result.session_id',
    }}
    sample = {'result': {'asr_text': '你好', 'trans_text': 'hello',
                         'session_id': 's-1'}}
    executor = _make_adapter(meta)._parse_voice_llm_response({'json': sample})
    preview = build_preview({'sample_response': sample,
                             'result_parser': meta['result_parser']})
    assert preview['extracted']['asr_text_path'] == executor['asr']
    assert preview['extracted']['trans_text_path'] == executor['trans']
    assert preview['extracted']['session_id_path'] == executor['session_id']
    assert preview['unresolved'] == []


# ──────────────────── 验收 3：非法请求 → 400 ────────────────────

@pytest.mark.parametrize('payload,needle', [
    (None, 'JSON 对象'),                                  # 空请求体
    ('not-an-object', 'JSON 对象'),                        # 请求体非对象
    ({}, 'sample_response'),                              # 缺样例响应
    ({'sample_response': 123}, 'sample_response'),        # 数字既非 JSON 对象也非字符串
    ({'sample_response': {}, 'result_parser': 'a.b'}, 'result_parser'),
    ({'sample_response': {}, 'asr_mapping': {'path': 'a'}}, 'asr_mapping'),
    ({'sample_response': {}, 'asr_mapping': 'a[x].b'}, 'asr_mapping'),  # 非法写法
    ({'sample_response': {}, 'result_parser': {'asr_text_path': 'a[-1]'}},
     'result_parser.asr_text_path'),
])
def test_invalid_requests_raise_readable_error(payload, needle):
    """验收 3：空/非法请求体、非法路径 → 400 语义（异常 message 可读）"""
    with pytest.raises(ParsePreviewError) as exc:
        build_preview(payload)
    assert needle in str(exc.value)


def test_is_valid_path_matches_extract_semantics():
    """语法校验与执行期同一份分段规则"""
    for ok in ('a', 'a.b', 'a.b[0].c', 'a.b.0.c', '[0].text', 'a[0][1]'):
        assert is_valid_path(ok) is True, ok
    for bad in ('', None, 'a[x]', 'a[-1]', 'a..b', 'a[0]b', 'a.',
                'a.b[0'):
        assert is_valid_path(bad) is False, bad


# ──────────────────── 验收 4：权限 403 ────────────────────

def _build_app():
    """最小网关：真实 api 路由 + 按测试头注入权限，验证 401/403 门禁与 200"""
    from fastapi import FastAPI
    from starlette.middleware.base import BaseHTTPMiddleware

    from api_gateway.middleware import RequestAdapterMiddleware
    from api_gateway.routes.api_bp import router as api_router

    class _PermissionStub(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            raw = request.headers.get('x-test-permissions', '')
            request.state.permissions = [p for p in raw.split(',') if p]
            return await call_next(request)

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)
    app.add_middleware(_PermissionStub)
    app.include_router(api_router, prefix='/api/v1/apis')
    return app


def _client():
    from fastapi.testclient import TestClient
    return TestClient(_build_app())


def test_route_403_without_api_config_read():
    """验收 4：缺 api_config:read → 403"""
    resp = _client().post(
        '/api/v1/apis/parse-preview',
        json={'sample_response': NESTED_RAW,
              'result_parser': {'asr_text_path': 'a.b[0].c'}},
        headers={'x-test-permissions': 'task:read'},
    )
    assert resp.status_code == 403, resp.text


def test_route_200_with_permission():
    """有 api_config:read → 200，data 为 {extracted, unresolved}"""
    resp = _client().post(
        '/api/v1/apis/parse-preview',
        json={'sample_response': NESTED_RAW,
              'result_parser': {'asr_text_path': 'a.b[0].c'},
              'asr_mapping': 'nope'},
        headers={'x-test-permissions': 'api_config:read'},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body['success'] is True
    assert body['data'] == {
        'extracted': {'asr_text_path': 'zero'},
        'unresolved': ['nope'],
    }


def test_route_400_on_empty_body():
    """验收 3（HTTP 层）：空请求体 → 400 且 message 可读"""
    resp = _client().post(
        '/api/v1/apis/parse-preview',
        headers={'x-test-permissions': 'api_config:read',
                 'content-type': 'application/json'},
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body['success'] is False
    assert 'sample_response' in body['message'] or 'JSON' in body['message']


def test_route_400_on_illegal_path():
    """非法路径在 HTTP 层是 400，不混进 unresolved"""
    resp = _client().post(
        '/api/v1/apis/parse-preview',
        json={'sample_response': NESTED_RAW, 'asr_mapping': 'a[x]'},
        headers={'x-test-permissions': 'api_config:read'},
    )
    assert resp.status_code == 400, resp.text
    assert 'asr_mapping' in resp.json()['message']
