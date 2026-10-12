# -*- coding: utf-8 -*-
"""INT-222 实机验收回归 — 算法参数 default_value 非 JSON 文本全链读回原文。

缺陷（INT-197 验收范围外发现②）：default_value 存非 JSON 文本（如 'zh'）时写路径
正常落库（DB 直查可见原值），但读路径（四类 PO to_dict 的 _parse_json 私有副本 +
converter _parse_json_value）json.loads 失败静默返 None → GET definitions 经 gRPC
回读空，重开算法配置模态窗默认值丢失。修复（01fca20c）：共享 helper
parse_json_or_raw 统一五处读点宽松语义——空值仍 None、合法 JSON 形态解析为对象、
解析失败返回原始字符串。

覆盖（需 V9.7.31 实机栈，RUN_LIVE_STACK=1 显式纳入，未运行时经 require_backend skip）：
  - case 主路径（验收标准 1）：default_value='zh' 落库原值（DB 直查断言前置）→
    GET /algorithm/definitions/{type} 全链（网关 gRPC → algorithm_service
    CaseParamRepository → PO.to_dict）回读 'zh'
  - JSON 形态回归（标准 2）：'{"k":1}' / '[1,2]' / '42' 回读解析后对象/数字
  - 空值回归（标准 3）：未携带 default_value 的行回读 None
  - 同族（标准 4）：device / api 参数 'zh' 经各自 gRPC 读链回读原文；
    dimension 参数经 evaluation_service gRPC 读链（GetDimensionParams →
    DimensionParamRepository → PO.to_dict）回读原文 + JSON 形态文本回读解析对象。
    维度写路径对纯文本 default_value 做 json.dumps（会写成 JSON 字符串形态），
    故「库中非 JSON 文本」状态按 issue 取证口径（实机 E2E + DB 直查）以 DB 直写
    构造——本回归验证的是读链语义，不依赖写路径。
  - 算法创建后 case 行 default_value 落库口径为原样文本（写路径 INT-197/218
    修复不回退的前置自证）

数据卫生：算法均为本回归唯一 type（int222_<hex> 前缀），teardown API 删除 +
按前缀硬删全部残留行（delete_algorithm 仅软删定义、不级联子行）；维度为唯一
name 前缀，API 删除 + 按 dimension_id / name 前缀硬删参数行、关联行与维度行，
库中不留残留。

认证：AUTH_MODE=dev 时经 /auth/login/encryption-key + RSA-OAEP 登录取 token
（凭据取实机 .env DEV_DEFAULT_USERNAME/PASSWORD，回退 admin/admin123 →
dev_user/dev_password）。
"""
import base64
import json
import os
import secrets

import httpx
import pytest
from tests.api.conftest import API_BASE, PROJECT_ROOT

_PREFIX = 'int222_' + secrets.token_hex(4)
_TYPE = f'{_PREFIX}_a'
_DIM_NAME = f'INT222维度{_PREFIX}'


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


def _db_engine():
    import sqlalchemy
    return sqlalchemy.create_engine(_database_url(),
                                    connect_args={'connect_timeout': 5})


def _purge_test_rows() -> None:
    """数据卫生：按唯一前缀 / 维度 id 硬删全部残留行（API 删除仅软删）。"""
    from sqlalchemy import text
    eng = _db_engine()
    algo_pattern = _PREFIX + '\\_%'
    dim_pattern = _DIM_NAME + '%'
    with eng.begin() as conn:
        for table, col in (('algorithm_device_params', 'algorithm_type'),
                           ('algorithm_api_params', 'algorithm_type'),
                           ('case_algorithm_params', 'algorithm_type'),
                           ('param_mappings', 'algorithm_type'),
                           ('algorithm_dimension_relations', 'algorithm_type'),
                           ('algorithm_definitions', 'type')):
            conn.execute(text(f'DELETE FROM {table} WHERE {col} LIKE :p'),
                         {'p': algo_pattern})
        # 维度族：按唯一 name 前缀定位 id，硬删参数行 / 关联行 / 维度行
        dim_ids = [row[0] for row in conn.execute(
            text("SELECT id FROM dimensions WHERE name LIKE :p"),
            {'p': dim_pattern})]
        for dim_id in dim_ids:
            conn.execute(text(
                'DELETE FROM evaluation_dimension_params WHERE dimension_id = :i'),
                {'i': dim_id})
            conn.execute(text(
                'DELETE FROM algorithm_dimension_relations WHERE dimension_id = :i'),
                {'i': dim_id})
        conn.execute(text("DELETE FROM dimensions WHERE name LIKE :p"),
                     {'p': dim_pattern})


def _db_case_default(algo_type: str, param_code: str):
    """直查 case 参数行 default_value 原值（含软删），供落库口径断言。"""
    from sqlalchemy import text
    eng = _db_engine()
    with eng.begin() as conn:
        rs = conn.execute(text(
            'SELECT default_value FROM case_algorithm_params '
            'WHERE algorithm_type = :t AND param_code = :c'),
            {'t': algo_type, 'c': param_code})
        rows = [r[0] for r in rs]
    assert len(rows) == 1, \
        f'case 行查询异常: {algo_type}/{param_code} 命中 {len(rows)} 行'
    return rows[0]


def _db_set_dimension_default(dim_id: int, param_code: str, raw: str) -> None:
    """DB 直写维度参数行 default_value（构造库中非 JSON 文本状态，issue 取证口径）。"""
    from sqlalchemy import text
    eng = _db_engine()
    with eng.begin() as conn:
        rs = conn.execute(text(
            'UPDATE evaluation_dimension_params SET default_value = :v '
            'WHERE dimension_id = :i AND param_code = :c'),
            {'v': raw, 'i': dim_id, 'c': param_code})
    assert rs.rowcount == 1, \
        f'维度参数行更新失败: dim_id={dim_id} param_code={param_code}'


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


def _case_by_code(detail: dict) -> dict:
    return {c['param_code']: c for c in (detail.get('case_params') or [])}


def _create_payload() -> dict:
    """算法：3 case 行（非 JSON 文本 / JSON 形态 / 空值）+ device/api 各 1 行 'zh'。"""
    return {
        'type': _TYPE,
        'name': f'INT222算法{_PREFIX}',
        'description': 'INT-222 实机回归（验收后删除）',
        'device_params': [
            {'param_code': 'dev_lang', 'param_name': '设备语言',
             'param_type': 'text', 'direction': 'input', 'required': False,
             'ui_order': 0, 'hidden': False, 'default_value': 'zh'},
        ],
        'api_params': [
            {'param_code': 'api_lang', 'param_name': '接口语言',
             'param_type': 'text', 'direction': 'input', 'required': False,
             'ui_order': 0, 'hidden': False, 'default_value': 'zh'},
        ],
        'case_params': [
            {'param_code': 'lang', 'param_name': '语言', 'param_type': 'text',
             'required': False, 'ui_order': 0, 'hidden': False,
             'scope': 'common', 'default_value': 'zh'},
            {'param_code': 'cfg', 'param_name': '配置', 'param_type': 'json',
             'required': False, 'ui_order': 1, 'hidden': False,
             'scope': 'common', 'default_value': '{"k":1}'},
            {'param_code': 'arr', 'param_name': '列表', 'param_type': 'json',
             'required': False, 'ui_order': 2, 'hidden': False,
             'scope': 'common', 'default_value': '[1,2]'},
            {'param_code': 'num', 'param_name': '数字', 'param_type': 'number',
             'required': False, 'ui_order': 3, 'hidden': False,
             'scope': 'common', 'default_value': '42'},
            {'param_code': 'empty', 'param_name': '空默认', 'param_type': 'text',
             'required': False, 'ui_order': 4, 'hidden': False,
             'scope': 'common'},
        ],
        'mappings': {},
    }


@pytest.fixture(scope='module')
def auth_headers(api_client):
    return _bearer_header(api_client)


@pytest.fixture(scope='module')
def algo_detail(api_client, auth_headers):
    """创建算法定义并自证写路径落库口径（原样文本），module 结束清理全部数据。"""
    r = api_client.post('/algorithm/definitions', json=_create_payload(),
                        headers=auth_headers)
    assert r.status_code < 400, f'算法创建失败: {r.status_code} {r.text[:300]}'

    # 写路径落库口径自证（INT-197/218 修复不回退）：'zh' 应为原样文本，
    # '{"k":1}' / '[1,2]' / '42' 应为原样 JSON 形态文本（读侧解析的前提）
    assert _db_case_default(_TYPE, 'lang') == 'zh'
    assert _db_case_default(_TYPE, 'cfg') == '{"k":1}'
    assert _db_case_default(_TYPE, 'arr') == '[1,2]'
    assert _db_case_default(_TYPE, 'num') == '42'

    yield _data(api_client.get(f'/algorithm/definitions/{_TYPE}',
                               headers=auth_headers))
    api_client.delete(f'/algorithm/definitions/{_TYPE}', headers=auth_headers)
    _purge_test_rows()


@pytest.fixture(scope='module')
def dim_id(api_client, auth_headers):
    """创建维度（含 2 个输入参数行），DB 直写非 JSON 文本后返回 dim_id；结束清理。"""
    r = api_client.post('/evaluation/dimensions', json={
        'name': _DIM_NAME,
        'description': 'INT-222 实机回归（验收后删除）',
        'fieldType': 'number',
        'required_inputs': [
            {'param_code': 'dim_lang', 'param_name': '语言', 'label': '语言',
             'field_type': 'text', 'required': False, 'ui_order': 0},
            {'param_code': 'dim_cfg', 'param_name': '配置', 'label': '配置',
             'field_type': 'text', 'required': False, 'ui_order': 1},
        ],
    }, headers=auth_headers)
    assert r.status_code < 400, f'维度创建失败: {r.status_code} {r.text[:300]}'
    new_id = (_data(r) or {}).get('id')
    assert new_id, f'维度创建响应无 id: {r.text[:200]}'

    # 库中非 JSON 文本状态（issue 取证口径：DB 直查可见原值）
    _db_set_dimension_default(new_id, 'dim_lang', 'zh')
    _db_set_dimension_default(new_id, 'dim_cfg', '{"k":1}')

    yield new_id
    api_client.delete(f'/evaluation/dimensions/{new_id}', headers=auth_headers)
    _purge_test_rows()


# ── 验收标准 1：case 主路径 'zh' 全链回读原文 ──

def test_case_param_non_json_text_read_back_full_chain(algo_detail):
    """default_value='zh' 落库原值 → GET definitions 全链回读 'zh'
    （重开算法配置模态窗默认值可见的后端口径，修复前回读 None）。"""
    by_code = _case_by_code(algo_detail)
    assert by_code['lang']['default_value'] == 'zh', \
        f"非 JSON 文本默认值读回异常（缺陷表征应为 None）: {by_code['lang']}"


# ── 验收标准 2：JSON 形态回归不破坏 ──

def test_case_param_json_form_still_parsed(algo_detail):
    """'{"k":1}' / '[1,2]' / '42' 回读仍为解析后对象/数字（修复行为不变）。"""
    by_code = _case_by_code(algo_detail)
    assert by_code['cfg']['default_value'] == {'k': 1}
    assert by_code['arr']['default_value'] == [1, 2]
    assert by_code['num']['default_value'] == 42


# ── 验收标准 3：空 default_value 回读 None ──

def test_case_param_empty_stays_none(algo_detail):
    """未携带 default_value 的行回读 None（宽松语义不把空值变成别的）。"""
    by_code = _case_by_code(algo_detail)
    assert by_code['empty']['default_value'] is None


# ── 验收标准 4：同族 device / api / dimension ──

def test_device_and_api_param_non_json_text_read_back(algo_detail):
    """device / api 参数 'zh' 经各自 gRPC 读链回读原文。"""
    dev = {d['param_code']: d for d in (algo_detail.get('device_params') or [])}
    api = {a['param_code']: a for a in (algo_detail.get('api_params') or [])}
    assert dev['dev_lang']['default_value'] == 'zh'
    assert api['api_lang']['default_value'] == 'zh'


def test_dimension_param_non_json_text_and_json_form_read_back(
        api_client, auth_headers, dim_id):
    """维度参数经 evaluation_service gRPC 读链回读：'zh' 原文 + '{"k":1}' 解析对象
    （读链 GetDimensionParams → PO.to_dict 宽松语义）。"""
    detail = _data(api_client.get(f'/evaluation/dimensions/{dim_id}',
                                  headers=auth_headers))
    assert detail, f'维度详情读取失败: dim_id={dim_id}'
    inputs = {p['param_code']: p for p in (detail.get('required_inputs') or [])}
    assert inputs['dim_lang']['default_value'] == 'zh', \
        f"维度非 JSON 文本默认值读回异常: {inputs['dim_lang']}"
    assert inputs['dim_cfg']['default_value'] == {'k': 1}
