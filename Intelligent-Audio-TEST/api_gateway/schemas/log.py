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


class LogListData(PaginatedData[LogItem]):
    pass


class LogRefreshData(APIModel):
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
