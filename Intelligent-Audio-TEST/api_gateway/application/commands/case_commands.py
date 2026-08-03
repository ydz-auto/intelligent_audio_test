"""api_gateway 应用层 —— 命令（写操作）

CQRS Command 侧：写操作通过 gRPC 转发到对应服务。

映射关系：
- TestCase CRUD     → 本地 DB（网关侧直接操作）
- Task 执行/停止    → task_service gRPC
- E2E 测试执行      → e2e_test_service gRPC
- API 测试执行      → api_test_service gRPC
- 报告生成          → task_service gRPC（触发 SSE 事件）
- Audio 上传        → e2e_test_service gRPC + OSS
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class CreateTestCaseCommand:
    """创建测试用例"""
    name: str
    description: str = ''
    group_id: Optional[str] = None
    algorithm_type: str = 'default'
    config: Dict[str, Any] = None
    tags: List[str] = None


@dataclass
class UpdateTestCaseCommand:
    """更新测试用例"""
    tc_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    group_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


@dataclass
class DeleteTestCaseCommand:
    """删除测试用例"""
    tc_id: str


@dataclass
class StartTaskCommand:
    """启动任务 —— 转发到 task_service"""
    task_id: str


@dataclass
class StopTaskCommand:
    """停止任务 —— 转发到 task_service"""
    task_id: str


@dataclass
class GenerateReportCommand:
    """生成报告 —— 转发到 task_service"""
    task_id: str
    report_type: str = 'task'


@dataclass
class UploadAudioCommand:
    """上传音频 —— 存储到 OSS"""
    file_path: str
    file_name: str
    md5: Optional[str] = None


@dataclass
class BatchImportCasesCommand:
    """批量导入用例"""
    file_path: str
    group_id: Optional[str] = None
