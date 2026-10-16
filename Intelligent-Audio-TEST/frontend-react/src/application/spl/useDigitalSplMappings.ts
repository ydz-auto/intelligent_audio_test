/**
 * 数字域 RMS-SPL 映射 query hooks（application 层；16_设备域.md §10 组件树落位）。
 * queryKey 前缀 ['digital-spl'] / ['api-refs']；增删改/校准/设默认后 invalidate
 * 自动刷新列表与 API 引用（默认指针随 setDefault 变化）。
 * 数字域无独立 stats 端点——统计前端 computed 聚合（§4.1.2 / §11-20）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  ApiConfigRef,
  ApiRmsSplMapping,
} from '@/domain/models/digitalSpl'
import {
  calibrateDigitalSplMapping,
  createDigitalSplMapping,
  deleteDigitalSplMapping,
  fetchApiRefs,
  fetchDigitalSplMappings,
  setDefaultDigitalSplMapping,
  updateDigitalSplMapping,
} from '@/infrastructure/api/digital-spl-api'

/** 数字域映射列表（§4.3；GET /digital-spl） */
export function useDigitalSplMappings() {
  return useQuery({
    queryKey: ['digital-spl'],
    queryFn: fetchDigitalSplMappings,
    staleTime: 30_000,
  })
}

/** 被测 API facet 选项（§4.1.1；GET /apis，含默认指针） */
export function useApiRefs() {
  return useQuery({
    queryKey: ['api-refs'],
    queryFn: fetchApiRefs,
    staleTime: 5 * 60_000,
  })
}

/** 数字域增删改/校准/设默认（聚合 CRUD + invalidate） */
export function useDigitalSplMutations() {
  const queryClient = useQueryClient()

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['digital-spl'] })
    void queryClient.invalidateQueries({ queryKey: ['api-refs'] })
  }

  const create = useMutation({
    mutationFn: (input: Omit<ApiRmsSplMapping, 'id' | 'createdAt' | 'updatedAt'>) =>
      createDigitalSplMapping(input),
    onSuccess: invalidate,
  })

  const update = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<ApiRmsSplMapping> }) =>
      updateDigitalSplMapping(id, patch),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteDigitalSplMapping(id),
    onSuccess: invalidate,
  })

  const calibrate = useMutation({
    mutationFn: ({
      id,
      points,
    }: {
      id: number
      points: Array<{ targetSpl: number; gainLinear: number; rmsDbfs: number | null }>
    }) => calibrateDigitalSplMapping(id, points),
    onSuccess: invalidate,
  })

  const setDefault = useMutation({
    mutationFn: ({ apiId, mappingId }: { apiId: number; mappingId: number | null }) =>
      setDefaultDigitalSplMapping(apiId, mappingId),
    onSuccess: invalidate,
  })

  return { create, update, remove, calibrate, setDefault, invalidate }
}

export type { ApiConfigRef, ApiRmsSplMapping }
