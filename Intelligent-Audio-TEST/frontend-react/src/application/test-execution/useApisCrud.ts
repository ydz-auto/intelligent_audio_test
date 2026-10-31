/**
 * API CRUD + 连接测试编排（application 层；10_测试执行.md §5.3/§5.4）。
 * 新增/编辑（api_config:create/update）/删除（api_config:delete）/连接测试
 * （api_config:test）；成功 toast + 列表失效重拉。
 */
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { toast } from 'sonner'

import { deleteApi, fetchApiHealth, saveApi } from '@/infrastructure/api/test-execution-api'
import { saveApiScopeOverrides } from '@/infrastructure/api/param-profile-api'
import type { ApiConfig, ApiHealthCheckResult } from '@/domain/models/apiConfig'
import type { ApiScopeOverridesInput } from '@/domain/models/paramProfile'

export function useApisCrud() {
  const queryClient = useQueryClient()
  const [healthByApi, setHealthByApi] = useState<Record<number, ApiHealthCheckResult | 'testing'>>(
    {}
  )

  const refreshList = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['test-execution', 'apis'] })
  }, [queryClient])

  /**
   * 新增/编辑保存。返回成否（INT-1939）：调用方据此决定关不关弹窗——保存失败时
   * 弹窗保持打开、五页签草稿原样保留，用户可在弹窗内重试。
   *
   * `paramOverrides`：新建态在「参数配置」页签直接编辑的草稿，API 创建成功后立刻
   * 落到 api-scope 覆盖行（用户不必先保存再回来配参数）。覆盖失败不回滚 API
   * （已创建），只单独提示，用户可重开弹窗再保存一次。
   */
  const save = useCallback(
    async (
      input: Partial<ApiConfig> & { name: string },
      paramOverrides?: ApiScopeOverridesInput
    ): Promise<boolean> => {
      try {
        const { id } = await saveApi(input)
        toast.success('API 已保存')
        refreshList()
        if (paramOverrides && id > 0) {
          try {
            await saveApiScopeOverrides(id, paramOverrides)
          } catch (error) {
            toast.error(
              `API 已保存，但参数配置保存失败：${
                error instanceof Error ? error.message : String(error)
              }`
            )
          }
        }
        return true
      } catch (error) {
        toast.error(`保存失败：${error instanceof Error ? error.message : String(error)}`)
        return false
      }
    },
    [refreshList]
  )

  const remove = useCallback(
    async (api: ApiConfig) => {
      try {
        await deleteApi(api.id)
        toast.success('API 已删除')
        refreshList()
      } catch (error) {
        toast.error(`删除失败：${error instanceof Error ? error.message : String(error)}`)
      }
    },
    [refreshList]
  )

  /** 连接测试（§5.4；进行中 Spinner，结果弹窗展示） */
  const testConnection = useCallback(async (apiId: number): Promise<ApiHealthCheckResult | null> => {
    setHealthByApi((s) => ({ ...s, [apiId]: 'testing' }))
    try {
      const result = await fetchApiHealth(apiId)
      setHealthByApi((s) => ({ ...s, [apiId]: result }))
      return result
    } catch (error) {
      toast.error(`连接测试失败：${error instanceof Error ? error.message : String(error)}`)
      return null
    } finally {
      setHealthByApi((s) => ({ ...s, [apiId]: s[apiId] as ApiHealthCheckResult }))
    }
  }, [])

  return { save, remove, testConnection, healthByApi, refreshList }
}
