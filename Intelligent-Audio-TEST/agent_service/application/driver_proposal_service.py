# -*- coding: utf-8 -*-
"""驱动 / 厂商适配器提案服务（INT-2467，方案 §6.5 / §6.5.1）。

职责（**只产提案，不执行、不注册、不发布**）：

1. ``generate_driver_from_elements``：UiAutoDev 元素树 / 操作轨迹 + 设备事实 +
   API 契约 → 确定性代码提案（设备驱动 ``AppDriver`` / 厂商 API 适配器
   ``ApiVendorAdapter`` / 成对），带文件清单、diff、依赖、风险、回滚方案、
   ``capabilities.json`` 与 manifest；
2. **静态检查**：宿主侧只做 AST / JSON 解析与契约核对（不 import、不执行生成
   代码），失败即不产生可发布产物；
3. **T2 验证**：把代码内容副本交给 ``SandboxRunner.run_untrusted_code``
   （gVisor，禁网、无凭证），阶段 = 导入/编译、单测、mock 厂商契约、
   注册表 resolve；运行时不可用即 ``T2_RUNTIME_UNAVAILABLE``，**绝不降级**；
4. ``publish_driver_proposal``：内部步骤，不是对外工具。要求**单独的
   DESTRUCTIVE 审批**且默认关闭（``AGENT_DRIVER_PUBLISH_ENABLED=false``）；
   本期只保留守卫，不写任何生产注册表。

确定性：同一输入 → 同一 ``code_sha256``（文件路径 + 内容，按路径排序）。
生成结果里没有时间戳 / 随机数 / 本机路径，重复生成可直接比对 hash。
"""
from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from agent_service.application.sandbox_runner import (
    T2SandboxRequest,
    default_validation_phases,
)
from shared.agent_tools import driver_tools
from shared.agent_tools.driver_tools import (
    ADAPTER_SUPPORTED_TRANSPORTS,
    METRIC_OWNERS,
    TARGET_API_ADAPTER,
    TARGET_DEVICE_DRIVER,
    TARGET_PAIR,
)

#: 对外工具名（唯一）；``generate_driver_from_elements`` /
#: ``publish_driver_proposal`` 是本服务的内部步骤，不是工具名。
DRIVER_PROPOSE_TOOL = 'driver_propose'

#: 提案代码来源标记（T2 审计口径；不能为空）。
CODE_SOURCE = 'driver_propose:generated'

#: 静态检查 / T2 的结论码
STATIC_OK = 'SUCCEEDED'
STATIC_FAILED = 'FAILED'
T2_RUNTIME_UNAVAILABLE = 'T2_RUNTIME_UNAVAILABLE'

#: 发布守卫的原因码
PUBLISH_DISABLED = 'PUBLISH_DISABLED'
PUBLISH_APPROVAL_REQUIRED = 'PUBLISH_APPROVAL_REQUIRED'
PUBLISH_NOT_PUBLISHABLE = 'NOT_PUBLISHABLE'
PUBLISH_UNAVAILABLE = 'PUBLISH_NOT_AVAILABLE'


@dataclass(frozen=True)
class DriverProposalSettings:
    """提案行为参数（全部可配置，不硬编码）。"""

    #: 发布开关：默认关闭（T2 隔离测试未启用前不发布，卡面执行约定）。
    publish_enabled: bool = False
    #: 工具结果里保留文件正文的预算（超出只回清单 + diff，按 hash 复现）。
    max_result_chars: int = 6000
    #: diff 预览长度上限。
    max_diff_chars: int = 4000


class DriverProposalError(ValueError):
    """提案输入 / 静态检查失败（调用方转成工具失败结果，不执行）。"""


# ======================================================================
# 代码模板（确定性；占位符替换，不用 f-string 以避开生成代码里的花括号）
# ======================================================================

_PLATFORM_STUBS = '''# -*- coding: utf-8 -*-
"""T2 沙箱内的平台契约替身（仅供提案自检；不进入生产代码）。

生成提案的驱动 / 适配器按生产契约 import 平台模块；沙箱镜像里没有业务包，
因此在这里以最小替身注入 sys.modules：ABC 契约、平台枚举、注册装饰器。
替身只记录注册键，不做任何 IO / 网络 / 凭据。
"""
import enum
import sys
import types


def _module(name):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


class DevicePlatform(str, enum.Enum):
    ANDROID = "android"
    HARMONYOS = "harmonyos"
    IOS = "ios"


class APIProtocol(str, enum.Enum):
    HTTP = "http"
    WEBSOCKET = "websocket"
    SSE = "sse"
    GRPC = "grpc"


class AdapterProtocol(str, enum.Enum):
    HTTP = "http"
    WEBSOCKET = "websocket"
    REALTIME = "realtime"
    GRPC = "grpc"
    ANY = "any"


class AdapterVendor(str, enum.Enum):
    API_DRIVER = "api_driver"
    MOCK = "mock"
    OPENAI = "openai"
    ANY = "any"


DRIVERS = {}
VENDOR_ADAPTERS = {}
REGISTERED_DRIVERS = []
REGISTERED_VENDOR_ADAPTERS = []


class AppDriver(object):
    app_type = ""
    version = ""
    platform = DevicePlatform.ANDROID
    display_name = ""
    dependencies = []

    def __init__(self, ctx=None):
        self.ctx = ctx


def register_driver(cls):
    DRIVERS[(cls.app_type, cls.version, cls.platform.name)] = cls
    REGISTERED_DRIVERS.append(cls)
    return cls


class ApiVendorAdapter(object):
    protocol = AdapterProtocol.ANY
    vendor = AdapterVendor.ANY
    supported_protocols = (APIProtocol.HTTP,)

    def __init__(self, api_config=None, case_config=None, endpoint=None,
                 test_case_id=None, task_id=None):
        self.api_config = api_config or {}


def register_vendor_adapter(cls):
    VENDOR_ADAPTERS[(cls.protocol.value, cls.vendor.value)] = cls
    REGISTERED_VENDOR_ADAPTERS.append(cls)
    return cls


for _name in (
    "device_service",
    "device_service.infrastructure",
    "device_service.infrastructure.drivers",
    "device_service.infrastructure.drivers.contracts",
    "device_service.infrastructure.drivers.driver_types",
    "device_service.infrastructure.drivers.registry",
    "api_test_service",
    "api_test_service.domain",
    "api_test_service.domain.ports",
    "api_test_service.domain.ports.api_vendor_adapter",
    "api_test_service.infrastructure",
    "api_test_service.infrastructure.adapters",
    "api_test_service.infrastructure.adapters.registry",
    "shared",
    "shared.models",
    "shared.models.common_enums",
):
    _module(_name)

_module("device_service.infrastructure.drivers.contracts").AppDriver = AppDriver
_module("device_service.infrastructure.drivers.driver_types").DevicePlatform = (
    DevicePlatform)
_module("device_service.infrastructure.drivers.registry").register_driver = (
    register_driver)
_module("api_test_service.domain.ports.api_vendor_adapter").ApiVendorAdapter = (
    ApiVendorAdapter)
_module("api_test_service.infrastructure.adapters.registry").\
    register_vendor_adapter = register_vendor_adapter
_common = _module("shared.models.common_enums")
_common.AdapterProtocol = AdapterProtocol
_common.AdapterVendor = AdapterVendor
_common.APIProtocol = APIProtocol
'''

_DRIVER_TEMPLATE = '''# -*- coding: utf-8 -*-
"""__DISPLAY_NAME__ 设备驱动（driver_propose 生成的**待评审提案**）。

未注册到生产注册表、未发布。合并需人工评审 + 单独的 DESTRUCTIVE 审批。
驱动只采集文本 / 音频 / 时序；WER / CER / MOS 等指标由 algorithm_service /
evaluation_service 计算，不在驱动里算。
"""
from device_service.infrastructure.drivers.contracts import AppDriver
from device_service.infrastructure.drivers.driver_types import DevicePlatform
from device_service.infrastructure.drivers.registry import register_driver

#: 能力画像与结果字段（与同目录 capabilities.json 一致，capabilities.json 是事实源）
RESULT_FIELDS = __RESULT_FIELDS__
CAPTURE_MODES = __CAPTURE_MODES__
TIMING_POINTS = __TIMING_POINTS__


@register_driver
class __CLASS_NAME__(AppDriver):
    app_type = "__APP_TYPE__"
    version = "__VERSION__"
    platform = DevicePlatform.__PLATFORM__
    display_name = "__DISPLAY_NAME__"
    dependencies = []

    # ---- 生命周期 ----
    def initialize(self, device_sn, **kwargs):
        """解锁 / 启动 App（按 ui_trace 的入口动作补全）。"""
        raise NotImplementedError(
            "提案桩：initialize 需接入平台原子能力（unlock / 启动 App）")

    def pre_process(self, device_sn, **kwargs):
        """进入功能页面（按 ui_trace 的页面树与 stable locator 补全）。"""
        raise NotImplementedError("提案桩：pre_process 需按 ui_trace 进入功能页面")

    def get_results(self, device_sn, **kwargs):
        """采集一轮结果；只取 CAPTURE_MODES 声明的通道。"""
        raise NotImplementedError(
            "提案桩：get_results 需按 capabilities.capture_modes 采集")

    def teardown(self, device_sn, **kwargs):
        return True

    # ---- 结果解析（已实现骨架：把采集原样映射到结果契约，不重算指标） ----
    def parse_result(self, raw):
        raw = raw or {}
        result = {field: None for field in RESULT_FIELDS}
        result.update({
            "success": bool(raw.get("success", True)),
            "message": raw.get("message") or "",
            "text": raw.get("text"),
            "asr": raw.get("asr") if raw.get("asr") is not None else raw.get("text"),
            "question": raw.get("question"),
            "answer": raw.get("answer"),
            "wav_path": raw.get("wav_path"),
            "user_wav": raw.get("user_wav"),
            "ai_wav": raw.get("ai_wav"),
            "record_path": raw.get("record_path"),
            "start_ms": raw.get("start_ms"),
            "end_ms": raw.get("end_ms"),
            "first_frame_ms": raw.get("first_frame_ms"),
            "latency_ms": raw.get("latency_ms"),
        })
        return result

    # ---- 元素定位（稳定标识优先，文本退化要能解释） ----
    @staticmethod
    def locator_summary(locator):
        locator = locator or {}
        if locator.get("resource_id"):
            return ("resource_id", locator["resource_id"])
        if locator.get("key"):
            return ("key", locator["key"])
        if locator.get("text") or locator.get("label"):
            return ("text", locator.get("text") or locator.get("label"))
        return ("none", None)
'''

_ADAPTER_TEMPLATE = '''# -*- coding: utf-8 -*-
"""__DISPLAY_NAME__ 厂商 API 适配器（driver_propose 生成的**待评审提案**）。

未注册到生产注册表、未发布。合并需人工评审 + 单独的 DESTRUCTIVE 审批。
只做厂商报文渲染与调用编排；不操作 UI、不写算法指标。
"""
from shared.models.common_enums import AdapterProtocol, AdapterVendor, APIProtocol
from api_test_service.domain.ports.api_vendor_adapter import ApiVendorAdapter
from api_test_service.infrastructure.adapters.registry import (
    register_vendor_adapter,
)

#: 契约声明的鉴权头（缺失时用 Authorization）
AUTH_HEADER = "__AUTH_HEADER__"


@register_vendor_adapter
class __CLASS_NAME__(ApiVendorAdapter):
    protocol = AdapterProtocol.__PROTOCOL__
    vendor = AdapterVendor.__VENDOR__
    supported_protocols = (__SUPPORTED_PROTOCOLS__,)

    def render_request_parts(self, context_data):
        """按厂商契约渲染请求头与请求体（骨架）。"""
        context_data = context_data or {}
        headers = dict(context_data.get("headers") or {})
        auth = context_data.get("auth") or {}
        token = auth.get("token")
        if token:
            headers.setdefault(AUTH_HEADER, "Bearer %s" % token)
        return headers, dict(context_data.get("body") or {})

    def execute(self, context_data, files=None, method=None):
        """执行一次厂商调用（提案桩：接厂商 SDK / HTTP 客户端后实现）。"""
        raise NotImplementedError(
            "提案桩：execute 需接入厂商 SDK / HTTP 客户端，并按契约解析响应")
'''

_CONTRACT_TEST_TEMPLATE = '''# -*- coding: utf-8 -*-
"""mock 厂商契约测试（提案自带；T2 阶段运行）。"""
import sys
import unittest

sys.path.insert(0, "/input")
sys.path.insert(0, "/input/tests")

import _platform_stubs  # noqa: F401  注入平台契约替身

import __MODULE_NAME__ as adapter_module


class VendorContractTest(unittest.TestCase):
    def test_declares_protocol_and_vendor(self):
        cls = adapter_module.__CLASS_NAME__
        self.assertEqual(cls.protocol.value, "__PROTOCOL_VALUE__")
        self.assertEqual(cls.vendor.value, "__VENDOR_VALUE__")

    def test_render_request_parts_returns_headers_and_body(self):
        adapter = adapter_module.__CLASS_NAME__(api_config={})
        headers, body = adapter.render_request_parts(
            {"body": {"input": "hello"}, "auth": {"token": "t-1"}})
        self.assertIsInstance(headers, dict)
        self.assertEqual(headers.get(adapter_module.AUTH_HEADER),
                         "Bearer t-1")
        self.assertEqual(body, {"input": "hello"})

    def test_execute_is_documented_stub(self):
        adapter = adapter_module.__CLASS_NAME__(api_config={})
        with self.assertRaises(NotImplementedError):
            adapter.execute({})


if __name__ == "__main__":
    unittest.main()
'''

_DRIVER_TEST_TEMPLATE = '''# -*- coding: utf-8 -*-
"""设备驱动提案单测（提案自带；T2 阶段运行）。"""
import json
import sys
import unittest

sys.path.insert(0, "/input")
sys.path.insert(0, "/input/tests")

import _platform_stubs  # noqa: F401  注入平台契约替身
from _platform_stubs import DRIVERS, DevicePlatform

import __MODULE_NAME__ as driver_module


class DeviceDriverProposalTest(unittest.TestCase):
    def test_registered_with_expected_key(self):
        key = ("__APP_TYPE__", "__VERSION__", "__PLATFORM__")
        self.assertIn(key, DRIVERS)
        self.assertIs(DRIVERS[key], driver_module.__CLASS_NAME__)

    def test_metadata_matches_inputs(self):
        cls = driver_module.__CLASS_NAME__
        self.assertEqual(cls.app_type, "__APP_TYPE__")
        self.assertEqual(cls.version, "__VERSION__")
        self.assertEqual(cls.platform, DevicePlatform.__PLATFORM__)
        self.assertTrue(cls.display_name)

    def test_capabilities_file_is_complete(self):
        with open("/input/capabilities.json", encoding="utf-8") as handle:
            capabilities = json.load(handle)
        for key in ("stimulus_modes", "capture_modes", "timing_points",
                    "result_fields", "supported_metrics", "limitations"):
            self.assertIn(key, capabilities)
        self.assertTrue(capabilities["supported_metrics"])

    def test_parse_result_covers_declared_fields(self):
        driver = driver_module.__CLASS_NAME__()
        result = driver.parse_result({"text": "hello", "latency_ms": 120})
        self.assertTrue(result["success"])
        for field in driver_module.RESULT_FIELDS:
            self.assertIn(field, result)

    def test_lifecycle_requires_real_implementation(self):
        driver = driver_module.__CLASS_NAME__()
        with self.assertRaises(NotImplementedError):
            driver.initialize("serial-1")


if __name__ == "__main__":
    unittest.main()
'''

_RESOLVE_SCRIPT_TEMPLATE = '''# -*- coding: utf-8 -*-
"""注册表 resolve 自检（提案自带；T2 阶段运行）。

模拟生产注册表：(app_type, version, platform) 解析设备驱动，
(protocol, vendor) 解析厂商适配器。失败即退出码 1。
"""
import sys

sys.path.insert(0, "/input")
sys.path.insert(0, "/input/tests")

import _platform_stubs  # noqa: F401  注入平台契约替身
from _platform_stubs import DRIVERS, VENDOR_ADAPTERS

__IMPORTS__


def main():
    failures = []
__CHECKS__
    if failures:
        for line in failures:
            print("registry_resolve: " + line)
        return 1
    print("registry_resolve: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

_README_TEMPLATE = '''# 驱动提案（__TARGET_KIND__）

由 `driver_propose` 生成的**待评审代码提案**。不执行、不注册、不发布。

## 文件清单

__FILE_LIST__

## 依赖

__DEPENDENCIES__

## 风险

__RISKS__

## 回滚方案

__ROLLBACK__

## 验证

- 静态检查：宿主侧 AST / JSON / 契约核对（不执行代码）；
- T2 沙箱：导入/编译、单测、mock 厂商契约、注册表 resolve（gVisor，禁网）；
- 结论与代码 hash 见工具结果的 `validation_report`（同输入可复现同一 hash）。

## 合并与发布

- 评审通过后只能保存为草稿 / 分支 / PR；
- 合并与注册到生产需**单独的 DESTRUCTIVE 审批**；本期发布开关默认关闭
  （`AGENT_DRIVER_PUBLISH_ENABLED=false`），不写生产注册表。
'''


# ======================================================================
# 生成器
# ======================================================================


def _slug(value: str, *, fallback: str = 'artifact') -> str:
    text = ''.join(ch if (ch.isalnum() or ch == '_') else '_'
                   for ch in str(value or '').strip().lower())
    text = '_'.join(part for part in text.split('_') if part)
    return text or fallback


def _camel(value: str, *, suffix: str = '') -> str:
    parts = [part for part in _slug(value).split('_') if part]
    name = ''.join(part[:1].upper() + part[1:] for part in parts) or 'Generated'
    if name[0].isdigit():
        name = 'X' + name
    return name + suffix


def _code_text(value: Any, *, limit: int = 120) -> str:
    """把用户输入安全地嵌进生成的 Python 字符串字面量（去引号 / 换行 / 反斜杠）。"""
    text = str(value or '')
    text = text.replace('\\', '/')
    text = text.replace('"', "'")
    text = text.replace('\r', ' ').replace('\n', ' ')
    return text.strip()[:limit]


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def canonical_code_sha256(files: Mapping[str, str]) -> str:
    """代码包 hash（路径 + 内容，按路径排序，带分隔符防拼接歧义）。"""
    digest = hashlib.sha256()
    for relative in sorted(files):
        digest.update(relative.encode('utf-8'))
        digest.update(b'\x00')
        digest.update(files[relative].encode('utf-8'))
        digest.update(b'\x00')
    return digest.hexdigest()


def _render(template: str, values: Mapping[str, str]) -> str:
    text = template
    for key, value in values.items():
        text = text.replace(key, value)
    return text


def _python_literal_list(values: Sequence[str]) -> str:
    return '(' + ''.join("'%s', " % value for value in values) + ')' \
        if values else '()'


def _auth_header(contract: Mapping[str, Any]) -> str:
    auth = contract.get('auth') if isinstance(contract, dict) else None
    if isinstance(auth, dict):
        for key in ('header', 'header_name', 'name'):
            value = auth.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return 'Authorization'


def _contract_summary(contract: Any) -> Dict[str, Any]:
    """契约摘要（只保留提案评审需要的结构，不复制整份契约）。"""
    if not isinstance(contract, dict):
        return {}
    endpoints = contract.get('endpoints')
    names: List[str] = []
    if isinstance(endpoints, list):
        for item in endpoints:
            if isinstance(item, dict):
                names.append(str(item.get('path') or item.get('name') or ''))
            elif isinstance(item, str):
                names.append(item)
    return {
        'endpoints': [name for name in names if name],
        'auth_header': _auth_header(contract),
        'has_samples': bool(contract.get('samples') or contract.get('examples')),
    }


def _driver_module_name(app_type: str, version: str) -> str:
    return f'drivers/{_slug(app_type)}_{_slug(version)}_driver.py'


def _adapter_module_name(vendor: str, protocol: str) -> str:
    return f'adapters/{_slug(vendor)}_{_slug(protocol)}_adapter.py'


def _module_import_name(path: str) -> str:
    return path[:-3].replace('/', '.') if path.endswith('.py') else path


class DriverProposalService:
    """驱动 / 适配器提案（确定性生成 + 静态检查 + T2 验证 + 发布守卫）。"""

    def __init__(self, *, sandbox_runner=None,
                 settings: Optional[DriverProposalSettings] = None):
        # sandbox_runner: ``SandboxRunner``（装配 T2 执行器时才有）。None =
        # T2 不可用，按 T2_RUNTIME_UNAVAILABLE 显式失败，不降级。
        self._sandbox = sandbox_runner
        self._settings = settings or DriverProposalSettings()

    # ------------------------------------------------------------ 校验

    def validate(self, arguments: Dict[str, Any]) -> Optional[str]:
        """提案前的材料 / 能力画像校验；返回错误文本或 ``None``。

        与 ``generate`` 用同一套规则：**提案阶段就拒绝**缺材料 / 指标算不出来的
        调用，避免「批准后才发现参数不合法」。
        """
        arguments = dict(arguments or {})
        target_kind = str(arguments.get('target_kind') or '').strip().upper()
        error = driver_tools.validate_target_inputs(target_kind, arguments)
        if error:
            return error
        error = driver_tools.validate_capabilities(arguments.get('capabilities'))
        if error:
            return error
        if target_kind in (TARGET_DEVICE_DRIVER, TARGET_PAIR):
            error = driver_tools.check_platform(arguments.get('platform'))
            if error:
                return error
            error = driver_tools.validate_ui_trace(
                arguments.get('ui_trace'), required=True)
            if error:
                return error
        if target_kind in (TARGET_API_ADAPTER, TARGET_PAIR):
            error = driver_tools.check_adapter_dimensions(
                arguments.get('protocol'), arguments.get('vendor'))
            if error:
                return error
            if not isinstance(arguments.get('contract'), dict):
                return ('参数 contract 必须是对象（端点 / 鉴权 / 请求响应样例）')
        return None

    # ------------------------------------------------------------ 生成

    def generate(self, arguments: Dict[str, Any], *,
                 run_id: str = '') -> Dict[str, Any]:
        """对外入口：校验材料 → 生成代码 → 静态检查 → T2 → 提案载荷。

        输入非法抛 ``DriverProposalError``（由 ToolGateway 转成普通失败结果，
        不产生任何产物）。
        """
        arguments = dict(arguments or {})
        error = self.validate(arguments)
        if error:
            raise DriverProposalError(error)
        target_kind = str(arguments.get('target_kind') or '').strip().upper()
        generated = self._build(arguments, target_kind)
        static = self._static_check(generated['files'], generated['expects'])
        t2 = self._run_t2(generated['files'], generated['code_sha256'], run_id,
                          has_adapter='adapter' in generated['expects'])
        publishable = (static['outcome'] == STATIC_OK
                       and t2.get('outcome') == 'SUCCEEDED')
        return self._payload(arguments, target_kind, generated, static, t2,
                             publishable)

    # ------------------------------------------------------------ 内部步骤

    def generate_driver_from_elements(self, arguments: Dict[str, Any], *,
                                      run_id: str = '') -> Dict[str, Any]:
        """内部步骤名（§6.5）：等价于 ``generate``，不是对外工具。"""
        return self.generate(arguments, run_id=run_id)

    def publish_driver_proposal(self, proposal: Mapping[str, Any], *,
                                approval_id: str = '',
                                approval_status: str = '') -> Dict[str, Any]:
        """发布守卫（内部步骤，不是对外工具）。

        必须同时满足：发布开关打开、有已批准的 **DESTRUCTIVE** 审批单、
        提案 ``publishable=true``。本期开关默认关闭、也没有写生产注册表的
        通道，因此即使前三项满足也只返回不可用 —— 未审批绝不写注册表。
        """
        if not self._settings.publish_enabled:
            return {'published': False, 'reason': PUBLISH_DISABLED,
                    'message': '发布开关未启用（AGENT_DRIVER_PUBLISH_ENABLED=false）；'
                               '本期只产出提案，不写生产注册表。'}
        if not approval_id or str(approval_status).upper() != 'APPROVED':
            return {'published': False, 'reason': PUBLISH_APPROVAL_REQUIRED,
                    'message': '需要已批准的 DESTRUCTIVE 审批单才能发布。'}
        report = proposal.get('validation_report') or {}
        if not report.get('publishable'):
            return {'published': False, 'reason': PUBLISH_NOT_PUBLISHABLE,
                    'message': '静态检查或 T2 验证未通过，不产生可发布产物。'}
        return {'published': False, 'reason': PUBLISH_UNAVAILABLE,
                'message': '本期未开放注册表写入通道；请走人工合并 + 发布审批。'}

    # ---- 代码生成 ----

    def _build(self, arguments: Dict[str, Any], target_kind: str
               ) -> Dict[str, Any]:
        capabilities = driver_tools.normalize_capabilities(
            arguments['capabilities'])
        with_driver = target_kind in (TARGET_DEVICE_DRIVER, TARGET_PAIR)
        with_adapter = target_kind in (TARGET_API_ADAPTER, TARGET_PAIR)

        files: Dict[str, str] = {
            'capabilities.json': _json(capabilities),
            'tests/_platform_stubs.py': _PLATFORM_STUBS,
        }
        expects: Dict[str, Any] = {'artifacts': []}
        artifacts: List[Dict[str, Any]] = []

        if with_driver:
            error = driver_tools.check_platform(arguments.get('platform'))
            if error:
                raise DriverProposalError(error)
            error = driver_tools.validate_ui_trace(
                arguments.get('ui_trace'), required=True)
            if error:
                raise DriverProposalError(error)
            app_type = str(arguments.get('app_type')).strip()
            version = str(arguments.get('version')).strip()
            platform = str(arguments.get('platform')).strip().upper()
            display_name = _code_text(
                arguments.get('display_name') or f'{app_type} {version}')
            class_name = _camel(f'{app_type}_{version}', suffix='Driver')
            module = _driver_module_name(app_type, version)
            files[module] = _render(_DRIVER_TEMPLATE, {
                '__DISPLAY_NAME__': display_name,
                '__CLASS_NAME__': class_name,
                '__APP_TYPE__': _code_text(app_type),
                '__VERSION__': _code_text(version),
                '__PLATFORM__': platform,
                '__RESULT_FIELDS__': _python_literal_list(
                    capabilities['result_fields']),
                '__CAPTURE_MODES__': _python_literal_list(
                    capabilities['capture_modes']),
                '__TIMING_POINTS__': _python_literal_list(
                    capabilities['timing_points']),
            })
            files['tests/test_device_driver.py'] = _render(
                _DRIVER_TEST_TEMPLATE, {
                    '__MODULE_NAME__': _module_import_name(module),
                    '__CLASS_NAME__': class_name,
                    '__APP_TYPE__': _code_text(app_type),
                    '__VERSION__': _code_text(version),
                    '__PLATFORM__': platform,
                })
            artifacts.append({
                'artifact_kind': TARGET_DEVICE_DRIVER,
                'artifact_id': f'{TARGET_DEVICE_DRIVER}:{module}',
                'module': module,
                'class': class_name,
                'display_name': display_name,
                'registry_key': {
                    'app_type': _code_text(app_type),
                    'version': _code_text(version),
                    'platform': platform},
            })
            expects['driver'] = {
                'module': module, 'class': class_name,
                'app_type': _code_text(app_type),
                'version': _code_text(version), 'platform': platform,
            }

        if with_adapter:
            error = driver_tools.check_adapter_dimensions(
                arguments.get('protocol'), arguments.get('vendor'))
            if error:
                raise DriverProposalError(error)
            protocol = str(arguments.get('protocol')).strip().lower()
            vendor = str(arguments.get('vendor')).strip().lower()
            contract = arguments.get('contract')
            if not isinstance(contract, dict):
                raise DriverProposalError(
                    '参数 contract 必须是对象（端点 / 鉴权 / 请求响应样例）')
            summary = _contract_summary(contract)
            api_id = arguments.get('api_id')
            class_name = _camel(f'{vendor}_{protocol}', suffix='Adapter')
            module = _adapter_module_name(vendor, protocol)
            transports = ADAPTER_SUPPORTED_TRANSPORTS.get(protocol, ('HTTP',))
            files[module] = _render(_ADAPTER_TEMPLATE, {
                '__DISPLAY_NAME__': _code_text(f'{vendor} {protocol}'),
                '__CLASS_NAME__': class_name,
                '__PROTOCOL__': protocol.upper(),
                '__VENDOR__': vendor.upper(),
                '__SUPPORTED_PROTOCOLS__': ', '.join(
                    f'APIProtocol.{item}' for item in transports),
                '__AUTH_HEADER__': _code_text(summary['auth_header'], limit=60),
            })
            files[f'tests/test_contract_{_slug(vendor)}.py'] = _render(
                _CONTRACT_TEST_TEMPLATE, {
                    '__MODULE_NAME__': _module_import_name(module),
                    '__CLASS_NAME__': class_name,
                    '__PROTOCOL_VALUE__': protocol,
                    '__VENDOR_VALUE__': vendor,
                })
            artifacts.append({
                'artifact_kind': TARGET_API_ADAPTER,
                'artifact_id': f'{TARGET_API_ADAPTER}:{module}',
                'module': module,
                'class': class_name,
                'api_id': api_id,
                'registry_key': {'protocol': protocol, 'vendor': vendor},
                'contract': summary,
            })
            expects['adapter'] = {
                'module': module, 'class': class_name,
                'protocol': protocol, 'vendor': vendor,
            }

        # 成对交付：manifest 互相引用（PAIR 时两个 artifact 各自带 pair_with）
        if len(artifacts) == 2:
            artifacts[0]['pair_with'] = artifacts[1]['artifact_id']
            artifacts[1]['pair_with'] = artifacts[0]['artifact_id']

        imports: List[str] = []
        checks: List[str] = []
        if with_driver:
            imports.append(
                'from %s import %s' % (
                    _module_import_name(expects['driver']['module']),
                    expects['driver']['class']))
            checks.extend([
                '    driver = DRIVERS.get(("%s", "%s", "%s"))' % (
                    expects['driver']['app_type'],
                    expects['driver']['version'],
                    expects['driver']['platform']),
                '    if driver is not %s:' % expects['driver']['class'],
                '        failures.append("设备驱动未按 (app_type, version, '
                'platform) resolve")',
            ])
        if with_adapter:
            imports.append(
                'from %s import %s' % (
                    _module_import_name(expects['adapter']['module']),
                    expects['adapter']['class']))
            checks.extend([
                '    adapter = VENDOR_ADAPTERS.get(("%s", "%s"))' % (
                    expects['adapter']['protocol'],
                    expects['adapter']['vendor']),
                '    if adapter is not %s:' % expects['adapter']['class'],
                '        failures.append("API 适配器未按 (protocol, vendor) '
                'resolve")',
            ])
        files['tests/registry_resolve.py'] = _render(
            _RESOLVE_SCRIPT_TEMPLATE, {
                '__IMPORTS__': '\n'.join(imports),
                '__CHECKS__': '\n'.join(checks),
            })

        expects['artifacts'] = list(artifacts)
        manifest = {
            'target_kind': target_kind,
            'artifacts': artifacts,
            'capabilities': 'capabilities.json',
            'validation': {
                'static_check': '宿主侧 AST / JSON / 契约核对（不执行代码）',
                't2_phases': ['import_compile', 'unit_test', 'mock_contract',
                              'registry_resolve'],
            },
        }
        files['manifest.json'] = _json(manifest)

        dependencies = self._dependencies(capabilities, with_driver,
                                           with_adapter)
        risks = self._risks(capabilities, arguments)
        rollback = [
            '提案未合并前：删除提案分支即可，生产无变化。',
            '合并后：驱动注册是装饰器注册，回滚方式为移除注册并 reload '
            '`device_service.infrastructure.drivers.<module>`。',
            '适配器回滚：从 `vendor_adapter_registry` unregister 并恢复用例 '
            '`vendor_adapter` 配置的上一取值。',
            '设备动作不可回滚（重启 / 安装 / 卸载会改变设备状态），'
            '提案评审必须先确认设备占用与回退窗口。',
        ]
        files['README.md'] = _render(_README_TEMPLATE, {
            '__TARGET_KIND__': target_kind,
            '__FILE_LIST__': '\n'.join(
                f'- `{path}`' for path in sorted(files)),
            '__DEPENDENCIES__': '\n'.join(f'- {item}' for item in dependencies),
            '__RISKS__': '\n'.join(f'- {item}' for item in risks),
            '__ROLLBACK__': '\n'.join(f'- {item}' for item in rollback),
        })
        # code hash 覆盖全部文件（README 不写 hash 自身，避免自引用）。
        code_sha256 = canonical_code_sha256(files)
        return {
            'files': files,
            'expects': expects,
            'artifacts': artifacts,
            'manifest': manifest,
            'dependencies': dependencies,
            'risks': risks,
            'rollback': rollback,
            'code_sha256': code_sha256,
        }

    @staticmethod
    def _dependencies(capabilities: Mapping[str, Any], with_driver: bool,
                      with_adapter: bool) -> List[str]:
        deps: List[str] = ['python3（T2 镜像 python:3.11-slim）']
        if with_driver:
            deps.append('device_service.infrastructure.drivers（AppDriver / '
                        'register_driver / DevicePlatform）')
            if set(capabilities.get('capture_modes') or ()) & {
                    'SCREEN_RECORD', 'PCM_CAPTURE'}:
                deps.append('音频采集依赖（录屏 / PCM 抓取）由平台既有 '
                            'HarmonyCollectionMixin 等设施提供')
            if 'ACOUSTIC_PLAYBACK' in (capabilities.get('stimulus_modes') or ()):
                deps.append('播放链路：audio_service / 播放设备（SPL 与增益由既有配置）')
        if with_adapter:
            deps.append('api_test_service.infrastructure.adapters（ApiVendorAdapter '
                        '/ register_vendor_adapter / AdapterProtocol / AdapterVendor）')
        return deps

    @staticmethod
    def _risks(capabilities: Mapping[str, Any],
               arguments: Mapping[str, Any]) -> List[str]:
        risks: List[str] = []
        captures = set(capabilities.get('capture_modes') or ())
        metrics = list(capabilities.get('supported_metrics') or ())
        if 'SCREEN_RECORD' in captures and not (
                captures & {'UI_TEXT', 'APP_EXPORT', 'API_RESPONSE'}):
            risks.append('只能录屏：ASR 文本需额外识别步骤，WER/CER 置信度低于文本通道。')
        if not (captures & {'SCREEN_RECORD', 'PCM_CAPTURE', 'API_RESPONSE'}):
            risks.append('无音频采集：无法评 TTS 音质（TTS_QUALITY 不可计算）。')
        if 'PCM_CAPTURE' not in captures:
            risks.append('无 PCM 抓取：打断（BARGE_IN）与低延迟评测不可用。')
        if 'TEXT_INPUT' in (capabilities.get('stimulus_modes') or ()) and \
                'ACOUSTIC_PLAYBACK' not in (capabilities.get('stimulus_modes') or ()):
            risks.append('仅文本激励：不覆盖声学播放链路，ASR/TTS 端到端时延不代表真机。')
        for metric in metrics:
            owner = METRIC_OWNERS.get(metric)
            if owner:
                risks.append(f'{metric} 由 {owner} 计算；驱动只采集，'
                             '指标口径以算法 / 评估服务的接口返回为准。')
        if arguments.get('target_kind') in (TARGET_API_ADAPTER, TARGET_PAIR):
            risks.append('厂商契约变更（端点 / 鉴权 / 帧格式）需要同步改适配器；'
                         'mock 契约测试只校验骨架，不替代真实厂商联调。')
        if not risks:
            risks.append('无额外风险项；仍需人工评审生成代码与契约一致性。')
        return risks

    # ---- 静态检查（不执行生成代码） ----

    def _static_check(self, files: Mapping[str, str],
                      expects: Mapping[str, Any]) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []
        errors: List[str] = []

        syntax_ok = True
        for path in sorted(files):
            if not path.endswith('.py'):
                continue
            try:
                ast.parse(files[path], filename=path)
            except SyntaxError as exc:
                syntax_ok = False
                errors.append(f'{path} 语法错误：{exc.msg}（第 {exc.lineno} 行）')
        checks.append({'check': 'python_syntax', 'passed': syntax_ok,
                       'detail': f'{sum(1 for p in files if p.endswith(".py"))} 个 Python 文件'})

        json_ok = True
        parsed: Dict[str, Any] = {}
        for path in ('capabilities.json', 'manifest.json'):
            try:
                parsed[path] = json.loads(files[path])
            except (KeyError, ValueError) as exc:
                json_ok = False
                errors.append(f'{path} 非法 JSON：{exc}')
        checks.append({'check': 'json_parse', 'passed': json_ok,
                       'detail': 'capabilities.json / manifest.json'})

        if json_ok:
            capabilities = parsed['capabilities.json']
            capability_error = driver_tools.validate_capabilities(capabilities)
            checks.append({'check': 'capabilities_contract',
                           'passed': capability_error is None,
                           'detail': capability_error or '能力画像字段齐全'})
            if capability_error:
                errors.append(capability_error)
            manifest = parsed['manifest.json']
            manifest_ok = (
                isinstance(manifest.get('artifacts'), list)
                and len(manifest['artifacts']) == len(expects['artifacts'])
                and manifest.get('target_kind'))
            checks.append({'check': 'manifest_contract', 'passed': manifest_ok,
                           'detail': 'artifacts / target_kind'})
            if not manifest_ok:
                errors.append('manifest.json 与生成产物不一致')

        driver_error = self._check_driver_contract(files, expects)
        if 'driver' in expects:
            checks.append({'check': 'device_driver_contract',
                           'passed': driver_error is None,
                           'detail': driver_error or '@register_driver + 元数据一致'})
            if driver_error:
                errors.append(driver_error)
        adapter_error = self._check_adapter_contract(files, expects)
        if 'adapter' in expects:
            checks.append({'check': 'api_adapter_contract',
                           'passed': adapter_error is None,
                           'detail': adapter_error or '@register_vendor_adapter + 维度一致'})
            if adapter_error:
                errors.append(adapter_error)

        return {'outcome': STATIC_FAILED if errors else STATIC_OK,
                'checks': checks, 'errors': errors}

    @staticmethod
    def _class_defs(tree: ast.AST) -> List[ast.ClassDef]:
        return [node for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef)]

    @staticmethod
    def _decorator_names(node: ast.ClassDef) -> List[str]:
        names: List[str] = []
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(target, ast.Name):
                names.append(target.id)
            elif isinstance(target, ast.Attribute):
                names.append(target.attr)
        return names

    @staticmethod
    def _class_assignments(node: ast.ClassDef) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            for target in stmt.targets:
                if not isinstance(target, ast.Name):
                    continue
                value = stmt.value
                if isinstance(value, ast.Constant):
                    values[target.id] = value.value
                elif isinstance(value, ast.Attribute):
                    values[target.id] = value.attr
        return values

    def _check_driver_contract(self, files: Mapping[str, str],
                               expects: Mapping[str, Any]) -> Optional[str]:
        expected = expects.get('driver')
        if not expected:
            return None
        source = files.get(expected['module'])
        if source is None:
            return f'缺少设备驱动模块：{expected["module"]}'
        tree = ast.parse(source, filename=expected['module'])
        for node in self._class_defs(tree):
            if node.name != expected['class']:
                continue
            if 'register_driver' not in self._decorator_names(node):
                return f'{node.name} 缺少 @register_driver'
            values = self._class_assignments(node)
            for key in ('app_type', 'version', 'platform'):
                if values.get(key) != expected[key]:
                    return (f'{node.name}.{key} 与输入不一致：'
                            f'{values.get(key)!r} != {expected[key]!r}')
            return None
        return f'未找到驱动类 {expected["class"]}'

    def _check_adapter_contract(self, files: Mapping[str, str],
                                expects: Mapping[str, Any]) -> Optional[str]:
        expected = expects.get('adapter')
        if not expected:
            return None
        source = files.get(expected['module'])
        if source is None:
            return f'缺少适配器模块：{expected["module"]}'
        tree = ast.parse(source, filename=expected['module'])
        for node in self._class_defs(tree):
            if node.name != expected['class']:
                continue
            if 'register_vendor_adapter' not in self._decorator_names(node):
                return f'{node.name} 缺少 @register_vendor_adapter'
            values = self._class_assignments(node)
            if str(values.get('protocol') or '').lower() != expected['protocol']:
                return (f'{node.name}.protocol 与输入不一致：'
                        f'{values.get("protocol")!r}')
            if str(values.get('vendor') or '').lower() != expected['vendor']:
                return (f'{node.name}.vendor 与输入不一致：'
                        f'{values.get("vendor")!r}')
            methods = {item.name for item in node.body
                       if isinstance(item, ast.FunctionDef)}
            for method in ('render_request_parts', 'execute'):
                if method not in methods:
                    return f'{node.name} 缺少 {method}'
            return None
        return f'未找到适配器类 {expected["class"]}'

    # ---- T2 验证 ----

    #: 厂商契约阶段只在提案含 API 适配器时执行（设备驱动没有厂商契约；
    #: 空 discover 在部分 Python 版本返回非零，会误判成验证失败）。
    MOCK_CONTRACT_PHASE = 'mock_contract'

    def _run_t2(self, files: Mapping[str, str], code_sha256: str,
                run_id: str, *, has_adapter: bool) -> Dict[str, Any]:
        if self._sandbox is None:
            return {
                'outcome': STATIC_FAILED,
                'reason': T2_RUNTIME_UNAVAILABLE,
                'detail': ('未装配 T2 执行器（gVisor runsc 不可用）；'
                           '按方案 §7 不降级到 T1，提案不可发布。'),
                'runtime': '',
                'succeeded': False,
                'phases': [],
            }
        phases = default_validation_phases()
        if not has_adapter:
            phases = tuple(phase for phase in phases
                           if phase.name != self.MOCK_CONTRACT_PHASE)
        request = T2SandboxRequest(
            code_source=CODE_SOURCE, files=dict(files), phases=phases,
            run_id=run_id, code_sha256=code_sha256)
        result = self._sandbox.run_untrusted_code(request)
        return {
            'outcome': getattr(getattr(result, 'outcome', None), 'value', 'FAILED'),
            'reason': getattr(getattr(result, 'reason', None), 'value', 'NONE'),
            'detail': getattr(result, 'detail', '') or '',
            'runtime': getattr(result, 'runtime', '') or '',
            'succeeded': bool(getattr(result, 'succeeded', False)),
            'code_sha256': getattr(result, 'code_sha256', '') or '',
            'phases': [
                {
                    'name': phase.name,
                    'outcome': getattr(getattr(phase, 'outcome', None), 'value', ''),
                    'reason': getattr(getattr(phase, 'reason', None), 'value', ''),
                    'exit_code': getattr(phase, 'exit_code', 0),
                    'duration_ms': getattr(phase, 'duration_ms', 0),
                }
                for phase in getattr(result, 'phases', ()) or ()
            ],
        }

    # ---- 载荷 ----

    def _payload(self, arguments: Mapping[str, Any], target_kind: str,
                 generated: Mapping[str, Any], static: Mapping[str, Any],
                 t2: Mapping[str, Any], publishable: bool) -> Dict[str, Any]:
        files: Mapping[str, str] = generated['files']
        artifacts = generated['artifacts']
        artifact_by_module = {item['module']: item for item in artifacts}
        with_content = self._files_with_content(files, artifact_by_module)
        payload: Dict[str, Any] = {
            'mode': 'proposal',
            'tool': DRIVER_PROPOSE_TOOL,
            'target_kind': target_kind,
            'artifact_kinds': [item['artifact_kind'] for item in artifacts],
            'artifacts': artifacts,
            'file_list': sorted(files),
            'files': with_content['files'],
            'contents_omitted': with_content['omitted'],
            'diff': self._diff(files),
            'diff_truncated': False,
            'code_sha256': generated['code_sha256'],
            'capabilities': driver_tools.normalize_capabilities(
                arguments['capabilities']),
            'source_trace': driver_tools.trace_summary(arguments.get('ui_trace')),
            'contract': _contract_summary(arguments.get('contract')),
            'dependencies': generated['dependencies'],
            'risks': generated['risks'],
            'rollback': generated['rollback'],
            'manifest': generated['manifest'],
            'validation_report': {
                'static_check': dict(static),
                't2': dict(t2),
                'publishable': publishable,
                'code_sha256': generated['code_sha256'],
            },
            'publish': {
                'available': False,
                'reason': PUBLISH_DISABLED,
                'requires': 'DESTRUCTIVE 审批（单独审批单）+ '
                            'AGENT_DRIVER_PUBLISH_ENABLED=true',
            },
        }
        return payload

    def _files_with_content(self, files: Mapping[str, str],
                            artifacts: Mapping[str, Mapping[str, Any]]
                            ) -> Dict[str, Any]:
        entries = []
        total = 0
        include = True
        for path in sorted(files):
            content = files[path]
            total += len(content)
        if total > self._settings.max_result_chars:
            include = False
        for path in sorted(files):
            content = files[path]
            artifact = artifacts.get(path)
            entry = {
                'path': path,
                'bytes': len(content.encode('utf-8')),
                'sha256': _sha256(content),
                'artifact_kind': artifact['artifact_kind'] if artifact else None,
            }
            if include:
                entry['content'] = content
            entries.append(entry)
        return {'files': entries, 'omitted': not include}

    def _diff(self, files: Mapping[str, str]) -> List[Dict[str, Any]]:
        """新增文件 diff（/dev/null → 文件）；超长只保留前 N 行并标记。"""
        entries: List[Dict[str, Any]] = []
        budget = self._settings.max_diff_chars
        for path in sorted(files):
            lines = files[path].splitlines()
            added = [f'+{line}' for line in lines]
            header = [f'--- /dev/null', f'+++ b/{path}']
            body: List[str] = []
            used = len('\n'.join(header))
            truncated = False
            for line in added:
                used += len(line) + 1
                if used > budget:
                    truncated = True
                    break
                body.append(line)
            budget -= used
            entries.append({
                'path': path,
                'hunk': '\n'.join(header + body),
                'lines': len(lines),
                'truncated': truncated,
            })
            if budget <= 0:
                break
        return entries


__all__ = [
    'CODE_SOURCE', 'DRIVER_PROPOSE_TOOL', 'DriverProposalError',
    'DriverProposalService', 'DriverProposalSettings', 'PUBLISH_APPROVAL_REQUIRED',
    'PUBLISH_DISABLED', 'PUBLISH_NOT_PUBLISHABLE', 'PUBLISH_UNAVAILABLE',
    'STATIC_FAILED', 'STATIC_OK', 'T2_RUNTIME_UNAVAILABLE',
    'canonical_code_sha256',
]
