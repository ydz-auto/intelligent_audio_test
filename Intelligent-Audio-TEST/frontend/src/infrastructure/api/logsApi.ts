/**
 * Logs API module
 * 出口契约：Domain（camelCase）；DTO 转换全部收敛在 adapters。
 * 查询参数/请求体显式 snake_case（per_page/content_include/start_time/log_ids 等）。
 */
import type { Log, LogQuery, LogStatsData, LogRefreshResult, LogExportQuery, LogClearInput } from '../../domain/model/log';
import { request, type RequestOptions } from '../http/client';
import { toPaginated } from '../adapters/commonAdapter';
import {
  toLog,
  toLogStatsData,
  toLogRefreshResult,
  toLogQueryDto,
  toLogExportQueryDto,
  toLogMarkDto,
  toLogClearDto,
  toLogRefreshRequestDto,
} from '../adapters/logAdapter';
import type { LogListDto, LogStatsDto, LogRefreshDto, LogMarkDto } from '../dto/logDto';

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
  }
};

export type { Log };
