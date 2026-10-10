# -*- coding: utf-8 -*-
"""领域服务：无状态校验纯函数。

适配器选择已由 adapters.factory.APIAdapterFactory 注册表承担
（UC-1003），原 AdapterSelector if 链随之移除。
"""

# 追加 re-export：会话状态校验等无状态纯函数
from api_adapter_service.domain.services.session_service import (  # noqa: F401
    can_send_message,
    validate_session_status,
)
