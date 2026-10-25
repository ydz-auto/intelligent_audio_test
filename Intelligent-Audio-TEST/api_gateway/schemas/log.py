from typing import List, Optional
from pydantic import Field

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class LogItem(APIModel):
    id: int
    time: str
    level: str
    category: str
    module: str
    source: str
    content: str
    mark: Optional[str] = None
    device_id: Optional[int] = None
    task_id: Optional[int] = None
    api_id: Optional[int] = None
    test_case_id: Optional[str] = None
    thread_id: Optional[str] = None
    algorithm_type: Optional[str] = None
    # INT-838：读侧响应补带操作人 user_id（DB 行 created_by_user_id / 业务文件条目 user_id）
    user_id: Optional[int] = None


class LogListData(PaginatedData[LogItem]):
    pass


class LogRefreshData(APIModel):
    """增量刷新响应（字段名与两前端契约不变，INT-1812 契约 §Q4）。

    - `last_id`：请求下发的增量基准。审计文件条目 `id` = cursor（事件时间
      epoch 微秒），legacy logs 表自增 id 用 CURSOR_FLOOR(10^12) 隔开。
    - `db_max_id`：保留原字段名，语义为 `server_max_cursor`（审计语料最大
      游标，无数据 0）——不再是 logs 表 max(id)。
    - `reset_required`：**可选**字段（仅在越界时出现在响应里，故不声明为模型
      成员、由服务层按需补进 dict）；React 已有分支清缓冲重建基准，Vue 不读。
    """
    items: List[LogItem]
    count: int
    new_count: int
    last_id: int


class LogStatsData(APIModel):
    total: int = 0
    debug: int = 0
    info: int = 0
    warning: int = 0
    error: int = 0
    critical: int = 0


class LogRefreshRequest(APIModel):
    last_id: int = 0


class LogMarkRequest(APIModel):
    log_ids: List[int]
    mark: str = "flagged"


class LogClearRequest(APIModel):
    before_datetime: Optional[str] = None
    keep_marked: bool = True


class LogExportRequest(APIModel):
    log_ids: Optional[List[int]] = None
    format: str = "excel"
    # INT-274：导出条件从 POST body 读取（doc/接口文档 6. 导出日志），
    # level/module 与 query（LogExportQuery，GET 兼容）可任一侧传入。
    level: Optional[str] = None
    module: Optional[str] = None


class LogArchiveRequest(APIModel):
    days: int = Field(default=7, description="保留最近N天的热数据")
    dry_run: bool = Field(default=False, description="仅统计，不执行归档")


class LogArchiveStatus(APIModel):
    total_logs: int
    hot_logs: int
    cold_logs: int
    archive_files: List[str]
    archive_dir: str


class LogArchiveResult(APIModel):
    archived_count: int
    deleted_count: int
    archive_file: Optional[str] = None
    remaining_count: int


class LogListQuery(APIModel):
    page: int = Field(1)
    per_page: int = Field(50)
    level: Optional[str] = Field(None)
    module: Optional[str] = Field(None)
    category: Optional[str] = Field(None)
    keyword: Optional[str] = Field(None)
    content_include: Optional[str] = Field(None)
    content_exclude: Optional[str] = Field(None)
    start_time: Optional[str] = Field(None)
    end_time: Optional[str] = Field(None)
    mark: Optional[str] = Field(None)
    device_id: Optional[int] = Field(None)
    task_id: Optional[int] = Field(None)
    api_id: Optional[int] = Field(None)
    test_case_id: Optional[str] = Field(None)
    thread_id: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    # INT-806：按操作人过滤（「仅自己」视图范围；user_id 与当前认证用户不一致 → 403）
    user_id: Optional[int] = Field(None)
    # INT-81：业务日志按轮次/评估ID检索（对应文件路径第三段）
    evaluation_id: Optional[str] = Field(None)
    round: Optional[str] = Field(None)


class LogStatsQuery(APIModel):
    start_time: Optional[str] = Field(None)
    end_time: Optional[str] = Field(None)
    level: Optional[str] = Field(None)
    module: Optional[str] = Field(None)
    category: Optional[str] = Field(None)
    keyword: Optional[str] = Field(None)
    mark: Optional[str] = Field(None)
    device_id: Optional[int] = Field(None)
    task_id: Optional[int] = Field(None)
    content_include: Optional[str] = Field(None)
    content_exclude: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    # INT-806：统计口径同步「仅自己」（user_id 与当前认证用户不一致 → 403）
    user_id: Optional[int] = Field(None)
    # INT-81：任务维度统计覆盖业务日志文件
    evaluation_id: Optional[str] = Field(None)
    round: Optional[str] = Field(None)


class LogArchiveQuery(APIModel):
    task_id: Optional[int] = Field(None)
    test_case_id: Optional[str] = Field(None)
    # INT-786：全局归档清单分页（照 LogListQuery 惯例，仅无筛选模式生效）
    page: int = Field(1)
    per_page: int = Field(50)


class LogExportQuery(APIModel):
    level: Optional[str] = Field(None)
    module: Optional[str] = Field(None)

