# -*- coding: utf-8 -*-
"""有效上下文窗口解析器（§6.4-9 / §8.3）。

唯一事实源：使用者覆盖 → 目录默认（协议 + 模型名）→ 128k 兜底，并记录
``ContextWindowSource``。INT-2454 的压缩算法与 run 预算都只能调用本模块，
不得另写一套阈值解析。

数值口径：
- 覆盖值必须落在 ``bounds``（默认 8k–2M）且按 ``alignment``（默认 1024）对齐；
- 覆盖值高于目录默认值时允许保存，但返回告警（预算仍按覆盖值计算）；
- 单轮输出预留 = ``min(cap, floor(10% × W, alignment))``；
- 压缩阈值按「可用窗口 = W − 输出预留」的 60% / 80% 计算，只产出数值，
  压缩动作由 INT-2454 落地。
"""
import fnmatch
import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from agent_service.domain.enums import ContextWindowSource, LlmProtocol
from agent_service.domain.exceptions import InvalidContextWindow

DEFAULT_CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'config', 'model_catalog.json')

DEFAULT_FALLBACK_CONTEXT_WINDOW = 131072
DEFAULT_MIN_CONTEXT_WINDOW = 8192
DEFAULT_MAX_CONTEXT_WINDOW = 2097152
DEFAULT_ALIGNMENT = 1024

WARNING_ABOVE_CATALOG = 'CONTEXT_WINDOW_ABOVE_CATALOG'


@dataclass(frozen=True)
class WindowBounds:
    min: int = DEFAULT_MIN_CONTEXT_WINDOW
    max: int = DEFAULT_MAX_CONTEXT_WINDOW
    alignment: int = DEFAULT_ALIGNMENT


@dataclass(frozen=True)
class CatalogEntry:
    protocol: str
    match: str
    context_window: int
    max_output_tokens: int


@dataclass(frozen=True)
class WindowResolution:
    effective_context_window: int
    source: ContextWindowSource
    catalog_context_window: Optional[int] = None
    catalog_max_output_tokens: Optional[int] = None
    warning: Optional[str] = None
    warning_message: Optional[str] = None


class ContextWindowResolver:
    """按模型目录解析有效窗口；同时提供预算 / 压缩阈值派生函数。"""

    def __init__(self, *, entries: Sequence[CatalogEntry],
                 fallback_context_window: int = DEFAULT_FALLBACK_CONTEXT_WINDOW,
                 bounds: Optional[WindowBounds] = None):
        self._entries: List[CatalogEntry] = list(entries)
        self._fallback = int(fallback_context_window)
        self._bounds = bounds or WindowBounds()

    # ------------------------------------------------------------ loading

    @classmethod
    def from_dict(cls, data: Dict) -> 'ContextWindowResolver':
        bounds_raw = data.get('bounds') or {}
        bounds = WindowBounds(
            min=int(bounds_raw.get('min', DEFAULT_MIN_CONTEXT_WINDOW)),
            max=int(bounds_raw.get('max', DEFAULT_MAX_CONTEXT_WINDOW)),
            alignment=int(bounds_raw.get('alignment', DEFAULT_ALIGNMENT)),
        )
        entries = [
            CatalogEntry(
                protocol=str(item.get('protocol') or '*'),
                match=str(item.get('match') or ''),
                context_window=int(item.get('context_window') or 0),
                max_output_tokens=int(item.get('max_output_tokens') or 0),
            )
            for item in (data.get('models') or [])
        ]
        return cls(
            entries=entries,
            fallback_context_window=int(
                data.get('fallback_context_window')
                or DEFAULT_FALLBACK_CONTEXT_WINDOW),
            bounds=bounds,
        )

    @classmethod
    def from_file(cls, path: Optional[str] = None) -> 'ContextWindowResolver':
        catalog_path = path or DEFAULT_CATALOG_PATH
        with open(catalog_path, encoding='utf-8') as handle:
            return cls.from_dict(json.load(handle))

    # ------------------------------------------------------------ accessors

    @property
    def fallback_context_window(self) -> int:
        return self._fallback

    @property
    def bounds(self) -> WindowBounds:
        return self._bounds

    @property
    def entries(self) -> Tuple[CatalogEntry, ...]:
        return tuple(self._entries)

    def match(self, protocol: LlmProtocol,
              model: str) -> Optional[CatalogEntry]:
        """协议 + 模型名匹配目录项（首个命中生效，支持 glob）。"""
        protocol_value = protocol.value if hasattr(protocol, 'value') else str(protocol)
        wanted = (model or '').strip().lower()
        if not wanted:
            return None
        for entry in self._entries:
            if entry.protocol not in ('*', protocol_value):
                continue
            if fnmatch.fnmatchcase(wanted, entry.match.lower()):
                return entry
        return None

    def as_catalog_dict(self) -> Dict:
        """GET /model-catalog 的响应体（供表单预填）。"""
        return {
            'fallback_context_window': self._fallback,
            'bounds': {
                'min': self._bounds.min,
                'max': self._bounds.max,
                'alignment': self._bounds.alignment,
            },
            'models': [
                {
                    'protocol': entry.protocol,
                    'match': entry.match,
                    'context_window': entry.context_window,
                    'max_output_tokens': entry.max_output_tokens,
                }
                for entry in self._entries
            ],
        }

    # ------------------------------------------------------------ resolution

    def validate_override(self, value: int) -> int:
        """校验用户覆盖值；非法抛 InvalidContextWindow（接口层映射 400）。"""
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidContextWindow('上下文窗口必须是整数')
        if value < self._bounds.min or value > self._bounds.max:
            raise InvalidContextWindow(
                f'上下文窗口需在 {self._bounds.min}–{self._bounds.max} 之间')
        if self._bounds.alignment > 0 and value % self._bounds.alignment != 0:
            raise InvalidContextWindow(
                f'上下文窗口需按 {self._bounds.alignment} 对齐')
        return value

    def resolve(self, protocol: LlmProtocol, model: str,
                override: Optional[int] = None) -> WindowResolution:
        entry = self.match(protocol, model)
        if override is not None:
            self.validate_override(int(override))
            window = int(override)
            warning = None
            message = None
            catalog_window = entry.context_window if entry else None
            if catalog_window and window > catalog_window:
                warning = WARNING_ABOVE_CATALOG
                message = (f'覆盖值 {window} 高于目录默认 {catalog_window}，'
                           f'预算按覆盖值计算')
            return WindowResolution(
                effective_context_window=window,
                source=ContextWindowSource.USER_OVERRIDE,
                catalog_context_window=catalog_window,
                catalog_max_output_tokens=(
                    entry.max_output_tokens if entry else None),
                warning=warning, warning_message=message,
            )
        if entry is not None and entry.context_window > 0:
            return WindowResolution(
                effective_context_window=entry.context_window,
                source=ContextWindowSource.MODEL_DEFAULT,
                catalog_context_window=entry.context_window,
                catalog_max_output_tokens=entry.max_output_tokens,
            )
        return WindowResolution(
            effective_context_window=self._fallback,
            source=ContextWindowSource.FALLBACK,
        )

    # ------------------------------------------------------------ budgets

    def align_down(self, value: int) -> int:
        alignment = self._bounds.alignment
        if alignment <= 0:
            return int(value)
        return int(value) // alignment * alignment

    def output_token_limit(self, window: int, *, cap: int,
                           ratio: float,
                           protocol: Optional[LlmProtocol] = None,
                           model: str = '') -> int:
        """单轮输出预留：``min(cap, floor(ratio × W, alignment))``。

        目录给出的 ``max_output_tokens`` 是模型能力上限，超出的预留没有意义，
        因此同时取 min；结果至少为 1。
        """
        if window <= 0:
            return 0
        candidate = min(int(cap), self.align_down(max(1, int(window * ratio))))
        entry = self.match(protocol, model) if protocol else None
        if entry is not None and entry.max_output_tokens > 0:
            candidate = min(candidate, entry.max_output_tokens)
        return max(1, candidate)

    @staticmethod
    def token_budget(window: int, multiplier: int) -> int:
        """总 token 预算 = multiplier × W（默认 2×W，Auto 4×W）。"""
        if window <= 0 or multiplier <= 0:
            return 0
        return int(window) * int(multiplier)

    @staticmethod
    def compaction_thresholds(window: int, output_reserve: int, *,
                              soft_ratio: float,
                              hard_ratio: float) -> Tuple[int, int]:
        """返回 (软触发 token 数, 硬触发 token 数)，基于可用窗口。"""
        available = max(0, int(window) - int(output_reserve))
        return (int(available * soft_ratio), int(available * hard_ratio))


__all__ = [
    'CatalogEntry', 'ContextWindowResolver', 'DEFAULT_CATALOG_PATH',
    'WARNING_ABOVE_CATALOG', 'WindowBounds', 'WindowResolution',
]
