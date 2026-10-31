"""时间戳转换公共工具。

项目内所有"毫秒级 Unix 时间戳 -> 东八区(UTC+8)可读字符串"的转换统一走这里，
避免每个模块各自重复 `datetime.now(timezone(timedelta(hours=8)))` 这段代码。
"""
from datetime import datetime, timezone, timedelta

# 东八区时区对象（UTC+8 / Asia/Shanghai）
UTC8 = timezone(timedelta(hours=8))


def utcnow() -> datetime:
    """当前 UTC naive（tzinfo=None，值为 UTC 墙钟）—— 写库统一口径（INT-2283）。

    库内 ``timestamp without time zone`` 列统一存 UTC naive，本地时区只在
    展示层转换（前端 ``parseApiDateTime`` 把无时区后缀的串按 UTC 解析后转
    本地）。执行链路（test_tasks / task_case_relations / test_results /
    test_result_dimensions 等）的 created_at / updated_at / started_at /
    completed_at 一律取这里，避免同一张表混两种口径。

    不要用 :func:`now_utc8`（aware +8）写库：部署库会话时区是
    Asia/Shanghai，aware 值会被再转一次落成 +8 墙钟，与 UTC 值差 8 小时。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

# 默认格式：精确到秒
DEFAULT_FMT = '%Y-%m-%d %H:%M:%S'
# 毫秒格式：精确到毫秒（strftime 的 %f 是 6 位微秒，这里在格式化后再截断到 3 位）
MS_FMT = '%Y-%m-%d %H:%M:%S.%f'


def now_utc8() -> datetime:
    """返回当前东八区时间（带时区信息）。"""
    return datetime.now(UTC8)


def now_utc8_str(fmt: str = DEFAULT_FMT) -> str:
    """返回当前东八区时间的字符串。"""
    return now_utc8().strftime(fmt)


def ms_to_utc8_str(ms, fmt: str = DEFAULT_FMT) -> str:
    """Unix 毫秒时间戳 -> 东八区字符串。

    Args:
        ms: 毫秒级时间戳（int/float/None）
        fmt: strftime 格式，默认 '%Y-%m-%d %H:%M:%S'
            若使用 MS_FMT（含 %f），会自动把微秒截断到 3 位毫秒。

    Returns:
        形如 '2026-07-18 16:00:00' 的字符串；ms 为 None 或非法时返回 'N/A'。
    """
    if ms is None:
        return 'N/A'
    try:
        out = datetime.fromtimestamp(ms / 1000, tz=UTC8).strftime(fmt)
        # %f 是 6 位微秒，毫秒场景下截断到 3 位
        if fmt == MS_FMT and '.' in out:
            head, _, frac = out.rpartition('.')
            return f"{head}.{frac[:3]}"
        return out
    except (TypeError, ValueError, OverflowError, OSError):
        return 'N/A'


def ms_to_utc8_dt(ms) -> datetime:
    """Unix 毫秒时间戳 -> 东八区 datetime 对象（带时区）。

    ms 为 None 或非法时返回 None。
    """
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=UTC8)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def s_to_utc8_str(s, fmt: str = DEFAULT_FMT) -> str:
    """Unix 秒级时间戳 -> 东八区字符串。"""
    if s is None:
        return 'N/A'
    try:
        return datetime.fromtimestamp(s, tz=UTC8).strftime(fmt)
    except (TypeError, ValueError, OverflowError, OSError):
        return 'N/A'
