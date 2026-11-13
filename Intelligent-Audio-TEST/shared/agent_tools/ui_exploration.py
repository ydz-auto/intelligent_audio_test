# -*- coding: utf-8 -*-
"""探索-生成层共享口径（INT-2492，方案 §6.6 / §6.7）。

本模块是 ``ui_tree`` / ``ui_action`` / ``api_spec`` 三个意图工具的**唯一事实源**：
枚举、预算、裁剪口径、树 diff、``ui_trace.json`` 结构与校验、契约解析全部在这里，
``agent_service`` 只做编排（租约 / 审批 / 预算 / 产物登记），不复制一份口径。

设计约束（卡面）：

- ``ui_tree`` 只返回**裁剪后的节点**（默认/上限 200），字段固定
  ``id`` / ``text`` / ``resource_id``(无则 ``key``) / ``class`` / ``bounds`` /
  ``clickable`` / ``enabled``；整页 XML 与 base64 一律不进响应（平台适配层
  ``parse_android_hierarchy`` / ``parse_harmony_components`` 在服务端内部完成解析）。
- ``ui_action`` 只接受 ``UiActionType`` 七种动作；每次动作返回树 diff 并追加到
  ``ui_trace.json``。``DESTRUCTIVE``（卸载 / 重启 / 支付 / 删账号等）与登录 /
  验证码页在动作层拦截，停止原因取 ``ExplorationStopReason``，禁止魔法值。
- 预算：单次探索最多 30 个动作 / 5 分钟（``MAX_ACTIONS`` / ``MAX_DURATION_SECONDS``，
  服务端可用配置覆盖），超限以 ``BUDGET`` 停止并交回。
- ``api_spec`` 只解析契约（OpenAPI / gRPC proto / WebSocket），**不做真实调用**；
  畸形契约抛 ``SpecParseError``（调用方转成模型可读的普通失败，不抛内部异常）。

平台覆盖（卡面「适配层按平台实现，字段缺省要有明确降级」）：

| 平台 | 树来源 | 定位键 | 降级 |
|---|---|---|---|
| Android | uiautomator2 ``dump_hierarchy`` XML | ``resource-id`` | 无 resource-id → ``key``（content-desc/稳定路径）→ 文本（必须带 ``fallback_reason``） |
| HarmonyOS | hypium 组件列表（``getComponent`` 结果） | ``id`` | 无 id → ``key`` → 文本（同上）；组件不可得时由驱动层显式报降级原因，不伪造空树 |

``ui_trace.json`` 的结构直接复用 ``driver_tools.validate_ui_trace`` 的校验口径：
``actions``（动作序列）/ ``pages``（页面树）/ ``screenshots``（截图引用），
因此探索轨迹可以直接作为 ``driver_propose`` 的 ``ui_trace`` 输入。
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from shared.agent_tools import driver_tools

# ---------------------------------------------------------------- 预算 / 上限

#: 单次 ui_tree 返回的节点上限（卡面硬上限，模型显式传更大值也按此截断）
MAX_TREE_NODES = 200
#: 模型可传的 max_nodes 上界 = MAX_TREE_NODES；缺省取同一值
DEFAULT_TREE_NODES = 200
#: 单次探索动作上限（第 31 个动作前以 BUDGET 停止）
MAX_ACTIONS = 30
#: 单次探索时长上限（秒）
MAX_DURATION_SECONDS = 300
#: 单次探索保留的截图引用上限
MAX_SCREENSHOTS = 30
#: ui_trace.json 保留的页面树页数上限（动作可到 30，页面数按快照去重后截断）
MAX_TRACE_PAGES = 30
#: 产物 kind（agent_artifact.kind 新增取值，枚举化）
ARTIFACT_KIND_UI_TRACE = 'UI_TRACE'
#: 轨迹文件名（交付包内固定名）
UI_TRACE_FILENAME = 'ui_trace.json'
#: 轨迹 JSON 字节上界（超出即裁剪；裁剪后仍超出才判产物校验失败）
MAX_TRACE_BYTES = 4 * 1024 * 1024
#: 轨迹裁剪时单个节点文本保留长度（被测 App 的文本长度不可控，必须设上限）
TRACE_TEXT_CAP = 256
#: 轨迹裁剪时至少保留的页数（最后一页 = 当前页面，丢了就无法定位）
TRACE_MIN_PAGES = 1

#: 节点固定字段（顺序即输出顺序）
NODE_FIELDS: Tuple[str, ...] = (
    'id', 'text', 'resource_id', 'class', 'bounds', 'clickable', 'enabled')
#: 定位键优先级：稳定标识在前，文本定位必须带 fallback_reason
LOCATOR_STABLE_KEYS: Tuple[str, ...] = ('resource_id', 'key')
LOCATOR_TEXT_KEYS: Tuple[str, ...] = ('text', 'label')
LOCATOR_FALLBACK_REASON_KEY = driver_tools.LOCATOR_FALLBACK_REASON_KEY

#: 支持解析的契约类型
CONTRACT_KINDS: Tuple[str, ...] = ('OPENAPI', 'PROTO', 'WS')


class UiActionType(str, Enum):
    """设备 UI 动作（卡面七种，接口值即枚举值）。"""

    TAP = 'TAP'
    LONG_PRESS = 'LONG_PRESS'
    SWIPE = 'SWIPE'
    INPUT_TEXT = 'INPUT_TEXT'
    BACK = 'BACK'
    HOME = 'HOME'
    WAIT = 'WAIT'

    @property
    def needs_target(self) -> bool:
        """需要元素定位的动作（其余是全局手势 / 系统动作）。"""
        return self in (UiActionType.TAP, UiActionType.LONG_PRESS,
                        UiActionType.INPUT_TEXT)


class ExplorationStopReason(str, Enum):
    """探索停止原因（禁止魔法值；写入 trace / 工具结果 / run 事件）。"""

    DONE = 'DONE'
    BUDGET = 'BUDGET'
    LOGIN_REQUIRED = 'LOGIN_REQUIRED'
    CAPTCHA = 'CAPTCHA'
    DESTRUCTIVE_BLOCKED = 'DESTRUCTIVE_BLOCKED'
    USER_CANCEL = 'USER_CANCEL'


class UiBlockedPage(str, Enum):
    """需要立即交回用户的页面类型（不尝试绕过）。"""

    LOGIN = 'LOGIN'
    CAPTCHA = 'CAPTCHA'
    REALNAME = 'REALNAME'
    PAYMENT = 'PAYMENT'


#: 页面类型 → 停止原因（REALNAME 按「需登录/实名交回」口径归入 LOGIN_REQUIRED）
_BLOCKED_PAGE_STOP: Dict[UiBlockedPage, ExplorationStopReason] = {
    UiBlockedPage.LOGIN: ExplorationStopReason.LOGIN_REQUIRED,
    UiBlockedPage.CAPTCHA: ExplorationStopReason.CAPTCHA,
    UiBlockedPage.REALNAME: ExplorationStopReason.LOGIN_REQUIRED,
    UiBlockedPage.PAYMENT: ExplorationStopReason.DESTRUCTIVE_BLOCKED,
}

#: 页面识别关键词（小写比较；同一组内按「任一命中」计）
_PAGE_KEYWORDS: Dict[UiBlockedPage, Tuple[str, ...]] = {
    UiBlockedPage.LOGIN: ('登录', '登入', 'sign in', 'signin', 'log in', 'login',
                          '账号密码', '手机号登录', '密码登录'),
    UiBlockedPage.CAPTCHA: ('验证码', '人机验证', '滑块', '拖动滑块', '滑动验证',
                            '安全验证', 'captcha', 'verify you are human'),
    UiBlockedPage.REALNAME: ('实名认证', '实名验证', '身份认证', 'real-name'),
    UiBlockedPage.PAYMENT: ('支付', '付款', '收银台', '立即购买', '确认支付',
                            'payment', 'checkout', 'purchase'),
}

#: 破坏性动作关键词：命中即 DESTRUCTIVE_BLOCKED（元素文本 / resource_id / 输入文本）
_DESTRUCTIVE_KEYWORDS: Tuple[str, ...] = (
    '卸载', '重启', '关机', '恢复出厂', '清空数据', '格式化',
    '支付', '付款', '确认支付', '立即购买', '开通会员', '充值',
    '删除账号', '注销账号', '注销账户', '退出登录并删除', '删除账户',
    'uninstall', 'reboot', 'shutdown', 'factory reset', 'wipe data',
    'payment', 'pay now', 'purchase', 'delete account', 'deactivate account',
)

#: 破坏性判定时只看这些动作（BACK/HOME/WAIT 不落在元素上，不做关键词判定）
_TARGET_ACTIONS = (UiActionType.TAP, UiActionType.LONG_PRESS)

_BOUNDS_PATTERN = re.compile(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]')


class SpecParseError(ValueError):
    """契约解析失败（畸形 / 不支持的格式）：调用方转普通失败，不抛内部异常。"""

    def __init__(self, message: str, *, code: str = 'SPEC_PARSE_ERROR'):
        super().__init__(message)
        self.code = code


class UiTreeParseError(ValueError):
    """平台 UI 树解析失败（格式不符 / 空树）。"""


# ---------------------------------------------------------------- 预算

@dataclass(frozen=True)
class ExplorationBudget:
    """单次探索预算（动作数 / 时长），值来自配置，不给默认魔法值以外的口径。"""

    max_actions: int = MAX_ACTIONS
    max_seconds: float = float(MAX_DURATION_SECONDS)

    def check_next(self, actions_used: int, elapsed_seconds: float
                   ) -> Optional[ExplorationStopReason]:
        """是否拒绝**下一个**动作：返回 ``BUDGET`` 或 ``None``。"""
        if actions_used >= max(0, int(self.max_actions)):
            return ExplorationStopReason.BUDGET
        if elapsed_seconds >= float(self.max_seconds):
            return ExplorationStopReason.BUDGET
        return None

    def as_dict(self, actions_used: int, elapsed_seconds: float) -> Dict[str, Any]:
        return {
            'actions_used': int(actions_used),
            'max_actions': int(self.max_actions),
            'elapsed_seconds': round(float(elapsed_seconds), 3),
            'max_seconds': float(self.max_seconds),
        }


# ---------------------------------------------------------------- 树裁剪

def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes')
    if value is None:
        return default
    return bool(value)


def parse_bounds(value: Any) -> Optional[List[int]]:
    """``[x1,y1][x2,y2]`` / ``[x1,y1,x2,y2]`` / ``{left,top,right,bottom}`` → 四元组。"""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if len(value) == 4:
            try:
                return [int(v) for v in value]
            except (TypeError, ValueError):
                return None
        return None
    if isinstance(value, dict):
        keys = ('left', 'top', 'right', 'bottom')
        if all(key in value for key in keys):
            try:
                return [int(value[key]) for key in keys]
            except (TypeError, ValueError):
                return None
        return None
    match = _BOUNDS_PATTERN.search(str(value))
    if not match:
        return None
    return [int(part) for part in match.groups()]


def normalize_node(raw: Dict[str, Any], *, index: int = 0,
                  platform: str = 'ANDROID') -> Optional[Dict[str, Any]]:
    """平台原始节点 → 固定七字段的裁剪节点；无文本且不可点的容器返回 ``None``。

    ``resource_id`` 缺失时用 ``key`` 兜底：key 取 content-desc / 稳定路径
    （``class[index]``），两者都不可得时留空并由调用方按文本定位（带原因）。
    """
    if not isinstance(raw, dict):
        return None
    # 稳定标识候选：Android 用 resource-id；HarmonyOS 的组件 id / key 本身就是
    # 稳定标识（hypium getComponent(...).getId()），按平台口径取，不跨平台串用。
    candidates = ['resource-id', 'resource_id']
    if platform == 'HARMONYOS':
        candidates += ['id', 'key']
    resource_id = ''
    for name in candidates:
        value = raw.get(name)
        if value is not None and str(value).strip():
            resource_id = str(value).strip()
            break
    text = str(raw.get('text') or '').strip()
    desc = str(raw.get('content-desc') or raw.get('description') or '').strip()
    class_name = str(raw.get('class') or raw.get('type') or '').strip()
    clickable = _as_bool(raw.get('clickable'))
    enabled = _as_bool(raw.get('enabled'), True)
    bounds = parse_bounds(raw.get('bounds'))
    node_id = str(raw.get('id') or raw.get('node_id') or '').strip() or \
        f'{platform.lower()}:{index}'
    key = ''
    if not resource_id:
        key = desc or (f'{class_name}[{index}]' if class_name else '')
    if not (text or desc or resource_id or clickable):
        return None
    return {
        'id': node_id,
        'text': text or desc,
        'resource_id': resource_id or None,
        'class': class_name or None,
        'bounds': bounds,
        'clickable': clickable,
        'enabled': enabled,
        # key 是定位降级用的稳定标识，不单独占响应字段（放进 nodes 时剔除）
        '_key': key or None,
    }


def _public_node(node: Dict[str, Any]) -> Dict[str, Any]:
    return {name: node.get(name) for name in NODE_FIELDS}


def crop_nodes(nodes: Sequence[Dict[str, Any]], max_nodes: int
               ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """裁剪到 ``max_nodes``（不超过 ``MAX_TREE_NODES``），返回 (节点, 统计)。"""
    limit = max(1, min(int(max_nodes or DEFAULT_TREE_NODES), MAX_TREE_NODES))
    total = len(nodes)
    kept = list(nodes[:limit])
    stats = {
        'total_nodes': total,
        'node_count': len(kept),
        'truncated': total > len(kept),
        'max_nodes': limit,
    }
    return kept, stats


def nodes_for_response(cropped: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """输出用节点：七字段 + ``key``（无 resource_id 时的定位降级值）。"""
    result = []
    for node in cropped:
        public = _public_node(node)
        if public.get('resource_id') is None and node.get('_key'):
            public['key'] = node['_key']
        result.append(public)
    return result


# ---------------------------------------------------------------- 平台适配

def parse_android_hierarchy(xml_text: str) -> List[Dict[str, Any]]:
    """uiautomator2 ``dump_hierarchy`` XML → 原始节点列表（服务端内部使用）。"""
    body = (xml_text or '').strip()
    if not body:
        raise UiTreeParseError('Android UI 树为空（dump_hierarchy 未返回内容）')
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise UiTreeParseError(f'Android UI 树 XML 解析失败：{exc}') from exc
    nodes: List[Dict[str, Any]] = []
    for index, element in enumerate(root.iter('node')):
        attrs = dict(element.attrib)
        attrs.setdefault('node_id', f'android:{index}')
        node = normalize_node(attrs, index=index, platform='ANDROID')
        if node is not None:
            nodes.append(node)
    if not nodes:
        raise UiTreeParseError('Android UI 树没有任何可用节点')
    return nodes


def _walk_components(items: Iterable[Any], out: List[Dict[str, Any]]) -> None:
    for item in items or ():
        if not isinstance(item, dict):
            continue
        node = normalize_node(item, index=len(out), platform='HARMONYOS')
        if node is not None:
            out.append(node)
        children = item.get('children')
        if isinstance(children, list):
            _walk_components(children, out)


def parse_harmony_components(components: Any) -> List[Dict[str, Any]]:
    """hypium 组件列表（``getComponent`` 结果）→ 原始节点列表。

    组件字段名跨版本不固定：``id`` / ``resource_id`` / ``key`` 都认，``type``
    当 class，``bounds`` 支持字符串与对象两种形态；缺 id 时按 key / 文本降级。
    """
    if isinstance(components, dict):
        components = components.get('components') or components.get('nodes') or []
    if not isinstance(components, list):
        raise UiTreeParseError('HarmonyOS UI 树必须是组件数组')
    nodes: List[Dict[str, Any]] = []
    _walk_components(components, nodes)
    if not nodes:
        raise UiTreeParseError('HarmonyOS UI 树没有任何可用节点')
    return nodes


def coverage_notes(nodes: Sequence[Dict[str, Any]], platform: str
                   ) -> Dict[str, Any]:
    """各平台覆盖与降级摘要（写进交付 / trace，说明定位键退化情况）。"""
    total = len(nodes)
    stable = sum(1 for node in nodes if node.get('resource_id'))
    keyed = sum(1 for node in nodes if not node.get('resource_id')
                and node.get('_key'))
    text_only = total - stable - keyed
    return {
        'platform': platform,
        'nodes': total,
        'resource_id': stable,
        'key': keyed,
        'text_only': text_only,
    }


# ---------------------------------------------------------------- 树 diff

def node_key(node: Dict[str, Any]) -> str:
    """节点稳定键：resource_id → key → class+text+bounds → id。"""
    if node.get('resource_id'):
        return f"rid:{node['resource_id']}"
    if node.get('_key'):
        return f"key:{node['_key']}"
    class_name = node.get('class') or ''
    bounds = node.get('bounds')
    if class_name or bounds:
        return f"sig:{class_name}:{node.get('text') or ''}:{bounds}"
    return f"id:{node.get('id')}"


def diff_trees(previous: Sequence[Dict[str, Any]],
               current: Sequence[Dict[str, Any]],
               *, max_items: int = MAX_TREE_NODES) -> Dict[str, Any]:
    """两棵裁剪树的结构 diff（按 ``node_key`` 对齐，输出受 ``max_items`` 限制）。"""
    before = {node_key(node): node for node in previous or ()}
    after = {node_key(node): node for node in current or ()}
    added = [_public_node(after[key]) for key in after if key not in before]
    removed = [_public_node(before[key]) for key in before if key not in after]
    changed = []
    unchanged = 0
    for key in after:
        if key not in before:
            continue
        old, new = before[key], after[key]
        if _public_node(old) == _public_node(new):
            unchanged += 1
            continue
        fields = [name for name in NODE_FIELDS
                  if old.get(name) != new.get(name)]
        changed.append({'key': key, 'fields': fields,
                        'before': _public_node(old),
                        'after': _public_node(new)})
    return {
        'added': added[:max_items],
        'removed': removed[:max_items],
        'changed': changed[:max_items],
        'counts': {'added': len(added), 'removed': len(removed),
                   'changed': len(changed), 'unchanged': unchanged,
                   'previous': len(before), 'current': len(after)},
        'truncated': (len(added) > max_items or len(removed) > max_items
                      or len(changed) > max_items),
    }


# ---------------------------------------------------------------- 安全判定

def _node_texts(nodes: Sequence[Dict[str, Any]]) -> str:
    parts = []
    for node in nodes or ():
        for key in ('text', 'resource_id'):
            value = node.get(key)
            if value:
                parts.append(str(value))
    return ' '.join(parts).lower()


def detect_blocked_page(nodes: Sequence[Dict[str, Any]]
                        ) -> Optional[UiBlockedPage]:
    """从裁剪树判断是否停在登录 / 验证码 / 实名 / 支付页（按关键词组）。"""
    text = _node_texts(nodes)
    if not text:
        return None
    # 支付页判定优先（同时含「确定支付 + 密码」时不能只当登录页放行）
    for page in (UiBlockedPage.PAYMENT, UiBlockedPage.CAPTCHA,
                 UiBlockedPage.REALNAME, UiBlockedPage.LOGIN):
        if any(term in text for term in _PAGE_KEYWORDS[page]):
            return page
    return None


def stop_reason_for_page(page: Optional[UiBlockedPage]
                         ) -> Optional[ExplorationStopReason]:
    return _BLOCKED_PAGE_STOP.get(page) if page else None


def detect_destructive(action_type: str, node: Optional[Dict[str, Any]],
                       params: Optional[Dict[str, Any]] = None
                       ) -> Optional[str]:
    """破坏性动作判定：返回命中的关键词（调用方转 ``DESTRUCTIVE_BLOCKED``）。"""
    try:
        action = UiActionType(str(action_type).upper())
    except ValueError:
        return None
    if action not in _TARGET_ACTIONS:
        return None
    haystack_parts: List[str] = []
    if isinstance(node, dict):
        for key in ('text', 'resource_id', 'class'):
            value = node.get(key)
            if value:
                haystack_parts.append(str(value))
    if isinstance(params, dict):
        for key in ('text', 'value', 'input_text'):
            value = params.get(key)
            if value:
                haystack_parts.append(str(value))
    haystack = ' '.join(haystack_parts).lower()
    for term in _DESTRUCTIVE_KEYWORDS:
        if term in haystack:
            return term
    return None


# ---------------------------------------------------------------- 动作 / 轨迹

def build_locator(node: Optional[Dict[str, Any]],
                  *, fallback_reason: Optional[str] = None
                  ) -> Optional[Dict[str, Any]]:
    """节点 → 轨迹定位键（稳定标识优先；文本定位必须带 fallback_reason）。"""
    if not isinstance(node, dict):
        return None
    if node.get('resource_id'):
        return {'resource_id': node['resource_id']}
    if node.get('_key'):
        return {'key': node['_key']}
    text = node.get('text')
    if text:
        return {'text': text,
                'fallback_reason': fallback_reason
                or '该元素没有 resource_id / key，只能按文本定位'}
    return None


def build_action_record(*, index: int, action_type: str,
                        params: Optional[Dict[str, Any]] = None,
                        node: Optional[Dict[str, Any]] = None,
                        at_ms: int = 0, dry_run: bool = False,
                        applied: bool = True,
                        image_ref: Optional[str] = None) -> Dict[str, Any]:
    """一条动作记录（``ui_trace.actions[]``；与 driver_tools 校验口径一致）。"""
    record: Dict[str, Any] = {
        'index': int(index),
        'action': UiActionType(str(action_type).upper()).value,
        'at_ms': int(at_ms),
        'applied': bool(applied),
        'dry_run': bool(dry_run),
    }
    if params:
        record['params'] = dict(params)
    locator = build_locator(node)
    if locator:
        record['locator'] = locator
    if image_ref:
        record['screenshot'] = image_ref
    return record


def build_page_record(*, snapshot_id: str, nodes: Sequence[Dict[str, Any]],
                      captured_ms: int = 0,
                      screenshot_ref: Optional[str] = None
                      ) -> Dict[str, Any]:
    """一页裁剪树（``ui_trace.pages[]``）。"""
    cropped, stats = crop_nodes(nodes, MAX_TREE_NODES)
    page = {
        'snapshot_id': snapshot_id,
        'captured_ms': int(captured_ms),
        'node_count': stats['node_count'],
        'total_nodes': stats['total_nodes'],
        'nodes': nodes_for_response(cropped),
    }
    if screenshot_ref:
        page['screenshot'] = screenshot_ref
    return page


def build_ui_trace(*, device_id: Any, platform: str, run_id: str,
                   session_id: Optional[str],
                   actions: Sequence[Dict[str, Any]],
                   pages: Sequence[Dict[str, Any]],
                   screenshots: Sequence[str],
                   started_ms: int, finished_ms: int,
                   stop_reason: ExplorationStopReason,
                   coverage: Optional[Dict[str, Any]] = None,
                   run_status: Optional[str] = None,
                   run_error: Optional[str] = None,
                   lease_mode: Optional[str] = None,
                   lease_degraded: bool = False
                   ) -> Dict[str, Any]:
    """组装 ``ui_trace.json``（动作序列 + 页面树 + 截图引用）。

    ``stop_reason`` 只描述**探索**为什么停（``ExplorationStopReason`` 六值）；
    ``run_status`` / ``run_error`` 记录收口时 run 的终态与失败原因（取消 /
    失败也要留痕，不能都记成 ``DONE`` 把失败原因丢掉）。``lease_mode`` /
    ``lease_degraded`` 记录设备租约的实际获取方式：底层 Redis 锁不可用时会
    「降级放行」，轨迹里必须能看到这次探索并没有真正锁住设备（P3-2）。
    """
    trace: Dict[str, Any] = {
        'version': 1,
        'device_id': device_id,
        'platform': platform,
        'run_id': run_id,
        'session_id': session_id,
        'started_ms': int(started_ms),
        'finished_ms': int(finished_ms),
        'stop_reason': stop_reason.value,
        'actions': list(actions),
        'pages': list(pages)[-MAX_TRACE_PAGES:],
        'screenshots': list(screenshots)[-MAX_SCREENSHOTS:],
        'coverage': coverage or {},
    }
    if lease_mode:
        trace['lease'] = {'mode': str(lease_mode).upper(),
                          'degraded': bool(lease_degraded)}
    if run_status:
        trace['run_status'] = str(run_status)
    if run_error:
        trace['run_error'] = str(run_error)
    return trace


def trace_bytes(trace: Dict[str, Any]) -> int:
    """轨迹的落盘字节数（与 ``_write_trace`` 序列化口径一致）。"""
    return len(json.dumps(trace, ensure_ascii=False,
                          sort_keys=True).encode('utf-8'))


def fit_trace_to_bytes(trace: Dict[str, Any],
                       *, max_bytes: int = MAX_TRACE_BYTES
                       ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """把轨迹压到 ``max_bytes`` 以内；返回 ``(轨迹, 裁剪说明)``。

    一次探索最多 30 个动作 × 每页 200 节点，而节点文本长度由被测 App 决定，
    不设上限时会产出十几 MB 的 ``ui_trace.json``。这里按确定性顺序裁剪：

    1. 截断单节点文本（``TRACE_TEXT_CAP`` → 64 → 16 字符，多轮递进）；
    2. 仍然超限则从最旧的页面开始丢（至少保留最后一页 = 当前页面）。

    动作序列 / 截图引用 / 定位键不动（审计与定位的底线），裁剪量写进
    ``trace['trimmed']``，**不静默截断**。裁剪后仍超限时原样返回，由
    ``validation_report`` 判失败（调用方不得把它登记成 ok=True）。
    """
    original = trace_bytes(trace)
    if original <= max_bytes:
        return trace, None
    result = json.loads(json.dumps(trace))  # 深拷贝：不改调用方持有的对象
    pages = result.get('pages')
    if not isinstance(pages, list):
        pages = []
    stats = {'text_truncated': 0, 'pages_dropped': 0}

    def truncate_texts(cap: int) -> None:
        for page in pages:
            for node in (page.get('nodes') or ()
                         if isinstance(page, dict) else ()):
                if not isinstance(node, dict):
                    continue
                text = node.get('text')
                if isinstance(text, str) and len(text) > cap:
                    node['text'] = text[:cap]
                    stats['text_truncated'] += 1

    for cap in (TRACE_TEXT_CAP, 64, 16):
        truncate_texts(cap)
        while len(pages) > TRACE_MIN_PAGES:
            current = trace_bytes(result)
            if current <= max_bytes:
                break
            # 按体积比例一次丢足够多的最旧页（避免逐页序列化 30 次）
            keep = max(TRACE_MIN_PAGES, int(len(pages) * max_bytes / current))
            drop = max(1, len(pages) - keep)
            del pages[:drop]
            stats['pages_dropped'] += drop
        if trace_bytes(result) <= max_bytes:
            break

    result['trimmed'] = {
        'bytes_before': original,
        'bytes_after': trace_bytes(result),
        'max_bytes': int(max_bytes),
        'text_cap': TRACE_TEXT_CAP,
        'text_truncated': stats['text_truncated'],
        'pages_dropped': stats['pages_dropped'],
    }
    return result, result['trimmed']


def validation_report(trace: Dict[str, Any], *, trace_bytes: int = 0
                      ) -> Dict[str, Any]:
    """产物校验报告：结构 + 体积 + 定位质量（写进 artifact.metadata）。"""
    structure_error = driver_tools.validate_ui_trace(trace, required=True)
    size = int(trace_bytes or 0)
    size_error = None
    if size <= 0:
        size_error = 'ui_trace.json 为空'
    elif size > MAX_TRACE_BYTES:
        size_error = f'ui_trace.json 超过 {MAX_TRACE_BYTES} 字节（{size}）'
    locators = driver_tools.locator_report(trace)
    summary = driver_tools.trace_summary(trace)
    checks = [
        {'name': 'structure', 'ok': structure_error is None,
         'detail': structure_error},
        {'name': 'size', 'ok': size_error is None, 'detail': size_error},
        {'name': 'locators', 'ok': True,
         'detail': f'稳定定位 {locators["stable_locators"]} / 文本定位 '
                   f'{locators["text_locators"]}'},
    ]
    return {
        'ok': structure_error is None and size_error is None,
        'checks': checks,
        'bytes': size,
        'actions': summary['actions'],
        'pages': summary['pages'],
        'screenshots': summary['screenshots'],
        'sha256': summary['sha256'],
        'locators': locators,
    }


# ---------------------------------------------------------------- api_spec

_HTTP_METHODS = ('get', 'post', 'put', 'patch', 'delete', 'head', 'options')


def _load_structured(content: Any, kind: str) -> Any:
    if isinstance(content, (dict, list)):
        return content
    text = str(content or '').strip()
    if not text:
        raise SpecParseError(f'{kind} 契约内容为空')
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:  # YAML 是 OpenAPI 的常见载体；PyYAML 缺失时给明确提示
        import yaml  # noqa: WPS433 - 可选依赖
    except ImportError as exc:  # pragma: no cover - 依赖在镜像里已装
        raise SpecParseError('契约不是 JSON，且环境未安装 YAML 解析器') from exc
    try:
        return yaml.safe_load(text)
    except Exception as exc:  # noqa: BLE001 - 解析失败按畸形契约处理
        raise SpecParseError(f'{kind} 契约解析失败：{exc}') from exc


def _openapi_params(operation: Dict[str, Any]) -> List[Dict[str, Any]]:
    params = []
    for item in operation.get('parameters') or ():
        if not isinstance(item, dict):
            continue
        schema = item.get('schema') if isinstance(item.get('schema'), dict) else {}
        params.append({
            'name': item.get('name'),
            'in': item.get('in'),
            'required': _as_bool(item.get('required')),
            'type': schema.get('type') or item.get('type'),
            'description': item.get('description'),
        })
    body = operation.get('requestBody')
    if isinstance(body, dict):
        content = body.get('content') if isinstance(body.get('content'), dict) else {}
        for media_type, media in content.items():
            schema = (media or {}).get('schema') if isinstance(media, dict) else None
            params.append({'name': 'body', 'in': 'body', 'required':
                           _as_bool(body.get('required')),
                           'type': media_type, 'schema': schema})
    return params


def _sample_from_schema(schema: Any) -> Any:
    """按 schema 生成字段名骨架（不是编造业务值：类型占位 + required 字段）。"""
    if not isinstance(schema, dict):
        return None
    properties = schema.get('properties')
    if isinstance(properties, dict):
        return {name: _sample_from_schema(value) for name, value in
                properties.items()}
    if schema.get('type') == 'array':
        return [_sample_from_schema(schema.get('items'))]
    return schema.get('type') or None


def _parse_openapi(document: Any, endpoint: Optional[str]) -> Dict[str, Any]:
    if not isinstance(document, dict):
        raise SpecParseError('OpenAPI 契约必须是对象（含 openapi / paths）')
    paths = document.get('paths')
    if not isinstance(paths, dict) or not paths:
        raise SpecParseError('OpenAPI 契约缺少 paths')
    # 鉴权：3.x components.securitySchemes / 2.0 securityDefinitions
    components = document.get('components') if isinstance(
        document.get('components'), dict) else {}
    schemes = components.get('securitySchemes') or \
        document.get('securityDefinitions') or {}
    auth_schemes = []
    for name, scheme in (schemes or {}).items():
        if not isinstance(scheme, dict):
            continue
        auth_schemes.append({
            'name': name,
            'type': scheme.get('type'),
            'scheme': scheme.get('scheme'),
            'in': scheme.get('in'),
            'key': scheme.get('name'),
        })
    endpoints: List[Dict[str, Any]] = []
    for path, operations in paths.items():
        if not isinstance(operations, dict):
            continue
        for method, operation in operations.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            full = f'{method.upper()} {path}'
            if endpoint and endpoint.lower() not in full.lower():
                continue
            responses = operation.get('responses') if isinstance(
                operation.get('responses'), dict) else {}
            response_sample = None
            for status, response in responses.items():
                if not str(status).startswith('2') or not isinstance(response, dict):
                    continue
                content = response.get('content') if isinstance(
                    response.get('content'), dict) else {}
                for media in content.values():
                    if isinstance(media, dict) and media.get('schema'):
                        response_sample = _sample_from_schema(media['schema'])
                        break
                if response_sample is None and isinstance(
                        response.get('schema'), dict):
                    response_sample = _sample_from_schema(response['schema'])
                break
            request_body = operation.get('requestBody')
            request_sample = None
            if isinstance(request_body, dict):
                content = request_body.get('content') if isinstance(
                    request_body.get('content'), dict) else {}
                for media in content.values():
                    if isinstance(media, dict) and media.get('schema'):
                        request_sample = _sample_from_schema(media['schema'])
                        break
            security = operation.get('security') or document.get('security') or []
            endpoints.append({
                'method': method.upper(),
                'path': path,
                'operation_id': operation.get('operationId'),
                'summary': operation.get('summary'),
                'params': _openapi_params(operation),
                'auth': [name for item in security if isinstance(item, dict)
                         for name in item],
                'request_sample': request_sample,
                'response_sample': response_sample,
            })
    if endpoint and not endpoints:
        raise SpecParseError(f'OpenAPI 契约里没有匹配 {endpoint} 的端点')
    if not endpoints:
        raise SpecParseError('OpenAPI 契约没有可用端点')
    return {'kind': 'OPENAPI', 'endpoints': endpoints,
            'auth_schemes': auth_schemes,
            'title': ((document.get('info') or {}).get('title')
                      if isinstance(document.get('info'), dict) else None),
            'openapi': document.get('openapi') or document.get('swagger')}


def _parse_ws(document: Any, endpoint: Optional[str]) -> Dict[str, Any]:
    if not isinstance(document, dict):
        raise SpecParseError('WS 契约必须是对象（含 url / messages 或 channels）')
    url = document.get('url') or document.get('endpoint') or document.get('path')
    channels = document.get('channels') if isinstance(
        document.get('channels'), list) else None
    messages = document.get('messages') if isinstance(
        document.get('messages'), list) else None
    if not (url or channels or messages):
        raise SpecParseError('WS 契约缺少 url / channels / messages')
    auth = document.get('auth') if isinstance(document.get('auth'), dict) else {}
    auth_schemes = []
    if auth:
        auth_schemes.append({'name': auth.get('type') or 'auth',
                             'type': auth.get('type'),
                             'in': auth.get('in') or 'header',
                             'key': auth.get('header') or auth.get('key')})
    endpoints: List[Dict[str, Any]] = []
    for channel in channels or ():
        if not isinstance(channel, dict):
            continue
        name = channel.get('name') or channel.get('channel')
        if endpoint and endpoint.lower() not in str(name).lower():
            continue
        endpoints.append({
            'method': 'WS',
            'path': name,
            'operation_id': channel.get('operation_id'),
            'summary': channel.get('description'),
            'params': [{'name': key, 'in': 'message', 'required': False,
                        'type': type(value).__name__}
                       for key, value in (channel.get('fields') or {}).items()]
            if isinstance(channel.get('fields'), dict) else [],
            'auth': [auth_schemes[0]['name']] if auth_schemes else [],
            'request_sample': channel.get('send') or channel.get('request_sample'),
            'response_sample': channel.get('receive') or channel.get('response_sample'),
        })
    for message in messages or ():
        if not isinstance(message, dict):
            continue
        name = message.get('type') or message.get('event') or 'message'
        if endpoint and endpoint.lower() not in str(name).lower():
            continue
        endpoints.append({
            'method': 'WS',
            'path': f'{url or "ws"}#{name}',
            'operation_id': name,
            'summary': message.get('description'),
            'params': [{'name': key, 'in': 'message', 'required': False,
                        'type': type(value).__name__}
                       for key, value in (message.get('send') or {}).items()],
            'auth': [auth_schemes[0]['name']] if auth_schemes else [],
            'request_sample': message.get('send'),
            'response_sample': message.get('receive'),
        })
    if not endpoints and url:
        endpoints.append({
            'method': 'WS', 'path': url, 'operation_id': None,
            'summary': document.get('description'), 'params': [],
            'auth': [auth_schemes[0]['name']] if auth_schemes else [],
            'request_sample': document.get('send_sample'),
            'response_sample': document.get('receive_sample'),
        })
    if not endpoints:
        raise SpecParseError('WS 契约没有可用端点')
    return {'kind': 'WS', 'endpoints': endpoints,
            'auth_schemes': auth_schemes, 'url': url,
            'protocols': document.get('protocols') or document.get('protocol')}


_SERVICE_PATTERN = re.compile(r'service\s+(\w+)\s*\{([^}]*)\}')
_RPC_PATTERN = re.compile(
    r'rpc\s+(\w+)\s*\(\s*(?:stream\s+)?([\w.]+)\s*\)\s*returns\s*'
    r'\(\s*(?:stream\s+)?([\w.]+)\s*\)')
_MESSAGE_PATTERN = re.compile(r'message\s+(\w+)\s*\{([^}]*)\}')
_FIELD_PATTERN = re.compile(
    r'(?:^|;|\{|\n)\s*(?:repeated\s+|optional\s+|required\s+)?'
    r'([\w.]+)\s+(\w+)\s*=\s*\d+')


def _parse_proto(text: str, endpoint: Optional[str]) -> Dict[str, Any]:
    body = (text or '').strip()
    if not body:
        raise SpecParseError('proto 契约内容为空')
    messages: Dict[str, List[Dict[str, Any]]] = {}
    for name, inner in _MESSAGE_PATTERN.findall(body):
        fields = [{'name': field, 'type': field_type, 'in': 'message',
                   'required': False}
                  for field_type, field in _FIELD_PATTERN.findall(inner)]
        messages[name] = fields
    services = _SERVICE_PATTERN.findall(body)
    if not services:
        raise SpecParseError('proto 契约里没有 service 定义')
    endpoints: List[Dict[str, Any]] = []
    package = re.search(r'^\s*package\s+([\w.]+)\s*;', body, re.MULTILINE)
    prefix = f'{package.group(1)}.' if package else ''
    for service_name, inner in services:
        for method, request, response in _RPC_PATTERN.findall(inner):
            path = f'{prefix}{service_name}/{method}'
            if endpoint and endpoint.lower() not in path.lower():
                continue
            endpoints.append({
                'method': 'GRPC',
                'path': path,
                'operation_id': f'{service_name}.{method}',
                'summary': None,
                'params': list(messages.get(request.split('.')[-1], [])),
                'auth': [],
                'request_sample': {field['name']: field['type']
                                   for field in messages.get(
                                       request.split('.')[-1], [])},
                'response_sample': {field['name']: field['type']
                                    for field in messages.get(
                                        response.split('.')[-1], [])},
            })
    if not endpoints:
        raise SpecParseError('proto 契约没有可用 rpc')
    return {
        'kind': 'PROTO', 'endpoints': endpoints, 'auth_schemes': [],
        'notes': ['proto 契约不含鉴权声明：鉴权以服务端拦截器 / 元数据为准，'
                  '本工具不推断 token 位置'],
        'package': prefix.rstrip('.') or None,
        'messages': sorted(messages),
    }


def parse_api_spec(content: Any, *, kind: Optional[str] = None,
                   endpoint: Optional[str] = None) -> Dict[str, Any]:
    """解析契约（OpenAPI / proto / WS），输出端点 + 鉴权 + 请求响应样例。

    **不发起任何真实调用**；``kind`` 缺省按内容推断（proto 文本 → PROTO，
    含 ``openapi``/``swagger``/``paths`` → OPENAPI，其余 JSON → WS）。
    """
    normalized = str(kind or '').strip().upper() or None
    if normalized is not None and normalized not in CONTRACT_KINDS:
        raise SpecParseError(
            f'不支持的契约类型：{kind}（可选 {" / ".join(CONTRACT_KINDS)}）')
    text = content if isinstance(content, str) else None
    if normalized is None:
        if text and re.search(r'^\s*service\s+\w+', text, re.MULTILINE):
            normalized = 'PROTO'
        elif text and re.search(r'^\s*(openapi|swagger)\s*:', text, re.MULTILINE):
            normalized = 'OPENAPI'
        else:
            normalized = 'OPENAPI'
    if normalized == 'PROTO':
        if not isinstance(content, str):
            raise SpecParseError('proto 契约必须以文本提供')
        return _parse_proto(content, endpoint)
    document = _load_structured(content, normalized)
    if normalized == 'WS':
        return _parse_ws(document, endpoint)
    if isinstance(document, dict) and (
            'paths' in document or 'openapi' in document
            or 'swagger' in document):
        return _parse_openapi(document, endpoint)
    # 没有 paths 的 JSON：WS 契约（channels / messages / url）再试一次
    if isinstance(document, dict) and (
            'channels' in document or 'messages' in document or 'url' in document):
        return _parse_ws(document, endpoint)
    raise SpecParseError('契约格式无法识别：既不是 OpenAPI（缺 paths），'
                         '也不是 WS（缺 url / channels / messages）')


def summarize_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """解析结果摘要（工具响应里的计数，避免模型只看端点总量）。"""
    endpoints = spec.get('endpoints') or []
    return {
        'kind': spec.get('kind'),
        'endpoints': len(endpoints),
        'methods': sorted({item.get('method') for item in endpoints
                           if item.get('method')}),
        'auth_schemes': len(spec.get('auth_schemes') or ()),
    }


__all__ = [
    'ARTIFACT_KIND_UI_TRACE', 'CONTRACT_KINDS', 'DEFAULT_TREE_NODES',
    'ExplorationBudget', 'ExplorationStopReason', 'LOCATOR_FALLBACK_REASON_KEY',
    'LOCATOR_STABLE_KEYS', 'LOCATOR_TEXT_KEYS', 'MAX_ACTIONS',
    'MAX_DURATION_SECONDS', 'MAX_SCREENSHOTS', 'MAX_TRACE_BYTES',
    'MAX_TRACE_PAGES', 'MAX_TREE_NODES', 'NODE_FIELDS', 'SpecParseError',
    'TRACE_MIN_PAGES', 'TRACE_TEXT_CAP', 'UI_TRACE_FILENAME', 'UiActionType',
    'UiBlockedPage', 'UiTreeParseError',
    'build_action_record', 'build_locator', 'build_page_record',
    'build_ui_trace', 'coverage_notes', 'crop_nodes', 'detect_blocked_page',
    'detect_destructive', 'diff_trees', 'fit_trace_to_bytes', 'node_key',
    'nodes_for_response', 'normalize_node', 'parse_android_hierarchy',
    'parse_api_spec', 'parse_bounds', 'parse_harmony_components',
    'stop_reason_for_page', 'summarize_spec', 'trace_bytes',
    'validation_report',
]
