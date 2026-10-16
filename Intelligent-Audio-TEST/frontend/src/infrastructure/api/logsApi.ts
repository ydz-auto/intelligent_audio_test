/**
 * Logs API module
 * 出口契约：Domain（camelCase）；DTO 转换全部收敛在 adapters。
 * 查询参数/请求体显式 snake_case（per_page/content_include/start_time/log_ids 等）。
 */
import type {
  Log,
  LogQuery,
  LogStatsData,
  LogRefreshResult,
  LogExportQuery,
  LogClearInput,
  LogArchiveStatus,
  LogArchiveResult,
  LogArchiveList,
  LogArchiveQuery,
  LogArchiveInput,
} from '../../domain/model/log';
import { request, type RequestOptions } from '../http/client';
import { toPaginated } from '../adapters/commonAdapter';
import {
  toLog,
  toLogStatsData,
  toLogRefreshResult,
  toLogArchiveStatus,
  toLogArchiveList,
  toLogArchiveResult,
  toLogQueryDto,
  toLogExportQueryDto,
  toLogArchiveQueryDto,
  toLogArchiveRequestDto,
  toLogMarkDto,
  toLogClearDto,
  toLogRefreshRequestDto,
} from '../adapters/logAdapter';
import type {
  LogListDto,
  LogStatsDto,
  LogRefreshDto,
  LogMarkDto,
  LogArchiveStatusDto,
  LogArchiveListDto,
  LogArchiveResultDto,
} from '../dto/logDto';

/** 标记入参（与后端 LogMarkRequest 的 mark 默认值一致） */
const DEFAULT_MARK = 'flagged';

export const logsApi = {
  /** 日志分页列表 → Paginated<Log>（camelCase） */
  async getAll(params: LogQuery = {}, options: RequestOptions = {}) {
    const dto = await request<LogListDto>('GET', '/logs', null, {
      ...options,
      params: toLogQueryDto(params),
    });
    return toPaginated(dto, toLog);
  },

  /** 日志统计（按级别细分：total/debug/info/warning/error/critical） */
  async getStats(params: LogQuery = {}, options: RequestOptions = {}): Promise<LogStatsData> {
    const dto = await request<LogStatsDto>('GET', '/logs/stats', null, {
      ...options,
      params: toLogQueryDto(params),
    });
    return toLogStatsData(dto);
  },

  /** 标记日志（请求体 log_ids + mark） */
  async mark(logIds: (string | number)[], mark: string = DEFAULT_MARK) {
    const input = { logIds, mark };
    return request('PUT', '/logs/mark', toLogMarkDto(input, DEFAULT_MARK) satisfies LogMarkDto);
  },

  /** 导出日志（GET /logs/export：条件查询 + format） */
  async export(params: LogExportQuery = {}, options: RequestOptions = {}) {
    return request('GET', '/logs/export', null, { ...options, params: toLogExportQueryDto(params) });
  },

  /** 清除日志（POST /logs/clear：before_datetime + keep_marked） */
  async clear(params: LogClearInput = {}, options: RequestOptions = {}) {
    return request('POST', '/logs/clear', toLogClearDto(params), options);
  },

  /** 刷新日志（POST /logs/refresh：last_id 增量拉取） */
  async refresh(lastId: string | number = 0, options: RequestOptions = {}): Promise<LogRefreshResult> {
    const dto = await request<LogRefreshDto>('POST', '/logs/refresh', toLogRefreshRequestDto(lastId), options);
    return toLogRefreshResult(dto);
  },

  // ===== 日志归档管理面（INT-548，对接后端 5 端点） =====

  /** 归档状态（GET /logs/archive/status） */
  async getArchiveStatus(options: RequestOptions = {}): Promise<LogArchiveStatus> {
    const dto = await request<LogArchiveStatusDto>('GET', '/logs/archive/status', null, options);
    return toLogArchiveStatus(dto);
  },

  /** 触发归档（POST /logs/archive：days 保留最近 N 天热数据；dry_run 仅预览） */
  async archive(input: LogArchiveInput = {}, options: RequestOptions = {}): Promise<LogArchiveResult> {
    const dto = await request<LogArchiveResultDto>('POST', '/logs/archive', toLogArchiveRequestDto(input), options);
    return toLogArchiveResult(dto);
  },

  /** 已归档日志列表（GET /logs/archive/logs：需 task_id 或 test_case_id） */
  async getArchivedLogs(query: LogArchiveQuery = {}, options: RequestOptions = {}): Promise<LogArchiveList> {
    const dto = await request<LogArchiveListDto>('GET', '/logs/archive/logs', null, {
      ...options,
      params: toLogArchiveQueryDto(query),
    });
    return toLogArchiveList(dto);
  },

  /** 下载归档文件（GET /logs/archive/{filename}：后端返回 JSON 文件流） */
  async downloadArchive(filename: string, options: RequestOptions = {}): Promise<Blob> {
    const data = await request<Blob>('GET', `/logs/archive/${encodeURIComponent(filename)}`, null, {
      ...options,
      responseType: 'blob',
    });
    return data instanceof Blob ? data : new Blob([data as unknown as BlobPart]);
  },

  /** 删除归档文件（DELETE /logs/archive/{filename}） */
  async deleteArchive(filename: string, options: RequestOptions = {}): Promise<void> {
    await request('DELETE', `/logs/archive/${encodeURIComponent(filename)}`, null, options);
  },
};

export type { Log };
