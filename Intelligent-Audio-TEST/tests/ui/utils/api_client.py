# -*- coding: utf-8 -*-
"""UI 用例 API 客户端：登录（RSA-OAEP 加密口径，对齐前端 authApi）+ 测试数据自建自清。

与 tests/api/conftest.py 的实机登录同口径：
- GET  /auth/login/encryption-key 取公钥（INT-188：加密启用时明文登录被网关拒绝）
- RSA-OAEP/SHA-256 加密密码后 POST /auth/login
- 127.0.0.1 直连（INT-102：localhost 解析 ::1 偶发误连，服务端仅绑 IPv4）
"""
import base64
import json
import time
import uuid

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# trust_env=False：忽略系统代理（INT-102 同款规避）
_client_kwargs = dict(timeout=15, trust_env=False)


class ApiError(RuntimeError):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f'HTTP {status}: {str(body)[:200]}')


class ApiClient:
    """面向 UI 测试的轻量 REST 客户端（仅测试数据准备/清理用，不做 UI 断言）。"""

    def __init__(self, api_root: str):
        self._root = api_root.rstrip('/')
        self._token = ''
        self._user = {}

    # ── 认证 ──────────────────────────────────────────────
    @property
    def token(self):
        return self._token

    @property
    def user(self):
        return self._user

    def _encryption_key(self) -> dict:
        r = httpx.get(f'{self._root}/api/v1/auth/login/encryption-key', **_client_kwargs)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _encrypt(password: str, key_doc: dict) -> dict:
        key = serialization.load_pem_public_key(key_doc['public_key'].encode())
        ct = key.encrypt(
            password.encode(),
            padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                         algorithm=hashes.SHA256(), label=None),
        )
        return {
            'password_encrypted': base64.b64encode(ct).decode(),
            'encryption_key_id': key_doc['kid'],
        }

    def login(self, username: str, password: str) -> dict:
        body = {'username': username, **self._encrypt(password, self._encryption_key())}
        r = httpx.post(f'{self._root}/api/v1/auth/login', json=body, **_client_kwargs)
        if r.status_code != 200:
            raise ApiError(r.status_code, r.text)
        data = r.json()
        self._token = data.get('access_token', '')
        self._user = data.get('user') or {}
        if not self._token:
            raise ApiError(200, f'登录响应缺少 access_token: {str(data)[:200]}')
        return data

    def register(self, username: str, password: str) -> int:
        body = {'username': username, **self._encrypt(password, self._encryption_key())}
        r = httpx.post(f'{self._root}/api/v1/auth/register', json=body, **_client_kwargs)
        if r.status_code != 200:
            raise ApiError(r.status_code, r.text)
        return (r.json().get('data') or {}).get('user_id', 0)

    def auth_mode(self) -> str:
        r = httpx.get(f'{self._root}/api/v1/auth/mode', **_client_kwargs)
        r.raise_for_status()
        return (r.json() or {}).get('auth_mode', '')

    def health(self) -> dict:
        r = httpx.get(f'{self._root}/health', **_client_kwargs)
        r.raise_for_status()
        return r.json()

    # ── 通用请求 ──────────────────────────────────────────
    def _headers(self):
        h = {}
        if self._token:
            h['Authorization'] = f'Bearer {self._token}'
        return h

    def request(self, method: str, path: str, json_body=None, **kw):
        url = path if path.startswith('http') else f'{self._root}/api/v1{path}'
        r = httpx.request(method, url, json=json_body, headers=self._headers(), **_client_kwargs, **kw)
        if r.status_code >= 400:
            raise ApiError(r.status_code, r.text)
        if not r.content:
            return {}
        try:
            return r.json()
        except ValueError:
            return r.text

    # ── 测试数据自建自清（INT-260 口径：UI 用例数据不落残留）──
    def create_group(self, name: str, description: str = '') -> str:
        data = self.request('POST', '/groups', {'name': name, 'description': description})
        return str((data.get('data') or {}).get('id', ''))

    def delete_group(self, group_id: str) -> None:
        self.request('DELETE', f'/groups/{group_id}')

    def create_tag(self, name: str, description: str = '') -> dict:
        data = self.request('POST', '/tags', {'name': name, 'description': description})
        items = data.get('data') or {}
        return items if isinstance(items, dict) and items.get('id') else items

    def delete_tag(self, tag_id) -> None:
        self.request('DELETE', f'/tags/{tag_id}')

    def create_testcase(self, name: str, group: str = '', tags=None, description: str = '') -> str:
        # 后端强制 group_id/group（创建时缺少直接 400）；id 为 UUID 字符串
        body = {'name': name, 'description': description, 'tags': tags or [],
                'group': group}
        data = self.request('POST', '/testcases', body)
        return str((data.get('data') or {}).get('id', ''))

    def delete_testcase(self, tc_id, purge: bool = True) -> None:
        # 逻辑删除（进回收站）后彻底删除，保证库内零残留
        try:
            self.request('DELETE', f'/testcases/{tc_id}')
        except ApiError:
            pass
        if purge:
            self.request('DELETE', f'/testcases/{tc_id}/purge')

    def favorite_testcase(self, tc_id, on: bool) -> None:
        self.request('POST' if on else 'DELETE', f'/testcases/{tc_id}/favorite')

    def list_favorites(self, entity: str = 'testcase') -> list:
        data = self.request('GET', '/favorites')
        favs = data.get('data') or data
        if isinstance(favs, dict):
            favs = favs.get(entity) or favs.get(f'{entity}s') or favs.get('items') or []
        return favs if isinstance(favs, list) else []


def unique_suffix() -> str:
    return f'{int(time.time())}_{uuid.uuid4().hex[:6]}'


def login_user(api_root: str, username: str, password: str) -> ApiClient:
    client = ApiClient(api_root)
    client.login(username, password)
    return client


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
