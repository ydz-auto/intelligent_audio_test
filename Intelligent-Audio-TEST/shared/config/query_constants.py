"""查询常量 — 集中管理分页大小，消除 per_page/limit 魔法数字"""


class QueryConstants:
    """查询分页常量"""
    # 无限制查询（用于内部全量获取，非用户分页）
    UNLIMITED_PAGE_SIZE = 99999
    # 大批量查询（用于导出等场景）
    EXPORT_PAGE_SIZE = 10000
    # 默认批量大小
    DEFAULT_BATCH_SIZE = 1000
    # 默认分页大小
    DEFAULT_PAGE_SIZE = 20
