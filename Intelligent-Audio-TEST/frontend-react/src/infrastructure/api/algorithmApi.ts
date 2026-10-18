/**
 * 全局算法选项真实 API（infrastructure/api 层；接线·壳 INT-607）。
 * GET /api/v1/algorithm/options（algorithm:read 门槛）——导航栏全局算法
 * 切换器数据源（02_导航栏.md §3.4）：仅在线算法；选项 type 码即全局过滤值
 * （业务列表 algorithm_type 参数同源，tasks/用例/音频/设备/报告/日志消费）。
 */
import type { AlgorithmOption } from '@/domain/models/algorithm'
import { request } from '@/infrastructure/api/client'
import {
  toAlgorithmOption,
  type AlgorithmOptionsResultDto,
} from '@/infrastructure/dto/algorithm.dto'

export async function fetchAlgorithmOptions(): Promise<AlgorithmOption[]> {
  const dto = await request<AlgorithmOptionsResultDto>(
    'GET',
    '/algorithm/options'
  )
  return (dto?.algorithms ?? []).map(toAlgorithmOption)
}

/** 算法参考参数选项（音频上传/文件夹导入「标注代码」select；GET /algorithm/reference-params） */
export interface ReferenceParamOption {
  value: string
  label: string
}

export async function fetchReferenceParams(
  algorithmType?: string
): Promise<ReferenceParamOption[]> {
  const dto = await request<{
    items?: Array<{ code?: string | null; name?: string | null }>
  }>(
    'GET',
    '/algorithm/reference-params',
    null,
    algorithmType ? { params: { algorithm_type: algorithmType } } : undefined
  )
  return (dto?.items ?? [])
    .filter((p) => p.code)
    .map((p) => ({
      value: p.code as string,
      label: p.name ? `${p.code} - ${p.name}` : (p.code as string),
    }))
}
