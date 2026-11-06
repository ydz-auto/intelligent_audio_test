# -*- coding: utf-8 -*-
"""实验室名称解析器 — device_service 只读 join 用途（实验室扩展 INT-493 §4.2）。

`laboratories` 表由实验室域（INT-493 拆分① api_gateway）维护，device_service 仅按
`lab_id` 取 `name` 透出 DTO（同共享库，避免网关二次 RPC）。为避免跨服务重复注册
同名 PO（同名 `__tablename__` 在同一 `Base.metadata` 下二次定义会抛
InvalidRequestError），这里以轻量 `text()` SQL 直查共享库表，不做 ORM 映射。
"""
import logging

from sqlalchemy import text

from shared.models.database import get_db_session

logger = logging.getLogger(__name__)


def resolve_lab_names(lab_ids) -> dict:
    """批量解析实验室名称，返回 {lab_id: lab_name} 映射（软删实验室视为未绑定）。

    - lab_ids 为空 → 返回 {}（无 join 语义）
    - 实验室表不可用（迁移未落地/表缺失）→ 返回 {}，lab_name 一律 null，
      前端按「未绑定」渲染（对齐 DTO 可选字段容错口径，INT-493 §4.2）
    - 软删（deleted=TRUE）实验室不返回，关联设备 lab_name 为 null
    """
    if not lab_ids:
        return {}
    ids = list(dict.fromkeys(lab_ids))  # 去重
    placeholders = ', '.join(f':lab_id_{i}' for i in range(len(ids)))
    params = {f'lab_id_{i}': v for i, v in enumerate(ids)}
    session = get_db_session()
    try:
        rows = session.execute(
            text(
                "SELECT id, name FROM laboratories "
                f"WHERE id IN ({placeholders}) AND deleted = FALSE"
            ),
            params,
        ).fetchall()
    except Exception:
        # 实验室表尚未就绪时降级为空映射：lab_name 为可选字段，不阻塞设备列表
        logger.debug("laboratories 表不可用，lab_name 降级为 null", exc_info=True)
        return {}
    return {row[0]: row[1] for row in rows}
