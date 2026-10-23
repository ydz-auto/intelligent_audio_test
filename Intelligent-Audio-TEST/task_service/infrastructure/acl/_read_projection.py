# -*- coding: utf-8 -*-
"""跨域只读投影（共享库窄字段 IN 查询）— INT-1625（同 agent/a/int-1500@479763142 口径）。

背景（2026-10-23 真实库实测，INT-1500）：任务列表 / 挑选候选等热读路径的装饰字段
（报告摘要、设备/API 名称与状态、音频时长、已评估标记）逐行或逐 ID 走 gRPC
时退化为 N+1——单个候选页 199 个用例的音频时长经 `GetAudiosByIds` 实测
27.9s（audio_service 内部逐音频查标签 + 标注），任务列表 10 行约 30 次下游
调用。全部服务共用同一 Postgres 库，窄字段一次性 IN 查询可取回同样的口径。
INT-1625 复测候选 under per_page=200：`GetDimensionResultsByResultIds` 为拿
「是否已评估」一个布尔集合回传 5592 行维度（宿主实测 5~22s），是 60s 超时的
主因之一。

口径纪律：每个投影都按对应 gRPC 实现的过滤条件逐条对齐（软删 `deleted =
FALSE`、报告可见性 `visible_condition` 同义），只读、只取窄字段，不承担任何
写语义；字段增减必须与源服务契约同步。

先例：`task_read_model._fetch_labs_map` 读 `laboratories` 共享库表
（INT-537/INT-538），避免网关二次 RPC。

失败一律返回空结果（仅日志告警）。失败语句会把 PostgreSQL 事务置为 aborted，
因此投影在 SAVEPOINT 内执行，失败只回滚该保存点——不破坏调用方会话里已加载
的 ORM 对象（普通 rollback 会过期全部实例，后续 `task.id` 访问抛
DetachedInstanceError）与后续查询（同 INT-339 的降级教训）。
"""
import logging

from sqlalchemy import bindparam, text

_logger = logging.getLogger(__name__)


def fetch_rows(session, sql: str, ids, ids_name: str = 'ids', extra_params=None) -> list:
    """执行一次「列表参数 IN」只读查询，失败降级为空结果。

    Args:
        session: SQLAlchemy session（跨域只读投影沿用调用方 session，不自行关闭）
        sql: SQL 文本，列表占位符写作 `:ids`（或 ids_name 指定）
        ids: IN 列表取值
        ids_name: 列表参数名
        extra_params: 其它标量参数

    Returns:
        Row 列表；参数为空或查询失败返回 []。
    """
    ids = list(ids or [])
    if not ids:
        return []
    savepoint = None
    try:
        stmt = text(sql).bindparams(bindparam(ids_name, expanding=True))
        params = dict(extra_params or {})
        params[ids_name] = ids
        savepoint = session.begin_nested()
        rows = session.execute(stmt, params).fetchall()
        savepoint.commit()
        return rows
    except Exception as e:
        try:
            if savepoint is not None:
                savepoint.rollback()
        except Exception:
            pass
        _logger.warning("共享库只读投影降级（表可能未建）: %s", e)
        return []
