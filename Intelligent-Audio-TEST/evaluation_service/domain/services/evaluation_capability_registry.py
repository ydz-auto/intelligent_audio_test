# -*- coding: utf-8 -*-
"""评估能力注册表 — 维度评估归属路由（LOCAL / THIRD_PARTY_C）。

设计文档 09_跨区网络传输方案 §4.1.1：配置化注册表决定每个维度的评估归属，
- LOCAL          走现有本区评估链路（EvaluateCase 不变）
- THIRD_PARTY_C  经 transfer_agent 传输链路调 C 第三方评估 API

能力面：注册（register）/ 发现（list/resolve）/ 禁用与启用（disable/enable），
配置持久化到 shared/config/evaluation_capability_config.json（原子写），
文件 mtime 变化自动热加载（运行时配置切换）。枚举化 + fail-closed：
非法 target/adapter 拒绝注册，未登记维度默认 LOCAL。
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from shared.models.common_enums import EvalCapabilityTarget, ThirdPartyAdapterKind

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
DEFAULT_CONFIG_PATH = os.path.join(
    _REPO_ROOT, 'shared', 'config', 'evaluation_capability_config.json')


@dataclass
class CapabilityEntry:
    """单条能力注册项。"""
    dimension: str
    target: EvalCapabilityTarget
    adapter: Optional[ThirdPartyAdapterKind] = None
    enabled: bool = True
    settings: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'dimension': self.dimension,
            'target': self.target.value,
            'adapter': self.adapter.value if self.adapter else None,
            'enabled': self.enabled,
            'settings': dict(self.settings),
        }


class EvaluationCapabilityRegistry:
    """评估能力注册表（线程安全 + 配置热加载）。"""

    def __init__(self, config_path: Optional[str] = None, persist: bool = True):
        self._config_path = config_path or os.environ.get(
            'EVALUATION_CAPABILITY_CONFIG_FILE', DEFAULT_CONFIG_PATH)
        self._persist = persist
        self._lock = threading.RLock()
        self._entries: Dict[str, CapabilityEntry] = {}
        self._loaded_mtime: Optional[float] = None
        self._reload_if_changed()

    # ---- 配置装载 ----
    def _reload_if_changed(self) -> None:
        try:
            mtime = os.path.getmtime(self._config_path) if os.path.isfile(self._config_path) else None
        except OSError:
            mtime = None
        if mtime is not None and mtime == self._loaded_mtime:
            return
        entries: Dict[str, CapabilityEntry] = {}
        if mtime is not None:
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f) or {}
                for item in data.get('dimension_capabilities', []):
                    entries[str(item['dimension'])] = self._build_entry(item)
            except Exception:
                logger.warning('评估能力配置加载失败（保持空注册表 fail-closed）: %s',
                               self._config_path, exc_info=True)
                entries = {}
        with self._lock:
            self._entries = entries
            self._loaded_mtime = mtime

    @staticmethod
    def _build_entry(item: dict) -> CapabilityEntry:
        dimension = str(item['dimension'])
        target = EvalCapabilityTarget(str(item.get('target', 'LOCAL')).upper())
        adapter_raw = item.get('adapter')
        adapter = None
        if adapter_raw:
            adapter = ThirdPartyAdapterKind(str(adapter_raw).lower())
        if target == EvalCapabilityTarget.THIRD_PARTY_C and adapter is None:
            adapter = ThirdPartyAdapterKind.MULTIPART
        if target == EvalCapabilityTarget.LOCAL:
            adapter = None
        return CapabilityEntry(
            dimension=dimension,
            target=target,
            adapter=adapter,
            enabled=bool(item.get('enabled', True)),
            settings=dict(item.get('settings') or {}),
        )

    def _save(self) -> None:
        """原子写回配置文件（tmp + os.replace，注册状态重启不丢）。"""
        if not self._persist:
            return
        with self._lock:
            entries = [e.to_dict() for e in self._entries.values()]
        data = {'dimension_capabilities': entries}
        tmp_path = f'{self._config_path}.tmp'
        os.makedirs(os.path.dirname(self._config_path) or '.', exist_ok=True)
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self._config_path)
        try:
            self._loaded_mtime = os.path.getmtime(self._config_path)
        except OSError:
            pass

    # ---- 能力面：注册 / 发现 / 禁用 ----
    def register(self, dimension: str, target: str,
                 adapter: Optional[str] = None, enabled: bool = True,
                 settings: Optional[dict] = None) -> dict:
        """注册/更新一个维度的评估能力归属（非法枚举 fail-closed 拒绝）。"""
        if not dimension or not str(dimension).strip():
            raise ValueError('dimension 必填')
        try:
            target_enum = EvalCapabilityTarget(str(target).upper())
        except ValueError:
            raise ValueError(f'非法评估归属 target: {target}（允许 LOCAL / THIRD_PARTY_C）')
        adapter_enum = None
        if adapter:
            try:
                adapter_enum = ThirdPartyAdapterKind(str(adapter).lower())
            except ValueError:
                raise ValueError(
                    f'非法第三方适配形态 adapter: {adapter}'
                    f'（允许 {", ".join(k.value for k in ThirdPartyAdapterKind)}）')
        if target_enum == EvalCapabilityTarget.THIRD_PARTY_C and adapter_enum is None:
            adapter_enum = ThirdPartyAdapterKind.MULTIPART
        if target_enum == EvalCapabilityTarget.LOCAL:
            adapter_enum = None
        entry = CapabilityEntry(
            dimension=str(dimension), target=target_enum, adapter=adapter_enum,
            enabled=bool(enabled), settings=dict(settings or {}))
        with self._lock:
            self._reload_if_changed()
            self._entries[entry.dimension] = entry
            self._save()
        logger.info('评估能力注册: %s', entry.to_dict())
        return entry.to_dict()

    def disable(self, dimension: str) -> dict:
        """禁用一个维度的第三方评估能力（禁用后 resolve 视为未命中 → LOCAL）。"""
        return self._set_enabled(dimension, False)

    def enable(self, dimension: str) -> dict:
        return self._set_enabled(dimension, True)

    def _set_enabled(self, dimension: str, enabled: bool) -> dict:
        with self._lock:
            self._reload_if_changed()
            entry = self._entries.get(str(dimension))
            if entry is None:
                raise KeyError(f'能力未注册: {dimension}')
            entry.enabled = enabled
            self._save()
            return entry.to_dict()

    def remove(self, dimension: str) -> bool:
        with self._lock:
            self._reload_if_changed()
            removed = self._entries.pop(str(dimension), None) is not None
            if removed:
                # 写回配置：否则 mtime 热加载后已移除条目会从文件复活
                self._save()
            return removed

    # ---- 发现 ----
    def list_capabilities(self) -> List[dict]:
        with self._lock:
            self._reload_if_changed()
            return [e.to_dict() for e in self._entries.values()]

    def get(self, dimension: str) -> Optional[CapabilityEntry]:
        with self._lock:
            self._reload_if_changed()
            return self._entries.get(str(dimension))

    def resolve(self, dimension_data: dict) -> Optional[CapabilityEntry]:
        """按维度数据解析能力归属（匹配键依次 task_type_code → name → id）。

        未登记或已禁用返回 None（调用方视为 LOCAL，走现有链路）。
        """
        if not isinstance(dimension_data, dict):
            return None
        candidates = [
            dimension_data.get('task_type_code'),
            dimension_data.get('name'),
            str(dimension_data.get('id')) if dimension_data.get('id') is not None else None,
        ]
        with self._lock:
            self._reload_if_changed()
            for key in candidates:
                if not key:
                    continue
                entry = self._entries.get(str(key))
                if entry is not None:
                    return entry if entry.enabled else None
        return None


# 模块级单例（接口层/调度层共用）
evaluation_capability_registry = EvaluationCapabilityRegistry()
