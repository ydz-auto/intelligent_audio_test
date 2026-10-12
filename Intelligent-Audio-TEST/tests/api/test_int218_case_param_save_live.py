# -*- coding: utf-8 -*-
"""INT-218 实机验收回归 — 算法定义整体保存 case_params 不再 400 + 失败语义。

缺陷（INT-210 验收发现）：task_service `_update_case_params` 既有行更新误走
UpdateParam RPC（设备/API 参数表），case_algorithm_params 行查不到 → 整体保存
必 400「Parameter id=43 不存在，无法更新」。更新分支已由 INT-198 修复、陈旧行
软删分支已由 INT-218（dfc5ec8a）修复改走 DeleteCaseParam；另新增写前预检
（跨算法 id 提前整体拒绝、零部分写）与失败响应已生效项披露。

覆盖（需 V9.7.31 实机栈，RUN_LIVE_STACK=1 显式纳入，未运行时经 require_backend skip）：
  - INT-210 复测口径：PUT 整体保存携带 case_params 既有行 id（编辑模态窗不触发
    blur 直接「确定」的后端口径）→ 成功、不再 400，值落库可读回
  - 省略删除：整体保存剔除某条 case 行 → 仅 case_algorithm_params 软删
    （deleted=True），device/api 行不受影响（INT-197 实测缺陷回归）
  - 跨算法 id：PUT 携带他算法 case 行 id → 预检整体拒绝，本算法零改动
    （零部分写：定义头与全部既有行原样，INT-197 跨表误删隐患的收口回归）
  - INT-210 四列表回归口径：device/api/case/mappings 四列表一次 PUT 全部正常更新

数据卫生：算法定义均为本回归创建的唯一 type（int218_<hex> 前缀），teardown 中
API 删除 + 按前缀硬删库中全部残留行（delete_algorithm 仅软删定义、不级联子行），
不留残留。

认证：AUTH_MODE=dev 时经 /auth/login/encryption-key + RSA-OAEP 登录取 token
（凭据取实机 .env DEV_DEFAULT_USERNAME/PASSWORD，回退 dev_user/dev_password）。
"""
import base64
import json
import os
import secrets

import httpx
import pytest
from tests.api.conftest import API_BASE, PROJECT_ROOT

_PREFIX = 'int218_' + secrets.token_hex(4)
_TYPE_A = f'{_PREFIX}_a'
_TYPE_B = f'{_PREFIX}_b'


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


def _db_rows(algo_type: str, table: str) -> list:
    """按算法 type 直查某表全部行（含软删），供落库口径断言。"""
    import sqlalchemy
    from sqlalchemy import text
    eng = sqlalchemy.create_engine(_database_url(),
                                   connect_args={'connect_timeout': 5})
    with eng.begin() as conn:
        rs = conn.execute(
            text(f'SELECT * FROM {table} WHERE algorithm_type = :t '
                 f'ORDER BY id'),
            {'t': algo_type})
        return [dict(r._mapping) for r in rs]


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


def _get_detail(client, headers, algo_type):
    detail = _data(client.get(f'/algorithm/definitions/{algo_type}',
                              headers=headers))
    assert detail is not None, f'GET {algo_type} 详情失败'
    return detail


def _save_payload(detail: dict) -> dict:
    """UI 整体保存的 PUT 载荷：既有行保留自身 id（前端 adapter 语义）。"""
    return {
        'name': detail.get('name'),
        'description': detail.get('description'),
        'status': detail.get('status', 'online'),
        'device_params': detail.get('device_params') or [],
        'api_params': detail.get('api_params') or [],
        'case_params': detail.get('case_params') or [],
        'mappings': detail.get('mappings') or {},
    }


def _create_payload_a() -> dict:
    """算法 A：2 设备行 + 1 API 行 + 2 case 行（lang/style）+ 1 设备映射。"""
    return {
        'type': _TYPE_A,
        'name': f'INT218算法A{_PREFIX}',
        'description': 'INT-218 实机回归（验收后删除）',
        'device_params': [
            {'param_code': 'audio_channel', 'param_name': '声道',
             'param_type': 'number', 'direction': 'output',
             'required': True, 'ui_order': 3, 'hidden': False},
            {'param_code': 'sample_rate', 'param_name': '采样率',
             'param_type': 'text', 'direction': 'input',
             'required': False, 'ui_order': 1, 'hidden': False},
        ],
        'api_params': [
            {'param_code': 'api_lang', 'param_name': '语言',
             'param_type': 'text', 'direction': 'input',
             'required': False, 'ui_order': 0, 'hidden': False},
        ],
        'case_params': [
            {'param_code': 'lang', 'param_name': '语言', 'param_type': 'text',
             'required': True, 'ui_order': 0, 'hidden': False, 'scope': 'common'},
            {'param_code': 'style', 'param_name': '风格', 'param_type': 'text',
             'required': False, 'ui_order': 1, 'hidden': False, 'scope': 'common'},
        ],
        'mappings': {
            'device': [
                {'source': 'device', 'source_param': 'asr_text',
                 'source_direction': 'output', 'target_param': 'text',
                 'transform_type': 'none'},
            ],
            'api': [],
        },
    }


def _create_payload_b() -> dict:
    """算法 B（跨算法 id 用）：仅 1 条 case 行。"""
    return {
        'type': _TYPE_B,
        'name': f'INT218算法B{_PREFIX}',
        'description': 'INT-218 跨算法 id 用（验收后删除）',
        'device_params': [],
        'api_params': [],
        'case_params': [
            {'param_code': 'b_only', 'param_name': 'B专属',
             'param_type': 'text', 'required': False, 'ui_order': 0,
             'hidden': False, 'scope': 'common'},
        ],
        'mappings': {},
    }


def _snapshot(detail: dict) -> str:
    """四列表行快照（去时间戳），供零改动比对。"""
    return json.dumps({
        'name': detail.get('name'),
        'device_params': detail.get('device_params'),
        'api_params': detail.get('api_params'),
        'case_params': detail.get('case_params'),
        'mappings': detail.get('mappings'),
    }, ensure_ascii=False, sort_keys=True, default=str)


@pytest.fixture(scope='module')
def auth_headers(api_client):
    return _bearer_header(api_client)


@pytest.fixture(scope='module')
def algo_a(api_client, auth_headers):
    """创建算法 A/B 并返回 A 创建后详情；module 结束时清理全部测试数据。"""
    r = api_client.post('/algorithm/definitions', json=_create_payload_a(),
                        headers=auth_headers)
    assert r.status_code < 400, f'算法A创建失败: {r.status_code} {r.text[:300]}'
    r = api_client.post('/algorithm/definitions', json=_create_payload_b(),
                        headers=auth_headers)
    assert r.status_code < 400, f'算法B创建失败: {r.status_code} {r.text[:300]}'
    yield _get_detail(api_client, auth_headers, _TYPE_A)
    for algo_type in (_TYPE_A, _TYPE_B):
        api_client.delete(f'/algorithm/definitions/{algo_type}',
                          headers=auth_headers)
    _purge_test_rows()


# ── 用例 1：INT-210 复测口径 — case 既有行整体保存不再 400 ──

def test_case_existing_row_whole_save_succeeds(api_client, auth_headers, algo_a):
    """PUT 整体保存携带 case_params 既有行 id（原必 400「Parameter id=43 不存在」）
    → 成功、修改后值落库可读回（编辑模态窗不触发 blur 直接「确定」的后端口径）。"""
    detail = _get_detail(api_client, auth_headers, _TYPE_A)
    case_rows = detail.get('case_params') or []
    assert len(case_rows) == 2, f'前置异常：case 行数 {len(case_rows)}'
    assert all(r.get('id') for r in case_rows), 'case 既有行应携带 id'

    payload = _save_payload(detail)
    for r in payload['case_params']:
        if r['param_code'] == 'lang':
            r['param_name'] = '语言(INT218改)'
        if r['param_code'] == 'style':
            r['help_text'] = 'INT-218 回归改风格'
    r = api_client.put(f'/algorithm/definitions/{_TYPE_A}', json=payload,
                       headers=auth_headers)
    assert r.status_code < 400, \
        f'整体保存仍失败（缺陷表征）: {r.status_code} {r.text[:300]}'

    after = _get_detail(api_client, auth_headers, _TYPE_A)
    by_code = {c['param_code']: c for c in (after.get('case_params') or [])}
    assert by_code['lang']['param_name'] == '语言(INT218改)'
    assert by_code['style']['help_text'] == 'INT-218 回归改风格'
    assert len(by_code) == 2

    db_rows = _db_rows(_TYPE_A, 'case_algorithm_params')
    assert len(db_rows) == 2 and all(not row['deleted'] for row in db_rows)


# ── 用例 2：省略删除仅打 case 表（INT-197 实测缺陷回归）──

def test_case_omitted_row_soft_deleted_in_case_table_only(api_client, auth_headers,
                                                          algo_a):
    """整体保存剔除一条 case 行 → 该行仅 case_algorithm_params 软删（deleted=True），
    device/api 行不受影响（修复前走 DeleteParam：无撞车则静默漏删、撞车误删他表）。"""
    detail = _get_detail(api_client, auth_headers, _TYPE_A)
    payload = _save_payload(detail)
    payload['case_params'] = [c for c in payload['case_params']
                              if c['param_code'] != 'style']

    r = api_client.put(f'/algorithm/definitions/{_TYPE_A}', json=payload,
                       headers=auth_headers)
    assert r.status_code < 400, f'省略删除保存失败: {r.status_code} {r.text[:300]}'

    case_db = _db_rows(_TYPE_A, 'case_algorithm_params')
    by_code = {row['param_code']: row for row in case_db}
    assert by_code['style']['deleted'] is True, \
        '被剔除的 case 行未在 case 表软删（缺陷表征：静默漏删）'
    assert by_code['lang']['deleted'] is False

    # 设备/API 行不受影响：全部 deleted=False
    for table in ('algorithm_device_params', 'algorithm_api_params'):
        rows = _db_rows(_TYPE_A, table)
        assert rows and all(not row['deleted'] for row in rows), \
            f'{table} 出现非预期软删（跨表误删表征）'


# ── 用例 3：跨算法 case 行 id → 预检整体拒绝、零部分写 ──

def test_cross_algorithm_case_id_rejected_with_zero_partial_write(
        api_client, auth_headers, algo_a):
    """PUT 携带算法 B 的 case 行 id → 预检整体拒绝；算法 A 定义头与四列表
    零改动（修复前该类失败发生于写循环中段，前面的写已静默落库）。"""
    before = _snapshot(_get_detail(api_client, auth_headers, _TYPE_A))

    detail_b = _get_detail(api_client, auth_headers, _TYPE_B)
    foreign_case = (detail_b.get('case_params') or [])[0]

    detail_a = _get_detail(api_client, auth_headers, _TYPE_A)
    payload = _save_payload(detail_a)
    payload['name'] = 'INT218零部分写验证名'
    payload['case_params'] = payload['case_params'] + [
        {'id': foreign_case['id'], 'param_name': '跨算法改写'}]

    r = api_client.put(f'/algorithm/definitions/{_TYPE_A}', json=payload,
                       headers=auth_headers)
    assert r.status_code >= 400, \
        f'跨算法 case 行 id 应被拒绝，实际: {r.status_code} {r.text[:200]}'
    body = r.json()
    msg = json.dumps(body, ensure_ascii=False)
    assert '拒绝跨算法' in msg, f'失败信息未指明跨算法拒绝: {msg[:300]}'

    after = _snapshot(_get_detail(api_client, auth_headers, _TYPE_A))
    assert after == before, '预检拒绝后算法 A 出现部分写（缺陷表征）'

    # 算法 B 行未被误改
    detail_b_after = _get_detail(api_client, auth_headers, _TYPE_B)
    b_case = (detail_b_after.get('case_params') or [])[0]
    assert b_case['param_name'] == foreign_case['param_name']


# ── 用例 4：INT-210 四列表回归口径不回退 ──

def test_four_list_whole_save_regression(api_client, auth_headers, algo_a):
    """四列表一次 PUT 全部更新：device/api/case 改值 + mappings 改目标参数
    → 全部落库（INT-210 验收正常路径不回退）。"""
    detail = _get_detail(api_client, auth_headers, _TYPE_A)
    payload = _save_payload(detail)
    for d in payload['device_params']:
        if d['param_code'] == 'audio_channel':
            d['param_name'] = '声道(四列表改)'
    for a in payload['api_params']:
        if a['param_code'] == 'api_lang':
            a['param_name'] = '语言(四列表改)'
    # case 行 lang 已在用例 2 后被软删，重新创建 + 保留 style 不在
    payload['case_params'] = [
        {'param_code': 'lang2', 'param_name': '语言2', 'param_type': 'text',
         'required': True, 'ui_order': 0, 'hidden': False, 'scope': 'common'},
    ]
    dev_map = (payload['mappings'].get('device') or [])
    assert dev_map, '前置异常：无设备映射行'
    dev_map[0]['target_param'] = 'text(四列表改)'

    r = api_client.put(f'/algorithm/definitions/{_TYPE_A}', json=payload,
                       headers=auth_headers)
    assert r.status_code < 400, f'四列表保存失败: {r.status_code} {r.text[:300]}'

    after = _get_detail(api_client, auth_headers, _TYPE_A)
    dev_by_code = {d['param_code']: d for d in (after.get('device_params') or [])}
    api_by_code = {a['param_code']: a for a in (after.get('api_params') or [])}
    assert dev_by_code['audio_channel']['param_name'] == '声道(四列表改)'
    assert api_by_code['api_lang']['param_name'] == '语言(四列表改)'
    case_codes = {c['param_code'] for c in (after.get('case_params') or [])}
    assert case_codes == {'lang2'}, f'case 列表口径异常: {case_codes}'
    maps = after.get('mappings') or {}
    assert (maps.get('device') or [{}])[0].get('target_param') == 'text(四列表改)'

    # 落库口径：device/api/case 均无意外软删，映射改值生效
    assert all(not row['deleted'] for row in _db_rows(_TYPE_A,
                                                      'algorithm_device_params'))
    assert all(not row['deleted'] for row in _db_rows(_TYPE_A,
                                                      'algorithm_api_params'))
    case_db = _db_rows(_TYPE_A, 'case_algorithm_params')
    assert all(not row['deleted'] for row in case_db if row['param_code'] == 'lang2')
