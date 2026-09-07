/**
 * Stats (Home dashboard) API module
 * 出口契约：Domain（camelCase）；DTO 转换收敛在 statsAdapter。
 */
import { request, type RequestOptions } from '../http/client';
import { toHomeStatsDetails, toHomeStatsSummary } from '../adapters/statsAdapter';
import type { HomeStatsDetailsDto, HomeStatsSummaryDto } from '../dto/statsDto';
import type { HomeStatsDetails, HomeStatsSummary } from '../../domain/model/stats';

export const statsApi = {
  /** 首页统计详情（后端字段 snake_case：test_cases/audio_files/with_endpoints 等） */
  async getStatsDetails(options: RequestOptions = {}): Promise<HomeStatsDetails> {
    const dto = await request<HomeStatsDetailsDto>('GET', '/home/stats/details', null, options);
    return toHomeStatsDetails(dto);
  },

  /** 首页统计摘要（最近任务/分组排行/设备状态） */
  async getStatsSummary(options: RequestOptions = {}): Promise<HomeStatsSummary> {
    const dto = await request<HomeStatsSummaryDto>('GET', '/home/stats/summary', null, options);
    return toHomeStatsSummary(dto);
  }
};
