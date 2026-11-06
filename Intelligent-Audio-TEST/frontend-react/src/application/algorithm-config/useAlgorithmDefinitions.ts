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
  fetchCaseCountByAlgorithmType,
  reloadAlgorithmConfig,
  updateAlgorithm,
  updateAlgorithmGroup,
  type SaveAlgorithmInput,
  type SaveGroupInput,
} from '@/infrastructure/api/algorithm-config-api'

/** 算法定义列表（全量；前端过滤/分页） */
export function useAlgorithmDefinitions() {
  return useQuery({
    queryKey: ['algorithm-definitions'],
    queryFn: fetchAlgorithmDefinitions,
    staleTime: 30_000,
  })
}

/**
 * 关联用例计数（§154/P3-1（INT-1319）异步补齐）：后端列表项未返回 case_count 时启用，
 * 按算法 type 逐个经 testcases 的 algorithm_type 聚合 total，不阻塞列表首屏；
 * 返回 type → count Map，由页面合并进 definitions 的 caseCount。
 * types 为 []（后端已返计数 / 列表空）时禁用，不发请求。
 */
export function useAlgorithmCaseCounts(types: string[]) {
  return useQuery({
    queryKey: ['algorithm-case-counts', types],
    queryFn: () => fetchCaseCountByAlgorithmType(types),
    enabled: types.length > 0,
    staleTime: 5 * 60_000,
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

/** 评估维度全量/分类由 index.tsx 直接经 useEvaluationDimensions/useEvaluationCategories
 *  拉取（INT-1030：映射/关联维度选择改分组/主维度/子维度，原仅主维度 options 退役） */

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
