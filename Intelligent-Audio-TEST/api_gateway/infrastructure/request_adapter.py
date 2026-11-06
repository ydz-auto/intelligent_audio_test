"""
Flask request 兼容适配器 —— 让旧控制器代码在 FastAPI 下无需修改即可运行。

用法：在控制器中 `from api_gateway.infrastructure.request_adapter import request`
即可替代 `from flask import request`。

原理：FastAPI 中间件将当前请求存入 ContextVar，request 适配器代理读取。
"""
from contextvars import ContextVar
from typing import Any, Optional
import json

# ContextVar 存储当前请求
_request_var: ContextVar[Any] = ContextVar('request', default=None)


def set_current_request(request: Any):
    """设置当前请求（由 FastAPI 中间件调用）"""
    _request_var.set(request)


def get_current_request() -> Optional[Any]:
    """获取当前请求"""
    return _request_var.get()


class _RequestProxy:
    """Flask request 对象的代理，兼容 FastAPI 的 Request"""

    @property
    def args(self):
        req = get_current_request()
        if req is None:
            return _EmptyDict()
        return _QueryParams(req.query_params)

    @property
    def form(self):
        req = get_current_request()
        if req is None:
            return _EmptyDict()
        return _FormProxy(req)

    @property
    def files(self):
        req = get_current_request()
        if req is None:
            return _EmptyDict()
        return _FilesProxy(req)

    @property
    def json(self):
        req = get_current_request()
        if req is None:
            return None
        # FastAPI doesn't have .json as property; need async
        # This is a sync fallback - may not work for async bodies
        return None  # Will be set by middleware if needed

    def get_json(self, silent=False):
        """同步获取 JSON body（由中间件预解析）。

        Flask 兼容参数 silent: True 时解析失败返回 None 而非抛异常。
        """
        req = get_current_request()
        if req is None:
            return None
        return getattr(req.state, '_json_body', None)

    @property
    def method(self):
        req = get_current_request()
        if req is None:
            return 'GET'
        return req.method

    @property
    def headers(self):
        req = get_current_request()
        if req is None:
            return _EmptyDict()
        return req.headers

    @property
    def content_type(self):
        req = get_current_request()
        if req is None:
            return ''
        return req.headers.get('content-type', '')

    @property
    def is_json(self):
        """Flask request.is_json 兼容：检查 content-type 是否为 application/json"""
        ct = self.content_type
        return ct.startswith('application/json')

    @property
    def username(self):
        """当前登录用户名（AuthMiddleware 注入 request.state.username；未登录为 ''）"""
        req = get_current_request()
        if req is None:
            return ''
        return getattr(req.state, 'username', '') or ''


class _QueryParams:
    """模拟 Flask 的 request.args"""

    def __init__(self, query_params):
        self._params = query_params
        # 构建多值字典（FastAPI query_params 是单值的，但同一个 key 可能出现多次）
        self._multi = {}
        if hasattr(query_params, 'multi_items'):
            for k, v in query_params.multi_items():
                self._multi.setdefault(k, []).append(v)
        else:
            for k, v in dict(query_params).items():
                self._multi[k] = [v]

    def get(self, key, default=None, type=None):
        val = self._params.get(key)
        if val is None:
            return default
        if type:
            try:
                return type(val)
            except (ValueError, TypeError):
                return default
        return val

    def getlist(self, key):
        """返回指定 key 的所有值列表（Flask 兼容）"""
        return self._multi.get(key, [])

    def __getitem__(self, key):
        return self._params[key]

    def __contains__(self, key):
        return key in self._params

    def to_dict(self):
        return dict(self._params)

    def keys(self):
        return self._params.keys()

    def values(self):
        return self._params.values()

    def items(self):
        return self._params.items()


class _FormProxy:
    """模拟 Flask 的 request.form"""

    def __init__(self, request):
        self._request = request

    def get(self, key, default=None, type=None):
        """Flask 兼容：支持 type 类型转换（如 form.get('chunk_index', type=int)），
        转换失败返回 default（INT-106：_FormProxy 缺 type 形参导致 chunk 上传 400）。"""
        val = getattr(self._request.state, '_form_data', {}).get(key, default)
        if val is None or type is None:
            return val
        try:
            return type(val)
        except (ValueError, TypeError):
            return default

    def __getitem__(self, key):
        return getattr(self._request.state, '_form_data', {})[key]

    def __contains__(self, key):
        return key in getattr(self._request.state, '_form_data', {})

    def keys(self):
        return getattr(self._request.state, '_form_data', {}).keys()

    def values(self):
        return getattr(self._request.state, '_form_data', {}).values()

    def items(self):
        return getattr(self._request.state, '_form_data', {}).items()

    def __iter__(self):
        return iter(getattr(self._request.state, '_form_data', {}))

    def __len__(self):
        return len(getattr(self._request.state, '_form_data', {}))

    def to_dict(self):
        return dict(getattr(self._request.state, '_form_data', {}))


class _UploadedFile:
    """Flask FileStorage 兼容包装：Starlette UploadFile 的同步读取视图。

    Starlette UploadFile.read 为异步，旧控制器按 Flask 语义同步调用
    file.read() / file.save()，经此包装统一。
    """

    def __init__(self, upload):
        self._upload = upload
        self.filename = getattr(upload, 'filename', None)
        self.name = getattr(upload, 'name', None)
        self.content_type = getattr(upload, 'content_type', None)
        self.file = getattr(upload, 'file', None)  # 同步文件句柄

    def read(self, *args, **kwargs):
        return self.file.read(*args, **kwargs)

    def save(self, dst, buffer_size=16384):
        import shutil
        with open(dst, 'wb') as out:
            shutil.copyfileobj(self.file, out, buffer_size)

    def close(self):
        self.file.close()


class _FilesProxy:
    """模拟 Flask 的 request.files"""

    def __init__(self, request):
        self._request = request

    def _wrap(self, value):
        if value is None or isinstance(value, _UploadedFile):
            return value
        return _UploadedFile(value)

    def __getitem__(self, key):
        return self._wrap(getattr(self._request.state, '_files', {}).get(key))

    def get(self, key, default=None):
        value = getattr(self._request.state, '_files', {}).get(key)
        return self._wrap(value) if value is not None else default

    def __contains__(self, key):
        return key in getattr(self._request.state, '_files', {})


class _EmptyDict:
    def get(self, key, default=None, type=None):
        return default

    def __getitem__(self, key):
        raise KeyError(key)

    def __contains__(self, key):
        return False

    def to_dict(self):
        return {}


# 全局 request 代理实例
request = _RequestProxy()
