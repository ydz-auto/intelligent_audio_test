# -*- coding: utf-8 -*-
"""领域服务 — 封装不属于单一实体的领域逻辑，纯逻辑，无 IO。"""
from api_test_service.domain.value_objects import ConcurrencyConfig
from api_test_service.domain.entities import APITestSession, SessionStatus


class ConcurrencyValidator:
    """并发验证领域服务

    封装对并发配置与会话状态的纯逻辑校验，不涉及任何 IO。
    """

    @staticmethod
    def validate_config(config: ConcurrencyConfig) -> None:
        """校验并发配置合法性"""
        if config.max_process < 1:
            raise ValueError(f"max_process 必须 >= 1，当前: {config.max_process}")
        if config.max_wait_time < 0:
            raise ValueError(f"max_wait_time 不能为负，当前: {config.max_wait_time}")
        if config.task_pool_size < 1:
            raise ValueError(
                f"task_pool_size 必须 >= 1，当前: {config.task_pool_size}"
            )

    @staticmethod
    def can_acquire(session: APITestSession, api_id: int) -> bool:
        """判断给定会话是否允许为指定 API 获取执行权

        仅当会话处于运行态且未请求停止时返回 True。
        """
        if session.status != SessionStatus.RUNNING:
            return False
        if session.stop_requested:
            return False
        if api_id not in session.api_ids:
            return False
        return True

    @staticmethod
    def validate_acquire(session: APITestSession, api_id: int) -> None:
        """校验获取执行权的前置条件，失败抛出 ValueError"""
        if session.status != SessionStatus.RUNNING:
            raise ValueError(
                f"会话 {session.session_id} 未运行，状态: {session.status}"
            )
        if session.stop_requested:
            raise ValueError(f"会话 {session.session_id} 已请求停止")
        if api_id not in session.api_ids:
            raise ValueError(
                f"API {api_id} 不属于会话 {session.session_id} 的 api 集合"
            )

    @staticmethod
    def should_timeout(start_time: float, config: ConcurrencyConfig,
                       current_time: float) -> bool:
        """判断并发等待是否超时"""
        return (current_time - start_time) >= config.max_wait_time
