/**
 * 评估维度页 query hooks（application 层；11_用例域.md §9 组件树落位）。
 * queryKey：['evaluation','dimensions'] / ['evaluation','categories'] / ['algorithm','options']。
 * 维度增删/权重/启停后 invalidate(['evaluation'])——与用例管理「评估维度」facet
 * （['evaluation','dimensions','options']）同前缀联动刷新（§4.3 三页口径）。
 */
import { useMemo } from 'react'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'
import {
  batchEvaluationDimensions,
  calculateDimensionScore,
  deleteEvaluationCategory,
  deleteEvaluationDimension,
  duplicateDimension,
  exportEvaluationDimensions,
  fetchAlgorithmOptions,
  fetchDimensionAudioFlags,
  fetchDimensionOptions,
  fetchEvaluationCategories,
  fetchEvaluationDimensionDetail,
  fetchEvaluationDimensions,
  importEvaluationDimensions,
  reorderDimension,
  saveEvaluationCategory,
  saveEvaluationDimension,
  testDimensionHealth,
  updateDimensionStatus,
  updateDimensionWeight,
} from '@/infrastructure/api/evaluation-api'

/**
 * 把「是否需要音频」标记表按 id 合并进维度列表（INT-1843）。
 * 标记表取不到（options 端点失败）时原样返回列表——音乐图标退化，不影响选择与保存。
 */
export function mergeDimensionRequiresAudio(
  dimensions: Dimension[],
  flags: Map<number, boolean> | undefined
): Dimension[] {
  if (!flags) return dimensions
  return dimensions.map((d) => ({
    ...d,
    requiresAudio: flags.get(Number(d.id)) ?? d.requiresAudio ?? false,
  }))
}

/**
 * 评估维度全量（列表/分组双视图共用；主/子同屏聚合）。
 * INT-1843：`requires_audio` 只有 options 端点下发、列表端点没有，这里按 id 合并成
 * Dimension.requiresAudio（维度云音乐图标的数据源）。
 */
export function useEvaluationDimensions() {
  const listQuery = useQuery({
    queryKey: ['evaluation', 'dimensions'],
    queryFn: fetchEvaluationDimensions,
    staleTime: 30_000,
  })
  const audioFlagsQuery = useQuery({
    queryKey: ['evaluation', 'dimensions', 'audio-flags'],
    queryFn: fetchDimensionAudioFlags,
    staleTime: 5 * 60_000,
  })
  const data = useMemo(
    () =>
      listQuery.data
        ? mergeDimensionRequiresAudio(listQuery.data, audioFlagsQuery.data)
        : listQuery.data,
    [listQuery.data, audioFlagsQuery.data]
  )
  return { ...listQuery, data }
}

/**
 * 维度选项（GET /evaluation/dimensions/options?algorithm_type=…；服务端按算法收敛）。
 * queryKey ['evaluation','dimensions','options', algorithmType]；维度增删改经
 * invalidateQueries(['evaluation']) 同前缀刷新。
 */
export function useDimensionOptions(
  algorithmType?: string | null,
  enabled = true
) {
  return useQuery({
    queryKey: ['evaluation', 'dimensions', 'options', algorithmType ?? 'all'],
    queryFn: () => fetchDimensionOptions(algorithmType ?? undefined),
    staleTime: 30_000,
    enabled,
  })
}

/**
 * 用例维度云专用：直接以 options 端点作为唯一维度数据源。
 * 该端点按 algorithmType 服务端过滤，并下发 parent_dimension_id / category_id，
 * 主/子层级与分类组头不再依赖列表端点（列表端点不下发 associated_algorithms，
 * 客户端二次过滤会恒空）。
 */
export function useAlgorithmDimensions(algorithmType?: string | null) {
  const query = useDimensionOptions(algorithmType ?? null)
  return { ...query, data: query.data ?? [] }
}

/** 维度详情（编辑反填用；列表不下发 required_inputs/output_fields，编辑必须走详情） */
export function useEvaluationDimensionDetail(id: number | string | null) {
  return useQuery({
    queryKey: ['evaluation', 'dimensions', 'detail', id],
    queryFn: () => fetchEvaluationDimensionDetail(id as number | string),
    enabled: id != null,
    staleTime: 30_000,
  })
}

/** 评估分类（分类 facet + 分组视图组头 + 分类表单 Select） */
export function useEvaluationCategories() {
  return useQuery({
    queryKey: ['evaluation', 'categories'],
    queryFn: fetchEvaluationCategories,
    staleTime: 5 * 60_000,
  })
}

/** 算法选项（关联算法 facet singleSelect + 维度表单 Combobox） */
export function useAlgorithmOptions() {
  return useQuery({
    queryKey: ['algorithm', 'options'],
    queryFn: fetchAlgorithmOptions,
    staleTime: 5 * 60_000,
  })
}

/** 维度增删改 + 权重/排序/启停/批量（聚合 CRUD + invalidate 联动） */
export function useEvaluationMutations() {
  const queryClient = useQueryClient()

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['evaluation'] })
  }

  const save = useMutation({
    mutationFn: (input: Partial<Dimension>) => saveEvaluationDimension(input),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id: number | string) => deleteEvaluationDimension(id),
    onSuccess: invalidate,
  })

  const batch = useMutation({
    mutationFn: ({
      ids,
      action,
    }: {
      ids: Array<number | string>
      action: 'enable' | 'disable' | 'delete'
    }) => batchEvaluationDimensions(ids, action),
    onSuccess: invalidate,
  })

  const weight = useMutation({
    mutationFn: ({ id, weight }: { id: number | string; weight: number }) =>
      updateDimensionWeight(id, weight),
    onSuccess: invalidate,
  })

  // 行内启停（INT-2247）：只提交 { status }，不上送列表行的占位空配置
  const status = useMutation({
    mutationFn: ({ id, status }: { id: number | string; status: boolean }) =>
      updateDimensionStatus(id, status),
    onSuccess: invalidate,
  })

  const reorder = useMutation({
    mutationFn: (ids: Array<number | string>) => reorderDimension(ids),
    onSuccess: invalidate,
  })

  const duplicate = useMutation({
    mutationFn: (dimension: Dimension) => duplicateDimension(dimension),
    onSuccess: invalidate,
  })

  return { save, remove, batch, weight, status, reorder, duplicate, invalidate }
}

/** 规则试算（行内「规则试算」；门槛 evaluation:dim_manage） */
export function useCalculateScore() {
  return useMutation({
    mutationFn: ({ dimension, value }: { dimension: Dimension; value: number }) =>
      calculateDimensionScore(dimension, value),
  })
}

/** 测试 API 健康（行内「测试 API」；门槛 evaluation:read） */
export function useTestHealth() {
  return useMutation({
    mutationFn: (dimension: Dimension) => testDimensionHealth(dimension),
  })
}

/** 导入/导出维度（页头「导入/导出」下拉；门槛 evaluation:import_export） */
export function useEvaluationImportExport() {
  const queryClient = useQueryClient()

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['evaluation'] })
  }

  const importMutation = useMutation({
    mutationFn: ({ file, updateExisting }: { file: File; updateExisting: boolean }) =>
      importEvaluationDimensions(file, updateExisting),
    onSuccess: invalidate,
  })

  const exportMutation = useMutation({
    mutationFn: (format: 'json' | 'excel') => exportEvaluationDimensions(format),
  })

  return { import: importMutation, export: exportMutation, invalidate }
}

/** 分类保存/删除（分类表单 + 分组视图分类行操作；门槛 evaluation:category_manage） */
export function useEvaluationCategoryMutations() {
  const queryClient = useQueryClient()

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['evaluation'] })
  }

  const save = useMutation({
    mutationFn: (input: Partial<EvaluationCategory>) =>
      saveEvaluationCategory(input),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteEvaluationCategory(id),
    onSuccess: invalidate,
  })

  return { save, remove, invalidate }
}
