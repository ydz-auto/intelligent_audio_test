# -*- coding: utf-8 -*-
"""task_service 时间口径契约（INT-2209）。

**写库口径：UTC naive。** test_tasks / task_case_relations 的
created_at / updated_at / started_at / completed_at 等时间列一律写入无时区
（tzinfo is None）的 datetime，其值就是 UTC 墙钟——与 created_at 的落库
结果同口径；东八区等本地时区只在展示层（前端 / 进度 payload 的 ts_ms）
转换。

为什么必须如此（INT-2209 缺陷根因）：
- DB session 的 TimeZone 为 UTC。把 aware datetime（如
  ``datetime.now(utc_plus_8)``）写进 ``timestamp without time zone`` 列时，
  PostgreSQL 会按会话时区再转换一次——值本身没错，但列里已不带时区信息；
- 读回的是 naive 值（UTC）。若再 ``.replace(tzinfo=utc_plus_8)`` 当作东方
  时间用，并**写回 ORM 属性**，提交时又会被按 UTC 转换一次：每往返一次
  偏移 -8h。历史数据里的 -16h / -8h 就是这样一次次叠出来的，
  表现为 ``started_at < created_at``、``actual_duration`` 虚高。

使用约定：
- 写库取当前时间一律 ``utcnow()``（PO 默认值也用它，见
  ``shared.models.database.utcnow``）；**不要**再传
  ``datetime.now(utc_plus_8)`` 这类 aware 值；
- 外部传来（gRPC / ISO8601 字符串 / 其他服务）的值落库前一律过
  ``to_utc_naive()``；
- 计算时长用 ``elapsed_seconds()``，两侧同为 naive，不需要补时区；
- 服务端自己拼展示串、或按"本地自然日"分桶时用 ``to_local_naive()``；
- 用户输入的本地墙钟（日期筛选参数）进 SQL 前用
  ``local_naive_to_utc_naive()``；
- 永远不要为了"对齐时区"把 naive 值 ``replace(tzinfo=...)`` 后写回 ORM
  属性（那会改掉库里已有的值）。

补充（INT-2283）：部署库的会话时区是 **Asia/Shanghai**（不是 UTC），所以
aware +8 写进 ``timestamp without time zone`` 列会落成 +8 墙钟，与
``utcnow()`` 写出的 UTC 墙钟差 8 小时——这正是「创建时间比开始时间晚 8
小时」的成因。写库侧因此只能是 naive UTC，任何本地语义都在读写边界转换。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

# 展示层时区：东八区（部署环境的本地时区）
_LOCAL_OFFSET = timedelta(hours=8)

# 实现只在 shared 一处（PO 默认值也取同一个），本模块是 task_service 的口径门面
from shared.utils.time_utils import utcnow as _shared_utcnow


def utcnow() -> datetime:
    """当前 UTC naive datetime —— 写库唯一口径。"""
    return _shared_utcnow()


def to_utc_naive(value) -> Optional[datetime]:
    """datetime / ISO8601 字符串 → UTC naive；None / 空串 / 无法解析 → None。

    已带时区的值按绝对时刻换算到 UTC 后去掉 tzinfo；naive 值视为**已是
    UTC**（库内口径），原样返回，绝不"猜"成本地时间再平移。
    """
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def elapsed_seconds(started_at, completed_at) -> Optional[int]:
    """结束时间 - 开始时间（秒，整数）；任一为空 → None。

    两侧统一归一到 UTC naive 后相减，与展示时区无关。
    """
    start = to_utc_naive(started_at)
    end = to_utc_naive(completed_at)
    if start is None or end is None:
        return None
    return int((end - start).total_seconds())


def to_local_naive(value) -> Optional[datetime]:
    """库内 UTC naive → 东八区 naive（展示 / 本地日历分桶用）。

    仅用于「服务端自己拼展示串」和「按本地自然日分桶」；实体字段落库仍是
    UTC naive，不要把本函数的返回值写回 ORM 属性。
    """
    utc_dt = to_utc_naive(value)
    if utc_dt is None:
        return None
    return utc_dt + _LOCAL_OFFSET


def local_naive_to_utc_naive(value) -> Optional[datetime]:
    """用户输入的本地墙钟（查询参数 / 日期筛选）→ 库内 UTC naive。

    用户点的是「本地 2026-10-31 00:00」，而列里存的是 UTC；直接拿来比会整体
    偏 8 小时（INT-2283）。带时区的输入按绝对时刻换算；naive 输入按东八区
    墙钟解释。
    """
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt - _LOCAL_OFFSET
