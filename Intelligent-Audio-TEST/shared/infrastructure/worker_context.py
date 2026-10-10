# -*- coding: utf-8 -*-
"""worker_instance_id 执行链路传播（UC-1001 / INT-69）。

任务归属实例（task_service worker）通过 gRPC metadata 把 worker_instance_id
传给执行服务（api_test_service / e2e_test_service），执行服务发布事件时
携带该字段，实现「调度归属 → 执行 → 事件 payload」全链路贯通：

- task_service 侧：任务工作线程入口 set_worker_instance_id(engine.instance_id)，
  出站 gRPC 拦截器（client_worker_context_interceptor）自动附加 metadata；
- 执行服务侧：servicer 入口用 worker_instance_id_from_context(context) 读取，
  线程池执行路径用 copy_context() 传播（见 api_test_service servicer），
  事件发布点用 get_worker_instance_id() 写入 payload。
"""
import contextvars

# gRPC metadata key（ASCII 小写，符合 HTTP/2 header 规范）
WORKER_INSTANCE_ID_METADATA_KEY = 'worker-instance-id'

_worker_instance_id: contextvars.ContextVar = contextvars.ContextVar(
    'worker_instance_id', default=None)


def set_worker_instance_id(instance_id) -> None:
    """在当前执行上下文设置 worker_instance_id（None 表示清除）"""
    _worker_instance_id.set(str(instance_id) if instance_id else None)


def get_worker_instance_id():
    """读取当前上下文的 worker_instance_id（未设置返回 None）"""
    return _worker_instance_id.get()


def worker_instance_id_metadata():
    """构造出站 gRPC metadata 列表片段（未设置时返回空列表）"""
    value = _worker_instance_id.get()
    if value:
        return [(WORKER_INSTANCE_ID_METADATA_KEY, value)]
    return []


def worker_instance_id_from_context(context):
    """服务端从 grpc ServicerContext 读取入站 worker_instance_id metadata"""
    if context is None:
        return None
    try:
        for key, value in (context.invocation_metadata() or ()):
            if key == WORKER_INSTANCE_ID_METADATA_KEY:
                return value
    except Exception:
        pass
    return None
