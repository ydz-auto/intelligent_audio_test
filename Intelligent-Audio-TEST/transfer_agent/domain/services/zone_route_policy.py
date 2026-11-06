# -*- coding: utf-8 -*-
"""区路由策略 — 5 层安全基座的网络隔离点 + 内容层。

校验 (src_zone, dst_zone, pkg_type) 三元组是否在白名单内：
- A↔C 物理不直连，任何包类型拒绝（必须经 B 中继）
- B→C 仅放行 EVAL_REQUEST（C 入口只收评估输入包）
- C→B 放行 EVAL_RESULT / C_REPORT / C_RESULT
- A↔B 双向放行数据/报告/评估互传

默认矩阵对齐设计文档 09_跨区网络传输方案 §3.2/§4.4/§5.3.1，
可通过 route_policy_file（JSON）整体覆盖以支持备选方案演进。
"""
from __future__ import annotations

import json
import os
from typing import Dict, FrozenSet, Optional, Set

from shared.models.common_enums import PkgType

from transfer_agent.domain.errors import InvalidPackageFieldError, RouteNotAllowedError


# 默认路由白名单：{(src, dst): {pkg_type, ...}}
DEFAULT_ROUTES: Dict[tuple, Set[str]] = {
    ('A', 'B'): {PkgType.EVAL_REQUEST, PkgType.EVAL_RESULT, PkgType.REPORT_SYNC, PkgType.DATA_SYNC},
    ('B', 'A'): {PkgType.EVAL_REQUEST, PkgType.EVAL_RESULT, PkgType.REPORT_SYNC, PkgType.DATA_SYNC},
    ('B', 'C'): {PkgType.EVAL_REQUEST},
    ('C', 'B'): {PkgType.EVAL_RESULT, PkgType.C_REPORT, PkgType.C_RESULT},
}

VALID_ZONES: FrozenSet[str] = frozenset({'A', 'B', 'C'})


class ZoneRoutePolicy:
    """路由白名单校验（fail-closed：未知区/未知包类型/未登记路由一律拒绝）。"""

    def __init__(self, routes: Optional[Dict[tuple, Set[str]]] = None,
                 policy_file: Optional[str] = None):
        if policy_file:
            self._routes = self._load_from_file(policy_file)
        elif routes:
            self._routes = routes
        else:
            self._routes = {k: set(v) for k, v in DEFAULT_ROUTES.items()}

    @staticmethod
    def _load_from_file(path: str) -> Dict[tuple, Set[str]]:
        """策略文件格式：{"routes": [{"src": "A", "dst": "B", "pkg_types": [...]}, ...]}"""
        if not path or not os.path.isfile(path):
            raise InvalidPackageFieldError(f'路由策略文件不存在: {path}')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f) or {}
        routes: Dict[tuple, Set[str]] = {}
        for item in data.get('routes', []):
            key = (str(item['src']).upper(), str(item['dst']).upper())
            routes[key] = {PkgType(p).value for p in item.get('pkg_types', [])}
        return routes

    def is_allowed(self, src_zone: str, dst_zone: str, pkg_type: str) -> bool:
        try:
            pkg = PkgType(str(pkg_type).upper())
        except ValueError:
            return False
        src, dst = str(src_zone).upper(), str(dst_zone).upper()
        allowed = self._routes.get((src, dst), set())
        return pkg.value in allowed

    def check(self, src_zone: str, dst_zone: str, pkg_type: str) -> None:
        src, dst = str(src_zone).upper(), str(dst_zone).upper()
        if src not in VALID_ZONES or dst not in VALID_ZONES:
            raise InvalidPackageFieldError(f'非法区标识: src={src_zone}, dst={dst_zone}')
        try:
            PkgType(str(pkg_type).upper())
        except ValueError:
            raise InvalidPackageFieldError(f'非法包类型 pkg_type: {pkg_type}')
        if not self.is_allowed(src, dst, pkg_type):
            raise RouteNotAllowedError(
                f'路由 {src}->{dst} 不允许包类型 {pkg_type}'
                f'（网络隔离点/内容层白名单拒绝）'
            )
