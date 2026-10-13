// -*- coding: utf-8 -*-
/**
 * 认证域常量（INT-285）：注册口径配置化，拒绝视图内魔法数字。
 * passwordMinLength 与后端网关 AUTH_PASSWORD_MIN_LENGTH（默认 6）
 * 保持一致（成员裁定 INT-285：密码最短 6 位）。
 */
export const AUTH_PASSWORD_MIN_LENGTH = 6
