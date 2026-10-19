# -*- coding: utf-8 -*-
"""INT-848 — api_gateway schema 透传 proxy_type / proxy_url（INT-839·#3）。

网关 schema 层新增被测 API 网络代理字段（与 #1 PO 列名一致）：
- ApiItem / ApiCreateInput / ApiUpdateInput 均含 `proxy_type`（http/https/socks5/socks5h）
  与 `proxy_url`（`[user:pass@]host:port`），Optional[str]，NULL/缺省 = 不用代理。
- 网关 gRPC proxy / BFF 透传层为 JSON blob 直传（create/update 的 data 经
  json.dumps 序列化、读侧 json.loads 原样返回），schema 层放行即完成透传，
  无需改 proto —— 本卡不引入网关侧校验（后端同规则校验在 INT-846 #1）。
"""
import pytest

from api_gateway.schemas.api import ApiCreateInput, ApiItem, ApiUpdateInput

PROXY_TYPES = ('http', 'https', 'socks5', 'socks5h')
PROXY_URL_WITH_AUTH = 'user:pass@proxy.example.com:8080'


class TestApiCreateInputProxyFields:
    """ApiCreateInput 接受 proxy_type / proxy_url（snake_case 与 camelCase）。"""

    @pytest.mark.parametrize('proxy_type', PROXY_TYPES)
    def test_accepts_each_proxy_type(self, proxy_type):
        data = ApiCreateInput.model_validate({
            'name': 'API-1',
            'proxy_type': proxy_type,
            'proxy_url': PROXY_URL_WITH_AUTH,
        })
        assert data.proxy_type == proxy_type
        assert data.proxy_url == PROXY_URL_WITH_AUTH

    def test_accepts_camel_case_aliases(self):
        """前端 DTO 以 camelCase（proxyType/proxyUrl）提交时可被 schema 接受。"""
        data = ApiCreateInput.model_validate({
            'name': 'API-1',
            'proxyType': 'socks5',
            'proxyUrl': 'u@h:1080',
        })
        assert data.proxy_type == 'socks5'
        assert data.proxy_url == 'u@h:1080'

    def test_omitted_fields_default_none(self):
        """未传新字段时行为与改动前一致（回归）：proxy 字段默认 None。"""
        data = ApiCreateInput.model_validate({'name': 'API-1'})
        assert data.proxy_type is None
        assert data.proxy_url is None

    def test_dump_excludes_none_proxy_fields(self):
        """exclude_none=True 下缺省字段不进 gRPC JSON blob（透传负载与改动前一致）。"""
        dump = ApiCreateInput(name='API-1').model_dump(by_alias=False, exclude_none=True)
        assert 'proxy_type' not in dump
        assert 'proxy_url' not in dump

        dump = ApiCreateInput(
            name='API-1', proxy_type='http', proxy_url='u:p@h:8080',
        ).model_dump(by_alias=False, exclude_none=True)
        assert dump['proxy_type'] == 'http'
        assert dump['proxy_url'] == 'u:p@h:8080'


class TestApiUpdateInputProxyFields:
    """ApiUpdateInput 同样透传 proxy_type / proxy_url。"""

    @pytest.mark.parametrize('proxy_type', PROXY_TYPES)
    def test_accepts_each_proxy_type(self, proxy_type):
        data = ApiUpdateInput.model_validate({
            'proxy_type': proxy_type,
            'proxy_url': PROXY_URL_WITH_AUTH,
        })
        assert data.proxy_type == proxy_type
        assert data.proxy_url == PROXY_URL_WITH_AUTH

    def test_omitted_fields_default_none(self):
        data = ApiUpdateInput.model_validate({'name': 'API-1'})
        assert data.proxy_type is None
        assert data.proxy_url is None


class TestApiItemProxyRoundTrip:
    """round-trip：创建输入 → ApiItem 输出字段一致（验收标准 3）。"""

    @pytest.mark.parametrize(
        ('proxy_type', 'proxy_url'),
        [(t, PROXY_URL_WITH_AUTH) for t in PROXY_TYPES],
    )
    def test_create_input_to_item(self, proxy_type, proxy_url):
        create = ApiCreateInput(
            name='API-1',
            proxy_type=proxy_type,
            proxy_url=proxy_url,
        )
        # 网关 create 侧真实路径：model_dump → gRPC JSON blob
        payload = create.model_dump(by_alias=False, exclude_none=True)

        # 读侧返回（json.loads(resp.data) 原样 dict）→ 构造 ApiItem 契约
        item = ApiItem.model_validate({'id': 1, 'name': 'API-1', **payload})

        assert item.proxy_type == proxy_type
        assert item.proxy_url == proxy_url

    def test_item_omitted_proxy_fields_default_none(self):
        """老数据/无代理 API 的读回：缺省字段为 None，与改动前一致。"""
        item = ApiItem.model_validate({'id': 1, 'name': 'API-1'})
        assert item.proxy_type is None
        assert item.proxy_url is None

    def test_item_accepts_camel_case_input(self):
        """读侧若收到 camelCase 载荷，ApiItem 亦能解析（alias_generator 统一行为）。"""
        item = ApiItem.model_validate({
            'id': 1, 'name': 'API-1',
            'proxyType': 'https', 'proxyUrl': 'u:p@h:8443',
        })
        assert item.proxy_type == 'https'
        assert item.proxy_url == 'u:p@h:8443'
