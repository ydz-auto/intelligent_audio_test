# -*- coding: utf-8 -*-
"""SSE 配置边界（A2 / INT-1790）— 写侧校验与执行侧限幅共用一组口径。

写侧（`application/api_crud_service.py`）按这些上限拒绝非法配置；执行侧
（`infrastructure/adapters/transport/sse_client.py`）对**线缆里来的值**再做一次
限幅：配置可能是旧数据 / 直接 SQL 写入而绕过校验，而服务端 `retry:` 字段
本身完全不可控（A2 返工 P3-2）。两处引用同一常量，避免各写一份魔法数字。
"""

# 毫秒字段上限：1 小时（idle_timeout_ms / max_duration_ms）
SSE_MAX_MS = 3600000
# 重连退避上限 60s：写侧 `retry_ms` 值域与线缆 `retry:` 限幅共用
SSE_MAX_RETRY_MS = 60000
# 重连次数上限
SSE_MAX_RECONNECT_ATTEMPTS = 10
