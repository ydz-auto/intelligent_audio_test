# -*- coding: utf-8 -*-
"""报告配置值对象（封装 Report.config JSON 字段）"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class ReportConfig:
    """报告配置值对象（封装 Report.config JSON 字段）。

    用于在领域层传递报告生成选项，避免直接操作裸 dict。
    """
    report_type: str = 'standard'
    include_raw: bool = False
    include_charts: bool = False
    format: str = 'json'

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReportConfig':
        """从字典构造（容忍 None）。"""
        if not data:
            return cls()
        return cls(
            report_type=data.get('report_type', 'standard'),
            include_raw=bool(data.get('include_raw', False)),
            include_charts=bool(data.get('include_charts', False)),
            format=data.get('format', 'json'),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            'report_type': self.report_type,
            'include_raw': self.include_raw,
            'include_charts': self.include_charts,
            'format': self.format,
        }
