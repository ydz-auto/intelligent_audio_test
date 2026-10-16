"""
操作人解析工具 (Operator Resolution Utility)

职责：集中解析「当前操作人用户ID」，供软删审计（backend/models/soft_delete.py）等
需要记录操作人的共享基础设施调用。

解析优先级：
1. `flask.g.operator_user_id` —— 认证层（G 域 RBAC）落地后由中间件注入；
2. 请求头 `X-User-Id` —— **仅过渡期（`AUTH_ENABLED=false`）接受**，认证落地即失效；
3. 都取不到 → 返回 None。

⚠️ 第 2 条是**过渡期专用**：`AUTH_ENABLED=true` 后本模块不再读该请求头，否则任何客户端
都能自带 `X-User-Id` 伪造审计操作人——被污染的审计字段比 NULL 更坏，与「无身份来源时
不伪造操作人」的口径相悖。认证落地后操作人只认认证中间件注入的 `flask.g.operator_user_id`。

V9.7.10 现状：无认证体系（`AUTH_ENABLED=false`、`users` 表为空、前端不携带任何身份），
因此实际解析结果为 None。此处**不伪造操作人**（不写系统哨兵、不猜用户），
审计字段按「操作人未知」留 NULL；认证体系落地后无需改动调用方即自动生效。
"""
from flask import current_app, g, request

OPERATOR_HEADER = 'X-User-Id'


def _auth_enabled():
    """认证体系是否已落地（AUTH_ENABLED=true）。无应用上下文时按未落地处理。"""
    try:
        return bool(current_app.config.get('AUTH_ENABLED', False))
    except Exception:
        return False


def _from_context():
    try:
        if not current_app:
            return None
    except Exception:
        # 无应用上下文（离线脚本 / 后台线程）
        return None

    try:
        value = getattr(g, 'operator_user_id', None)
    except Exception:
        value = None
    if value is not None:
        return value

    # 过渡期专用：认证落地后不再信任客户端自带的请求头
    if _auth_enabled():
        return None

    try:
        return request.headers.get(OPERATOR_HEADER)
    except Exception:
        # 无请求上下文（后台线程 / 调度器）
        return None


def current_operator_user_id():
    """返回当前操作人用户ID（int），解析不到返回 None。"""
    raw = _from_context()
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
