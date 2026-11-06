# -*- coding: utf-8 -*-
"""E2E 测试领域服务。

领域服务封装了不属于单一实体的领域逻辑。E2EOrchestrator 负责编排
E2ETestSession 的生命周期状态转换与设备会话协调，但不包含任何 IO
（数据库、gRPC、文件系统），保证领域层的纯粹性。

实际的 IO 调用由应用层（application/handlers/）委托给
已有的 core/ 模块（e2e_service / e2e_executor）完成。

re-export：本包同时作为各服务子模块的统一入口。
"""

from typing import Optional

from e2e_test_service.domain.entities import E2ETestSession, DeviceSession
from e2e_test_service.domain.value_objects import DeviceId, TestResult
from e2e_test_service.domain.events import (
    TestStarted,
    DeviceConnected,
    TestCompleted,
)


class E2EOrchestrator:
    """E2E 测试编排领域服务

    职责：
    - 根据设备信息构建 DeviceSession 列表
    - 驱动 E2ETestSession 的状态转换
    - 收集并归并测试结果

    本类不直接执行任何 IO，仅操作领域对象。
    """

    @staticmethod
    def create_session(task_id: str, tc_rel_id: str) -> E2ETestSession:
        """创建一个新的 E2E 测试会话（聚合根）"""
        return E2ETestSession(task_id=task_id, tc_rel_id=tc_rel_id)

    @staticmethod
    def register_device(session: E2ETestSession, device_id: int,
                        device_sn: str, device_name: str,
                        driver: Optional[str] = None,
                        prompt_audio_path: Optional[str] = None,
                        prompt_audio_name: Optional[str] = None,
                        needs_prompt_audio: bool = False) -> DeviceSession:
        """向会话注册一台被测设备，返回构建好的 DeviceSession"""
        ds = DeviceSession(
            device_id=DeviceId(device_id),
            device_sn=device_sn,
            device_name=device_name,
            driver=driver,
            prompt_audio_path=prompt_audio_path,
            prompt_audio_name=prompt_audio_name,
            needs_prompt_audio=needs_prompt_audio,
        )
        session.add_device_session(ds)
        return ds

    @staticmethod
    def start(session: E2ETestSession) -> TestStarted:
        """启动会话，返回 TestStarted 事件"""
        session.mark_running()
        return TestStarted(
            task_id=session.task_id,
            tc_rel_id=session.tc_rel_id,
        )

    @staticmethod
    def connect_device(session: E2ETestSession, device_id: str) -> Optional[DeviceConnected]:
        """连接指定设备，返回 DeviceConnected 事件"""
        for ds in session.device_sessions:
            if str(ds.device_id) == device_id:
                ds.connect()
                return DeviceConnected(
                    task_id=session.task_id,
                    device_id=device_id,
                    device_sn=ds.device_sn,
                )
        return None

    @staticmethod
    def record_progress(session: E2ETestSession, round_idx: int, total_rounds: int):
        """记录轮次进度"""
        session.update_round_progress(round_idx, total_rounds)

    @staticmethod
    def collect_result(session: E2ETestSession, result: TestResult):
        """收集单次测试结果"""
        session.add_result(result)

    @staticmethod
    def finish(session: E2ETestSession, success: bool,
               error_message: Optional[str] = None) -> TestCompleted:
        """结束会话，返回 TestCompleted 事件"""
        if success:
            session.mark_completed()
        else:
            session.mark_failed()
        return TestCompleted(
            task_id=session.task_id,
            tc_rel_id=session.tc_rel_id,
            success=success,
            round_count=len(session.round_progress),
            error_message=error_message,
        )

    @staticmethod
    def stop(session: E2ETestSession):
        """请求停止会话（非终态，等待实际停止后由 finish 收尾）"""
        session.mark_stopping()


# ---- 本地服务子模块 ----

from e2e_test_service.domain.services.upload_scheduler import UploadScheduler
from e2e_test_service.domain.services.e2e_calculation_service import (
    E2ECalculationService,
)

__all__ = [
    # E2E 编排
    "E2EOrchestrator",
    # 上传调度
    "UploadScheduler",
    # E2E 纯领域计算
    "E2ECalculationService",
]
