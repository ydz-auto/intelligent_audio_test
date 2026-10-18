/**
 * 算法选项 API（infrastructure/api 层，接线壳 INT-607）。
 * 真实端点：GET /api/v1/algorithm/options（algorithm:read，algorithm_bp.py:165-167；
 * gRPC GetAlgorithmOptions 仅返回在线算法）。供全局算法切换器/算法卡片网格共用
 * 数据源；snake→camel 转换收敛在 infrastructure/dto/algorithm.dto.ts。
 */
import { apiClient } from './client'
import type { AlgorithmSwitchOption } from '@/domain/models/algorithm'
import {
  toAlgorithmOption,
  type AlgorithmOptionsResultDto,
} from '@/infrastructure/dto/algorithm.dto'

/** 算法选项（下拉框；value=算法类型码，与 useAlgorithmStore.algorithmId 同源） */
export async function fetchAlgorithmOptions(): Promise<AlgorithmSwitchOption[]> {
  const dto = await apiClient.get<AlgorithmOptionsResultDto>('/algorithm/options')
  return (dto?.algorithms ?? []).map(toAlgorithmOption)
}
