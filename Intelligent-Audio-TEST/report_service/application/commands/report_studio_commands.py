# -*- coding: utf-8 -*-
"""Report Studio 命令（Command）对象（INT-673）

CQRS 写侧入口：命令是 immutable 的写意图描述，本身不包含业务逻辑。
Handler 接收命令后委托 ReportStudioService（领域编排）执行。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CreateStudioDocumentCommand:
    """用现有 reportId 创建草稿（可绑定已有 agentSessionId，可空）。"""
    data: Dict[str, Any]


@dataclass(frozen=True)
class CreateStudioUploadDocumentCommand:
    """文件型独立报告导入（INT-1763 §6.2）：source_type=uploaded_file 建文档。"""
    data: Dict[str, Any]


@dataclass(frozen=True)
class UpdateStudioDocumentCommand:
    """人工编辑：expected_version 乐观锁 + 幂等键；冲突 409 + 差异。"""
    data: Dict[str, Any]


@dataclass(frozen=True)
class RestoreStudioDocumentVersionCommand:
    """选定历史版本恢复为新版本（不覆盖），带 expected_version。"""
    data: Dict[str, Any]


@dataclass(frozen=True)
class CreateStudioExportJobCommand:
    """固定文档版本 + 格式 + 主题，创建导出异步作业。"""
    data: Dict[str, Any]
