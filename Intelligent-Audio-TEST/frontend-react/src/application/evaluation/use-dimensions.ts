/**
 * 评估维度页 query hooks（application 层；11_用例域.md §9 组件树落位）。
 * queryKey：['evaluation','dimensions'] / ['evaluation','categories'] / ['algorithm','options']。
 * 维度增删/权重/启停后 invalidate(['evaluation'])——与用例管理「评估维度」facet
 * （['evaluation','dimensions','options']）同前缀联动刷新（§4.3 三页口径）。
 */
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
  fetchEvaluationCategories,
  fetchEvaluationDimensionDetail,
  fetchEvaluationDimensions,
  importEvaluationDimensions,
  reorderDimension,
  saveEvaluationCategory,
  saveEvaluationDimension,
  testDimensionHealth,
  updateDimensionWeight,
} from '@/infrastructure/api/evaluation-api'

/** 评估维度全量（列表/分组双视图共用；主/子同屏聚合） */
export function useEvaluationDimensions() {
  return useQuery({
    queryKey: ['evaluation', 'dimensions'],
    queryFn: fetchEvaluationDimensions,
    staleTime: 30_000,
  })
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

  const reorder = useMutation({
    mutationFn: (ids: Array<number | string>) => reorderDimension(ids),
    onSuccess: invalidate,
  })

  const duplicate = useMutation({
    mutationFn: (dimension: Dimension) => duplicateDimension(dimension),
    onSuccess: invalidate,
  })

  return { save, remove, batch, weight, reorder, duplicate, invalidate }
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
