/**
 * 算法配置页 query hooks（application 层；17_配置运维.md §11 组件树落位）。
 * queryKey 前缀 ['algorithm-definitions'] / ['algorithm-groups'] 与全局算法切换器
 * （INT-344）共享语义；新建/编辑/复制/删除/分组变更后 invalidate 自动刷新。
 * 接线后列表全量经 client.ts（GET /algorithm/definitions INT-297 信封），前端过滤分页（§12-4）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  bulkDeleteAlgorithms,
  createAlgorithm,
  createAlgorithmGroup,
  deleteAlgorithm,
  deleteAlgorithmGroup,
  fetchAlgorithmDefinitions,
  fetchAlgorithmGroups,
  reloadAlgorithmConfig,
  updateAlgorithm,
  updateAlgorithmGroup,
  type SaveAlgorithmInput,
  type SaveGroupInput,
} from '@/infrastructure/api/algorithm-config-api'
import { fetchDimensionOptions } from '@/infrastructure/api/evaluation-api'

/** 算法定义列表（全量；前端过滤/分页） */
export function useAlgorithmDefinitions() {
  return useQuery({
    queryKey: ['algorithm-definitions'],
    queryFn: fetchAlgorithmDefinitions,
    staleTime: 30_000,
  })
}

/** 算法分组列表（facet 选项 + 分组管理 + 编辑 Sheet 所属分组 Select 共用） */
export function useAlgorithmGroups() {
  return useQuery({
    queryKey: ['algorithm-groups'],
    queryFn: fetchAlgorithmGroups,
    staleTime: 5 * 60_000,
  })
}

/** 评估维度选项（§6.6 关联维度 Select / §6.5 评估映射 target 选项；
 *  数据源 GET /evaluation/dimensions/options，仅主维度） */
export function useAlgorithmDimensionOptions() {
  return useQuery({
    queryKey: ['evaluation-dimension-options'],
    queryFn: async () => {
      const items = await fetchDimensionOptions()
      return items.map((d) => ({ id: d.id, name: d.name }))
    },
    staleTime: 5 * 60_000,
  })
}

/** 新建/编辑/复制/删除/批量删除/重载（聚合 CRUD + invalidate） */
export function useAlgorithmMutations() {
  const queryClient = useQueryClient()

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['algorithm-definitions'] })
    void queryClient.invalidateQueries({ queryKey: ['algorithm-groups'] })
  }

  const save = useMutation({
    mutationFn: (input: SaveAlgorithmInput & { isNew: boolean }) =>
      input.isNew ? createAlgorithm(input) : updateAlgorithm(input.type, input),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (type: string) => deleteAlgorithm(type),
    onSuccess: invalidate,
  })

  const bulkRemove = useMutation({
    mutationFn: (types: string[]) => bulkDeleteAlgorithms(types),
    onSuccess: invalidate,
  })

  const reload = useMutation({
    mutationFn: () => reloadAlgorithmConfig(),
  })

  return {
    save,
    remove,
    bulkRemove,
    reload,
    invalidate,
  }
}

/** 分组 CRUD（§7.1） */
export function useAlgorithmGroupMutations() {
  const queryClient = useQueryClient()

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['algorithm-groups'] })
    void queryClient.invalidateQueries({ queryKey: ['algorithm-definitions'] })
  }

  const create = useMutation({
    mutationFn: (input: SaveGroupInput) => createAlgorithmGroup(input),
    onSuccess: invalidate,
  })

  const update = useMutation({
    mutationFn: ({ id, input }: { id: number; input: SaveGroupInput }) =>
      updateAlgorithmGroup(id, input),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteAlgorithmGroup(id),
    onSuccess: invalidate,
  })

  return { create, update, remove, invalidate }
}
