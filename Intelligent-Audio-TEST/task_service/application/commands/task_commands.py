# -*- coding: utf-8 -*-
"""任务命令定义 (Task Commands) - CQRS 写模型。

命令对象是不可变的意图描述，仅包含执行所需数据，不包含业务逻辑。
处理器消费命令并委托给 ExecutionEngine 等基础设施。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Command:
    """命令基类。所有命令返回 (success: bool, message: str)。"""
    pass


@dataclass(frozen=True)
class CreateTaskCommand(Command):
    """创建任务命令。

    ExecutionEngine 不提供独立的 create_task，
    实际 Task 记录由上层业务创建后通过 StartTaskCommand 启动。
    本命令用于在应用层显式建立任务记录。
    """
    name: str
    task_type: str = 'api'  # api / e2e
    description: str = ''
    config: Dict[str, Any] = field(default_factory=dict)
    algorithm_type: Optional[str] = None
    algorithm_params: Dict[str, Any] = field(default_factory=dict)
    case_ids: List[str] = field(default_factory=list)
    device_ids: List[int] = field(default_factory=list)
    api_ids: List[int] = field(default_factory=list)
    created_by: Optional[int] = None


@dataclass(frozen=True)
class StartTaskCommand(Command):
    """启动任务命令。委托给 ExecutionEngine.start_task。"""
    task_id: int


@dataclass(frozen=True)
class StopTaskCommand(Command):
    """停止任务命令。委托给 ExecutionEngine.control_task(task_id, 'stop')。"""
    task_id: int


@dataclass(frozen=True)
class PauseTaskCommand(Command):
    """暂停任务命令。委托给 ExecutionEngine.control_task(task_id, 'pause')。"""
    task_id: int


@dataclass(frozen=True)
class ResumeTaskCommand(Command):
    """恢复任务命令。委托给 ExecutionEngine.control_task(task_id, 'resume')。"""
    task_id: int


@dataclass(frozen=True)
class RemoveFromQueueCommand(Command):
    """从队列移除任务命令。委托给 ExecutionEngine.remove_from_queue。"""
    task_id: int


@dataclass(frozen=True)
class ReevaluateTaskCommand(Command):
    """重新评估任务命令。委托给 ReevaluationExecutor.submit。"""
    task_id: int
    reextract_device_output: bool = True
    reevaluate_type: str = 'all'  # all / failed


@dataclass(frozen=True)
class MergeTasksCommand(Command):
    """合并任务命令。

    将多个源任务的结果合并到一个新任务。
    参数由调用方提供源任务列表和合并后的任务配置。
    """
    source_task_ids: List[int]
    merged_task_name: str
    merged_task_type: str = 'api'
    description: str = ''
    created_by: Optional[int] = None


# ==================== task 域 CRUD/批量/合并命令（gRPC servicer 用） ====================
# 以下命令接收原始 data dict，委托 task_crud_service 旧服务作为过渡，
# 返回 dict: {success, message, data, code?}（与旧 service 返回格式一致）。


@dataclass(frozen=True)
class CreateTaskConfigCommand(Command):
    """创建任务配置命令（dict 参数版）。

    与 CreateTaskCommand 区别：接收网关透传的原始 data dict，
    供 gRPC TaskConfigServiceServicer 使用。委托 task_crud_service.create。
    """
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UpdateTaskCommand(Command):
    """更新任务配置命令（名称/描述）。委托 task_crud_service.update。"""
    task_id: int
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeleteTaskCommand(Command):
    """软删除任务命令。委托 task_crud_service.delete。"""
    task_id: int


@dataclass(frozen=True)
class UpdateTaskCasesCommand(Command):
    """动态添加/移除任务用例命令。委托 task_crud_service.update_cases。"""
    task_id: int
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BatchActionTaskCommand(Command):
    """任务批量操作命令（delete/export）。委托 task_crud_service.batch_action。"""
    data: Dict[str, Any] = field(default_factory=dict)
    query_args: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class MergeTasksConfigCommand(Command):
    """合并任务命令（dict 参数版）。

    与 MergeTasksCommand 区别：接收原始 data dict（含 task_ids），
    供 gRPC TaskConfigServiceServicer 使用。委托 task_crud_service.merge。
    """
    data: Dict[str, Any] = field(default_factory=dict)


# ==================== task 域生命周期命令（gRPC servicer 用） ====================
# 委托 task_lifecycle_service 旧服务作为过渡，保留完整生命周期逻辑（状态校验等）。


@dataclass(frozen=True)
class StartTaskLifecycleCommand(Command):
    """启动任务生命周期命令。委托 task_lifecycle_service.start。"""
    task_id: int


@dataclass(frozen=True)
class RetryTaskCommand(Command):
    """重试失败用例命令。委托 task_lifecycle_service.retry。"""
    task_id: int


@dataclass(frozen=True)
class ControlTaskCommand(Command):
    """任务运行时控制命令（暂停/恢复/停止/跳过/单用例重试）。
    委托 task_lifecycle_service.control。
    """
    task_id: int
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StopTaskLifecycleCommand(Command):
    """停止任务生命周期命令。委托 task_lifecycle_service.stop。"""
    task_id: int


@dataclass(frozen=True)
class RextractTaskCommand(Command):
    """重新提取设备输出命令。委托 task_lifecycle_service.reextract。"""
    task_id: int
    data: Dict[str, Any] = field(default_factory=dict)


# ==================== testcase 域命令（gRPC servicer 用） ====================


@dataclass(frozen=True)
class CreateTestCaseCommand(Command):
    """创建测试用例命令。委托 testcase_crud_service.create。"""
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UpdateTestCaseCommand(Command):
    """更新测试用例命令。委托 testcase_crud_service.update。"""
    tc_id: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeleteTestCaseCommand(Command):
    """软删除测试用例命令。委托 testcase_crud_service.delete。"""
    tc_id: str


@dataclass(frozen=True)
class CopyTestCaseCommand(Command):
    """复制测试用例命令。委托 testcase_crud_service.copy。"""
    tc_id: str


@dataclass(frozen=True)
class BatchActionTestCaseCommand(Command):
    """测试用例批量操作命令。委托 testcase_crud_service.batch_action。

    TODO: batch_service 包含 14 种子操作（delete/move/copy/参数更新等），
    后续可拆分为独立 Command；当前作为过渡统一入口。
    """
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UpdateTestCaseRefParamsCommand(Command):
    """更新用例参考参数命令。委托 testcase_crud_service.update_ref_params。"""
    tc_id: str
    round_number: int
    data: Dict[str, Any] = field(default_factory=dict)


# ==================== tag 域命令（gRPC servicer 用） ====================


@dataclass(frozen=True)
class CreateTagCategoryCommand(Command):
    """创建标签分类命令。委托 tag_crud_service.create_category。"""
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UpdateTagCategoryCommand(Command):
    """更新标签分类命令。委托 tag_crud_service.update_category。"""
    category_id: int
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeleteTagCategoryCommand(Command):
    """删除标签分类命令。委托 tag_crud_service.delete_category。"""
    category_id: int


@dataclass(frozen=True)
class CreateTagCommand(Command):
    """创建标签命令。委托 tag_crud_service.create_tag。"""
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UpdateTagCommand(Command):
    """更新标签命令。委托 tag_crud_service.update_tag。"""
    tag_id: int
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeleteTagCommand(Command):
    """删除标签命令。委托 tag_crud_service.delete_tag。"""
    tag_id: int


@dataclass(frozen=True)
class BatchUpdateTagCategoryCommand(Command):
    """批量更新标签分类命令。委托 tag_crud_service.batch_update_category。"""
    data: Dict[str, Any] = field(default_factory=dict)
