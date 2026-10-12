# -*- coding: utf-8 -*-
"""INT-211 实机验收回归 — 算法复制链路行隔离（副本保存不得改写源算法参数行）。

缺陷（INT-210 范围外发现）：旧 handleClone 将源算法定义原样展开提交，载荷携带源
算法各行真实 id；后端 _update_* 的 id 对账分支按全局 id 取行且不校验 algorithm_type
归属，副本保存改写源算法参数行、副本自身不产生参数行。

修复：前端 handleClone 剥离行级 id（复制=纯新建）；后端 _update_* id 分支新增
_assert_row_owner 归属校验（跨算法 id 整体拒绝）。

覆盖（需 V9.7.31 实机栈，RUN_LIVE_STACK=1 显式纳入，未运行时经 require_backend skip）：
  - 复制（无 id 载荷新建）→ 副本生成自己的参数行（新 id），字段值逐项保留
  - 打开副本修改参数保存（PUT，副本自身 id 对账）→ 源算法行完全不变
  - 复制后不做任何修改直接保存副本 → 源算法行不被改写
  - 删除副本 → 源算法参数行完好
  - 防御路径：携带源算法真实行 id 的旧式复制载荷 → 整体拒绝（写前预检零部分写，
    新定义不落库），源行零改写

数据卫生：源算法/副本均为本回归创建的唯一 type（int211_<hex> 前缀），teardown 中
API 删除 + 按前缀硬删库中全部残留行（delete_algorithm 仅软删定义、不级联子行），
不留残留。

认证：AUTH_MODE=dev 时经 /auth/login/encryption-key + RSA-OAEP 登录取 token
（凭据取实机 .env DEV_DEFAULT_USERNAME/PASSWORD，回退 dev_user/dev_password）；
off 模式下直接匿名请求。
"""
import base64
import json
import os
import secrets

import httpx
import pytest
from tests.api.conftest import API_BASE, PROJECT_ROOT

_PREFIX = 'int211_' + secrets.token_hex(4)
_TYPE_SOURCE = f'{_PREFIX}_src'
_TYPE_CLONE = f'{_PREFIX}_copy'
_TYPE_LEGACY = f'{_PREFIX}_legacy'


def _database_url() -> str:
    """实机栈 .env 的 DATABASE_URL（与 run_all 同源解析；缺省回退本地默认值）。"""
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


def _purge_test_rows() -> None:
    """数据卫生：按本回归唯一前缀硬删全部残留行（定义软删 + 子行孤儿）。

    delete_algorithm 仅软删定义行，不级联子行；API 删除后仍有参数/映射
    孤儿残留，故 teardown 以唯一前缀精确硬删，库中不留本卡测试数据。
    """
    import sqlalchemy
    from sqlalchemy import text
    eng = sqlalchemy.create_engine(_database_url(),
                                   connect_args={'connect_timeout': 5})
    pattern = _PREFIX + '\\_%'
    with eng.begin() as conn:
        for table, col in (('algorithm_device_params', 'algorithm_type'),
                           ('algorithm_api_params', 'algorithm_type'),
                           ('case_algorithm_params', 'algorithm_type'),
                           ('param_mappings', 'algorithm_type'),
                           ('algorithm_dimension_relations', 'algorithm_type'),
                           ('algorithm_definitions', 'type')):
            conn.execute(text(f'DELETE FROM {table} WHERE {col} LIKE :p'),
                         {'p': pattern})


# ── 认证 ──────────────────────────────────────────────────

def _bearer_header(client: httpx.Client) -> dict:
    """AUTH_MODE=dev 时登录获取 Bearer token；off 模式返回空头。"""
    r = client.get('/auth/login/encryption-key')
    if r.status_code != 200:
        return {}
    info = r.json()
    if isinstance(info.get('data'), dict) and info['data'].get('kid'):
        info = info['data']
    if not info.get('enabled'):
        return {}
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    pub = serialization.load_pem_public_key(info['public_key'].encode())

    def _login(username: str, password: str):
        ct = base64.b64encode(pub.encrypt(
            password.encode(),
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                         algorithm=hashes.SHA256(), label=None))).decode()
        return client.post('/auth/login', data={
            'username': username, 'password_encrypted': ct,
            'encryption_key_id': info['kid']})

    # 凭据与实机 .env 种子一致（DEV_DEFAULT_*），回退 dev_user/dev_password
    r = _login(os.environ.get('DEV_DEFAULT_USERNAME', 'admin'),
               os.environ.get('DEV_DEFAULT_PASSWORD', 'admin123'))
    if r.status_code != 200:
        r = _login('dev_user', 'dev_password')
    assert r.status_code == 200, f'登录失败: {r.status_code} {r.text[:200]}'
    body = r.json()
    token = body.get('access_token') or (body.get('data') or {}).get('token')
    assert token, f'登录响应无 token: {json.dumps(body, ensure_ascii=False)[:200]}'
    return {'Authorization': f'Bearer {token}'}


# ── 工具 ──────────────────────────────────────────────────

def _data(resp: httpx.Response):
    body = resp.json()
    return body.get('data') if isinstance(body, dict) and 'data' in body else body


def _strip_row_ids(detail: dict) -> dict:
    """复刻修复后 handleClone 的载荷构造：四类参数列表剥离行级 id（INT-211 主修复）。"""
    def strip(items):
        return [{k: v for k, v in item.items() if k != 'id'} for item in (items or [])]
    payload = {k: v for k, v in detail.items() if k not in ('id', 'created_at', 'updated_at')}
    payload['device_params'] = strip(detail.get('device_params'))
    payload['api_params'] = strip(detail.get('api_params'))
    payload['case_params'] = strip(detail.get('case_params'))
    if detail.get('mappings') is not None:
        payload['mappings'] = {
            source_type: strip(lst)
            for source_type, lst in detail['mappings'].items()
        }
    return payload


def _save_payload(detail: dict) -> dict:
    """UI 整体保存的 PUT 载荷：仅 Update schema 字段，既有行保留自身 id
    （后端以 id 对账，未提交 id 会被软删除——与前端 adapter 保留 id 的语义一致）。"""
    return {
        'name': detail.get('name'),
        'description': detail.get('description'),
        'status': detail.get('status', 'online'),
        'device_params': detail.get('device_params') or [],
        'api_params': detail.get('api_params') or [],
        'case_params': detail.get('case_params') or [],
        'mappings': detail.get('mappings') or {},
    }


def _row_lists(detail: dict) -> dict:
    """提取四类参数行的 (id, 关键字段) 快照，用于源行零改写比对。"""
    mappings = detail.get('mappings') or {}
    return {
        'device_params': [(r.get('id'), r.get('param_code'), r.get('param_name'),
                           r.get('direction'), r.get('required'), r.get('ui_order'))
                          for r in (detail.get('device_params') or [])],
        'api_params': [(r.get('id'), r.get('param_code'), r.get('param_name'))
                       for r in (detail.get('api_params') or [])],
        'case_params': [(r.get('id'), r.get('param_code'), r.get('param_name'),
                         r.get('scope'), r.get('required'))
                        for r in (detail.get('case_params') or [])],
        'mappings': {k: [(r.get('id'), r.get('source_param'), r.get('target_param'))
                         for r in (v or [])] for k, v in mappings.items()},
    }


def _create_source_payload() -> dict:
    """源算法：四类参数列表各含真实行（值互异），不带维度关联（避免关联表清理面）。"""
    return {
        'type': _TYPE_SOURCE,
        'name': f'INT211源算法{_PREFIX}',
        'description': 'INT-211 复制链路行隔离回归（验收后删除）',
        'device_params': [
            {'param_code': 'audio_channel', 'param_name': '声道', 'param_type': 'number',
             'direction': 'output', 'required': True, 'ui_order': 3, 'hidden': False},
            {'param_code': 'sample_rate', 'param_name': '采样率', 'param_type': 'text',
             'direction': 'input', 'required': False, 'ui_order': 1, 'hidden': False},
        ],
        'api_params': [
            {'param_code': 'api_lang', 'param_name': '语言', 'param_type': 'text',
             'direction': 'input', 'required': False, 'ui_order': 0, 'hidden': False},
        ],
        'case_params': [
            {'param_code': 'lang', 'param_name': '语言', 'param_type': 'text',
             'required': True, 'ui_order': 0, 'hidden': False, 'scope': 'common'},
        ],
        'mappings': {
            'device': [
                {'source': 'device', 'source_param': 'asr_text', 'source_direction': 'output',
                 'target_param': 'text', 'transform_type': 'none'},
            ],
            'api': [],
        },
    }


@pytest.fixture(scope='module')
def auth_headers(api_client):
    return _bearer_header(api_client)


@pytest.fixture(scope='module')
def source_snapshot(api_client, auth_headers):
    """创建源算法并返回创建后的行快照；module 结束时删除本回归全部算法定义。"""
    r = api_client.post('/algorithm/definitions', json=_create_source_payload(),
                        headers=auth_headers)
    assert r.status_code < 400, f'源算法创建失败: {r.status_code} {r.text[:300]}'
    detail = _data(api_client.get(f'/algorithm/definitions/{_TYPE_SOURCE}',
                                  headers=auth_headers))
    yield _row_lists(detail)
    for algo_type in (_TYPE_LEGACY, _TYPE_CLONE, _TYPE_SOURCE):
        api_client.delete(f'/algorithm/definitions/{algo_type}', headers=auth_headers)
    _purge_test_rows()


def _get_source_rows(api_client, auth_headers) -> dict:
    detail = _data(api_client.get(f'/algorithm/definitions/{_TYPE_SOURCE}',
                                  headers=auth_headers))
    return _row_lists(detail)


# ── 用例 ──────────────────────────────────────────────────

def test_clone_payload_creates_own_rows_and_preserves_values(api_client, auth_headers,
                                                             source_snapshot):
    """复制（无 id 载荷）→ 副本生成自己的参数行（新 id），字段值逐项保留。"""
    src_detail = _data(api_client.get(f'/algorithm/definitions/{_TYPE_SOURCE}',
                                      headers=auth_headers))
    clone_payload = _strip_row_ids(src_detail)
    clone_payload['type'] = _TYPE_CLONE
    clone_payload['name'] = f'{src_detail["name"]} (副本)'

    for lst in (clone_payload['device_params'], clone_payload['api_params'],
                clone_payload['case_params']):
        assert lst and all('id' not in item for item in lst), '复制载荷不应携带行级 id'
    for lst in clone_payload['mappings'].values():
        assert all('id' not in item for item in lst), '复制载荷映射不应携带行级 id'

    r = api_client.post('/algorithm/definitions', json=clone_payload, headers=auth_headers)
    assert r.status_code < 400, f'复制创建失败: {r.status_code} {r.text[:300]}'

    clone_detail = _data(api_client.get(f'/algorithm/definitions/{_TYPE_CLONE}',
                                        headers=auth_headers))
    assert clone_detail['type'] == _TYPE_CLONE

    # 副本行全部是新 id（与源行 id 无交集），且字段值逐项保留
    src_ids = {rid for rid, *_ in source_snapshot['device_params']}
    src_ids |= {rid for rid, *_ in source_snapshot['api_params']}
    src_ids |= {rid for rid, *_ in source_snapshot['case_params']}
    clone_rows = (clone_detail.get('device_params') or []) + \
                 (clone_detail.get('api_params') or []) + \
                 (clone_detail.get('case_params') or [])
    assert clone_rows, '副本未产生自己的参数行（缺陷表征）'
    assert all(row.get('id') not in src_ids for row in clone_rows), \
        '副本参数行复用了源算法行 id（缺陷表征）'

    by_code = {r['param_code']: r for r in clone_rows}
    assert by_code['audio_channel']['param_name'] == '声道'
    assert by_code['audio_channel']['direction'] == 'output'
    assert by_code['sample_rate']['ui_order'] == 1
    assert by_code['api_lang']['param_name'] == '语言'
    case = {r['param_code']: r for r in clone_detail.get('case_params') or []}
    assert case['lang']['scope'] == 'common'

    clone_maps = clone_detail.get('mappings') or {}
    assert clone_maps.get('device') and clone_maps['device'][0]['source_param'] == 'asr_text'
    assert clone_maps.get('device') and clone_maps['device'][0]['target_param'] == 'text'
    assert clone_maps.get('api') == []


def test_modified_clone_save_never_touches_source_rows(api_client, auth_headers,
                                                       source_snapshot):
    """打开副本修改参数保存 → 源算法行完全不变（验收标准 1）。"""
    clone_detail = _data(api_client.get(f'/algorithm/definitions/{_TYPE_CLONE}',
                                        headers=auth_headers))
    update_payload = _save_payload(clone_detail)
    update_payload['name'] = f'{clone_detail["name"]}·改'

    # 模拟 UI 修改：设备参数、用例参数各改一行值（携带副本自身 id 走对账更新）
    dev = next(r for r in update_payload['device_params']
               if r['param_code'] == 'audio_channel')
    dev['param_name'] = '声道·副本改'
    case = next(r for r in update_payload['case_params'] if r['param_code'] == 'lang')
    case['param_name'] = '语言·副本改'

    r = api_client.put(f'/algorithm/definitions/{_TYPE_CLONE}', json=update_payload,
                       headers=auth_headers)
    assert r.status_code < 400, f'副本修改保存失败: {r.status_code} {r.text[:300]}'

    clone_after = _data(api_client.get(f'/algorithm/definitions/{_TYPE_CLONE}',
                                       headers=auth_headers))
    clone_dev = {r['param_code']: r for r in clone_after.get('device_params') or []}
    clone_case = {r['param_code']: r for r in clone_after.get('case_params') or []}
    assert clone_dev['audio_channel']['param_name'] == '声道·副本改'
    assert clone_case['lang']['param_name'] == '语言·副本改'

    # 核心断言：源算法对应行完全不变
    assert _get_source_rows(api_client, auth_headers) == source_snapshot, \
        '副本保存改写了源算法参数行（缺陷回归）'


def test_unmodified_clone_save_never_touches_source_rows(api_client, auth_headers,
                                                         source_snapshot):
    """复制后不做任何修改直接保存副本 → 源算法行不被改写（验收标准 3）。"""
    clone_detail = _data(api_client.get(f'/algorithm/definitions/{_TYPE_CLONE}',
                                        headers=auth_headers))
    r = api_client.put(f'/algorithm/definitions/{_TYPE_CLONE}',
                       json=_save_payload(clone_detail), headers=auth_headers)
    assert r.status_code < 400, f'副本原样保存失败: {r.status_code} {r.text[:300]}'
    assert _get_source_rows(api_client, auth_headers) == source_snapshot, \
        '副本原样保存改写了源算法参数行（缺陷回归）'


def test_delete_clone_keeps_source_rows(api_client, auth_headers, source_snapshot):
    """删除副本 → 源算法参数行完好（验收标准 2）。"""
    r = api_client.delete(f'/algorithm/definitions/{_TYPE_CLONE}', headers=auth_headers)
    assert r.status_code < 400, f'副本删除失败: {r.status_code} {r.text[:300]}'
    assert _get_source_rows(api_client, auth_headers) == source_snapshot, \
        '删除副本影响了源算法参数行'


def test_legacy_clone_payload_rejected_and_source_rows_untouched(api_client, auth_headers,
                                                                 source_snapshot):
    """防御路径：旧式复制载荷携带源算法真实行 id → 后端整体拒绝（写前预检零部分写），
    新定义不落库，源行零改写（后端 _assert_row_owner 加固）。"""
    src_detail = _data(api_client.get(f'/algorithm/definitions/{_TYPE_SOURCE}',
                                      headers=auth_headers))
    legacy_payload = {k: v for k, v in src_detail.items()
                      if k not in ('id', 'created_at', 'updated_at')}
    legacy_payload['type'] = _TYPE_LEGACY
    legacy_payload['name'] = f'{src_detail["name"]} (legacy)'

    r = api_client.post('/algorithm/definitions', json=legacy_payload, headers=auth_headers)
    assert r.status_code >= 400, \
        f'携带他算法行 id 的创建应被整体拒绝，实际: {r.status_code}'

    detail = api_client.get(f'/algorithm/definitions/{_TYPE_LEGACY}', headers=auth_headers)
    assert detail.status_code >= 400, '被拒请求留下了新算法定义（部分写）'
    assert _get_source_rows(api_client, auth_headers) == source_snapshot, \
        '被拒请求改写了源算法参数行'
