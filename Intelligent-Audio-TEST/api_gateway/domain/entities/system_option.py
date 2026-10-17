# -*- coding: utf-8 -*-
"""系统选项领域实体与默认基线（INT-620）。

对位 newAPI `/api/option/` KV 通道：键 = `域.分区.字段`，值类型与
前端 `frontend-react/src/domain/models/option.ts` 的 SystemOptionValue
（string / number / boolean / string[]）对齐。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Union

# 选项值类型（与前端 domain 模型 SystemOptionValue 一致；拒绝魔法类型）
SystemOptionValue = Union[str, int, float, bool, List[str]]

# 系统选项默认基线（= 前端 settings-mock MOCK_SYSTEM_OPTIONS 的当前可视稿基线：
# SYSTEM_OPTION_DEFAULTS ∪ 站点信息四项覆写）。库中未落键回退默认，显式写入
# 空值覆盖默认——与前端 use-system-options 按默认值类型安全解析的口径一致。
SYSTEM_OPTION_DEFAULTS: Dict[str, SystemOptionValue] = {
    # 站点设置 · 站点信息
    'site.name': '智能语音测试平台',
    'site.logo': '',
    'site.footer': '© 2026 智能语音测试平台',
    # 站点设置 · 站点公告
    'site.notice': '',
    # 站点设置 · 导航模块
    'site.navigation.show_breadcrumb': True,
    'site.navigation.show_algorithm_switcher': True,
    # 认证设置 · 认证方式
    'auth.password_login': True,
    'auth.registration': True,
    'auth.email_verification': False,
    # 安全设置 · 访问控制
    'security.rate_limit': True,
    # 运维设置 · 日志维护
    'operations.log_retention_days': 30,
}


@dataclass
class SystemOption:
    """系统选项实体（KV 记录）。"""

    key: str
    value: SystemOptionValue
    updated_at: Optional[datetime] = None
