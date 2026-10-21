# -*- coding: utf-8 -*-
"""OpenAI 密钥链解析（INT-70 / INT-1177，Infrastructure 层密钥提供者）。

设计依据：API测试功能设计文档 §3.7/§8.1、04_类设计 §3.2.2、
01_UseCase总览 UC-0901 扩展流程 3a ——
`case_config.api_key → api_config.meta.api_key → env OPENAI_API_KEY`
逐级回退；密钥解析统一收敛在密钥提供者，Domain 层只见解析结果。
各级键名与环境变量名均可配置（默认值对齐设计约定），禁止硬编码密钥。

INT-1177 密钥池扩展：
- 新增 `resolve_rotating()`：候选优先级 = case 层（单值，最高优先，不变）
  → `meta.api_keys`（轮换池）→ `meta.api_key`（单值回退）→ 服务配置层 → env。
- 轮换状态（round-robin 游标 + 冷却集合）经模块级共享单例
  `RotationStateStore`（按 api_id 维度，线程安全）维护——所有消费面
  （HTTP / Realtime）经同一模块引用同一单例，实现同一 API 跨协议同源轮换。
  `RotationStateStore` 抽象为端口，首版进程内实现；Redis 跨副本实现列后续增强。
- `resolve()` 单值语义保持不变（向后兼容，4 消费面零回归）。
"""
import os
import threading
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Sequence

DEFAULT_CASE_KEY = 'api_key'
DEFAULT_META_KEY = 'api_key'
DEFAULT_API_KEYS_KEY = 'api_keys'
DEFAULT_ENV_KEY = 'OPENAI_API_KEY'
DEFAULT_COOLDOWN_SECONDS = 60


class RotationStateStore(ABC):
    """轮换状态存储端口（INT-1177）— 按 api_id 维度维护 round-robin 游标
    + 冷却集合（线程安全）。首版进程内实现；Redis 跨副本实现列后续增强，
    消费面只依赖本端口，换实现零改动。
    """

    @abstractmethod
    def next_index(self, api_id, pool: Sequence[str], cooldown_seconds: float) -> int:
        """返回下一个非冷却 key 下标并前移游标；全冷却返回 -1。"""

    @abstractmethod
    def has_available(self, api_id, pool: Sequence[str], cooldown_seconds: float) -> bool:
        """是否存在非冷却 key（不改变游标）。"""

    @abstractmethod
    def mark_failure(self, api_id, value: str, cooldown_seconds: float) -> None:
        """将某 key 值置冷却（冷却期内不再选中）。"""


class InMemoryRotationStateStore(RotationStateStore):
    """进程内轮换状态实现：dict[api_id] → {cursor, cooldown{value: until_ts}}。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._cursor: Dict[object, int] = {}
        self._cooldown: Dict[object, Dict[str, float]] = {}

    def _effective_cooled(self, api_id, cooldown_seconds) -> Dict[str, float]:
        """清洗过期冷却项后返回当前冷却集合（调用方须持锁）。"""
        now = time.time()
        cooled = self._cooldown.setdefault(api_id, {})
        expired = [v for v, until in cooled.items() if until <= now]
        for v in expired:
            cooled.pop(v, None)
        return cooled

    def next_index(self, api_id, pool, cooldown_seconds):
        with self._lock:
            cooled = self._effective_cooled(api_id, cooldown_seconds)
            n = len(pool)
            cursor = self._cursor.get(api_id, 0)
            for offset in range(n):
                idx = (cursor + offset) % n
                if pool[idx] not in cooled:
                    self._cursor[api_id] = (idx + 1) % n
                    return idx
            return -1

    def has_available(self, api_id, pool, cooldown_seconds):
        with self._lock:
            cooled = self._effective_cooled(api_id, cooldown_seconds)
            return any(v not in cooled for v in pool)

    def mark_failure(self, api_id, value, cooldown_seconds):
        with self._lock:
            self._cooldown.setdefault(api_id, {})[value] = \
                time.time() + cooldown_seconds


# 模块级共享单例：所有消费面（HTTP/Realtime/…）经同一模块引用，跨协议同源轮换
_rotation_store = InMemoryRotationStateStore()


def get_rotation_store() -> RotationStateStore:
    """获取轮换状态存储单例（端口引用；测试可注入替换实现）。"""
    return _rotation_store


class ApiKeyChainResolver:
    """密钥链逐级回退解析器（case_config → meta → 服务配置层 → env）。

    resolve() 按序取第一个非空候选；全部为空时回退环境变量
    （默认 OPENAI_API_KEY）。各级键名经构造参数注入，由调用方
    服务自己的配置源（yml / config_manager）提供。

    resolve_rotating()（INT-1177）在 resolve() 基础上新增密钥池轮换：
    case 层单值最高优先（不变）；`meta.api_keys` 池 round-robin 轮换，
    失败经 report_failure 置冷却（冷却期不选）；池全冷却返回空串。
    """

    def __init__(self, case_key=DEFAULT_CASE_KEY, meta_key=DEFAULT_META_KEY,
                 env_key=DEFAULT_ENV_KEY, api_keys_key=DEFAULT_API_KEYS_KEY,
                 cooldown_seconds=DEFAULT_COOLDOWN_SECONDS):
        self.case_key = case_key
        self.meta_key = meta_key
        self.env_key = env_key
        self.api_keys_key = api_keys_key
        self.cooldown_seconds = cooldown_seconds
        # 轮换状态经模块级共享单例（跨协议同源）；端口可替换（Redis 后续增强）
        self.rotation_store = get_rotation_store()

    def resolve(self, case_config=None, meta=None, service_candidates=None,
                case_value=None, meta_value=None) -> str:
        """按密钥链顺序解析，返回首个非空候选（去首尾空白）。

        :param case_config: 用例配置 dict（取 case_key 字段）
        :param meta: API meta dict（取 meta_key 字段）
        :param service_candidates: 服务配置层候选序列（依序，
            如 application.yml vendor 层 api_key，env 替换后的值）
        :param case_value: 跨服务下发场景的 case 层直接候选值
            （执行侧按配置键名提取后随 vendor_config 传递）
        :param meta_value: 跨服务下发场景的 meta 层直接候选值
        """
        candidates = (
            case_value if case_value else (case_config or {}).get(self.case_key),
            meta_value if meta_value else (meta or {}).get(self.meta_key),
            *(service_candidates or ()),
        )
        for candidate in candidates:
            if candidate:
                return str(candidate).strip()
        return os.environ.get(self.env_key, '').strip()

    # ── INT-1177 密钥池（轮换解析） ──

    def rotating_pool(self, meta) -> List[str]:
        """meta.api_keys 清洗后的轮换池（非空字符串元素；空/非数组 = 无池）。"""
        api_keys = (meta or {}).get(self.api_keys_key)
        if not isinstance(api_keys, list):
            return []
        return [str(k).strip() for k in api_keys
                if k is not None and str(k).strip()]

    def resolve_rotating(self, api_id, case_config=None, meta=None,
                         service_candidates=None, case_value=None,
                         meta_value=None) -> str:
        """轮换解析：case 层单值最高优先（不变）→ meta.api_keys 轮换池
        → 回退单值链（resolve() 语义）。

        :param api_id: API 配置 ID（轮换状态维度；同一 API 跨协议同源）
        :param meta: API meta dict（取 api_keys_key 轮换池 / meta_key 单值回退）
        """
        case_val = case_value if case_value else (case_config or {}).get(self.case_key)
        if case_val:
            return str(case_val).strip()
        pool = self.rotating_pool(meta)
        if pool:
            idx = self.rotation_store.next_index(
                api_id, pool, self.cooldown_seconds)
            if idx >= 0:
                return pool[idx]
            # 池全冷却：返回空串（调用方不注入 Authorization，立即失败语义）
            return ''
        return self.resolve(case_config=case_config, meta=meta,
                            service_candidates=service_candidates,
                            case_value=case_value, meta_value=meta_value)

    def has_available_rotating_key(self, api_id, meta) -> bool:
        """池是否存在非冷却 key；无池返回 False（调用方按单值/无 key 处理）。"""
        pool = self.rotating_pool(meta)
        if not pool:
            return False
        return self.rotation_store.has_available(
            api_id, pool, self.cooldown_seconds)

    def report_failure(self, api_id, failed_value, cooldown_seconds=None) -> None:
        """报告轮换池中某 key 失败：置冷却（冷却期默认 60s，可配置）。

        非池内 value 静默忽略（幂等；空值 no-op）。
        """
        if not failed_value:
            return
        cooldown = (cooldown_seconds if cooldown_seconds is not None
                    else self.cooldown_seconds)
        self.rotation_store.mark_failure(api_id, str(failed_value), cooldown)


def resolver_from_config(get_value, section='secrets') -> ApiKeyChainResolver:
    """从配置源构建解析器（各级键名与环境变量名均可配置）。

    :param get_value: 配置读取函数，签名 (section, key, default)
        （如 config_manager.get_value）
    """
    raw_cooldown = get_value(section, 'cooldown_seconds', DEFAULT_COOLDOWN_SECONDS)
    try:
        cooldown = int(raw_cooldown)
    except (TypeError, ValueError):
        cooldown = DEFAULT_COOLDOWN_SECONDS
    return ApiKeyChainResolver(
        case_key=get_value(section, 'case_config_key', DEFAULT_CASE_KEY),
        meta_key=get_value(section, 'meta_key', DEFAULT_META_KEY),
        env_key=get_value(section, 'env_key', DEFAULT_ENV_KEY),
        api_keys_key=get_value(section, 'api_keys_key', DEFAULT_API_KEYS_KEY),
        cooldown_seconds=cooldown,
    )
