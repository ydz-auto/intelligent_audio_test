import { testcasesApi, groupsApi } from '../../utils/api'
import { snakeToCamelObject } from '../../utils/fieldNaming'
import { useNotification } from '../modal/useNotification'
import type { TestCase, TestCaseGroup, GroupFormData } from '../../shared/types'

interface GroupWithCount {
  id: string | number;
  name: string;
  description?: string;
  testCaseCount: number;
}

interface GroupPaginationInfo {
  page: number;
  pages: number;
  perPage: number;
  total: number;
  algorithmType?: string;
}

/**
 * 测试用例分组管理 composable。
 *
 * 接收 testCaseStore 实例作为参数，访问/修改分组相关状态（groupsList /
 * fullGroupsMap / loadedGroupCases 等），并提供分组增删改、按分组拉取用例、
 * 按分组加载更多等能力。organizeTestCasesByGroup / extractTags 由 store
 * 传入（作为核心本地状态操作），composable 仅复用以避免逻辑重复。
 * 所有方法名与返回值与原 testCaseStore 中的实现保持一致。
 */
export function useTestCaseGroups(store: {
  testCases: import('vue').Ref<TestCase[]>
  testCaseGroups: import('vue').Ref<Record<string, TestCase[]>>
  tags: import('vue').Ref<string[]>
  isLoading: import('vue').Ref<boolean>
  error: import('vue').Ref<string | null>
  allGroups: import('vue').Ref<string[]>
  fullGroupsMap: import('vue').Ref<Record<string, TestCaseGroup>>
  groupsList: import('vue').Ref<GroupWithCount[]>
  loadedGroupCases: import('vue').Ref<Record<string, TestCase[]>>
  groupLoadingStates: import('vue').Ref<Record<string, boolean>>
  groupPagination: import('vue').Ref<Record<string, GroupPaginationInfo>>
  organizeTestCasesByGroup: () => void
  extractTags: () => void
  handleError: (err: any, errorMessage: string) => boolean
  DEFAULT_GROUP_PAGE_SIZE: number
}) {
  const notification = useNotification()

  const {
    testCases,
    testCaseGroups,
    tags,
    isLoading,
    error,
    allGroups,
    fullGroupsMap,
    groupsList,
    loadedGroupCases,
    groupLoadingStates,
    groupPagination,
    organizeTestCasesByGroup,
    extractTags,
    handleError,
    DEFAULT_GROUP_PAGE_SIZE
  } = store

  // 显式标记这些状态在 composable 内被读取，避免 TS 未使用报错；
  // tags / allGroups / testCaseGroups 实际由 organizeTestCasesByGroup /
  // extractTags 间接写入，这里保留引用以明确依赖关系。
  void tags
  void allGroups
  void testCaseGroups

  const fetchGroupsList = async (params: Record<string, any> = {}) => {
    try {
      isLoading.value = true
      error.value = null

      const page = params.page || 1
      const perPage = params.perPage || 100

      const response = await groupsApi.getAll({
        page,
        perPage,
        algorithmType: params.algorithmType
      })

      if (response && response.items) {
        groupsList.value = response.items.map((g: any) => ({
          id: g.id,
          name: g.name,
          description: g.description,
          testCaseCount: g.testCaseCount ?? g.test_case_count ?? 0
        }))

        fullGroupsMap.value = response.items.reduce((map: Record<string, TestCaseGroup>, g: any) => {
          const id = g.id?.toString() || `group-${Date.now()}`
          map[id] = { ...g, id, name: g.name } as TestCaseGroup
          return map
        }, {} as Record<string, TestCaseGroup>)

        allGroups.value = groupsList.value.map(g => g.name)

        const initialGroups: Record<string, TestCase[]> = {}
        groupsList.value.forEach(g => {
          initialGroups[g.name] = []
        })
        testCaseGroups.value = initialGroups
      }

      return groupsList.value
    } catch (err: any) {
      console.error('获取分组列表失败:', err)
      error.value = err.message || '获取分组列表失败'
      return []
    } finally {
      isLoading.value = false
    }
  }

  const fetchCasesByGroup = async (groupId: string | number, params: Record<string, any> = {}) => {
    const groupKey = groupId.toString()

    if (groupLoadingStates.value[groupKey]) {
      return
    }

    try {
      groupLoadingStates.value[groupKey] = true
      error.value = null

      const page = params.page || 1
      const perPage = params.perPage || DEFAULT_GROUP_PAGE_SIZE

      const response = await testcasesApi.getAll({
        page,
        perPage,
        group_id: groupId,
        keyword: params.keyword,
        tag: params.tag,
        algorithm_type: params.algorithmType,
        include_deleted: params.includeDeleted || false
      })

      let casesData: TestCase[] = []
      if (response && response.items) {
        casesData = response.items.map((tc: any) => {
          const normalized = snakeToCamelObject(tc)
          return {
            ...normalized,
            type: normalized.type || 'api',
            deleted: normalized.deleted || false
          } as TestCase
        })
      }

      if (page === 1) {
        loadedGroupCases.value[groupKey] = casesData
      } else {
        loadedGroupCases.value[groupKey] = [
          ...(loadedGroupCases.value[groupKey] || []),
          ...casesData
        ]
      }

      groupPagination.value[groupKey] = {
        page: response?.page || page,
        pages: response?.pages || 1,
        perPage: response?.perPage || perPage,
        total: response?.total || 0,
        algorithmType: params.algorithmType
      }

      const group = fullGroupsMap.value[groupKey]
      const groupName = group?.name || `分组-${groupKey}`
      testCaseGroups.value[groupName] = [...(loadedGroupCases.value[groupKey] || [])]

      casesData.forEach(tc => {
        const existingIndex = testCases.value.findIndex(t => t.id === tc.id)
        if (existingIndex === -1) {
          testCases.value.push(tc)
        } else {
          testCases.value[existingIndex] = tc
        }
      })

      extractTags()

      return {
        cases: casesData,
        pagination: groupPagination.value[groupKey],
        hasMore: (response?.page || 1) < (response?.pages || 1)
      }
    } catch (err: any) {
      console.error(`获取分组 ${groupId} 用例失败:`, err)
      error.value = err.message || `获取分组用例失败`
      return null
    } finally {
      groupLoadingStates.value[groupKey] = false
    }
  }

  const loadMoreGroupCases = async (groupId: string | number) => {
    const groupKey = groupId.toString()
    const currentPagination = groupPagination.value[groupKey]

    if (!currentPagination || currentPagination.page >= currentPagination.pages) {
      return null
    }

    return fetchCasesByGroup(groupId, {
      page: currentPagination.page + 1,
      algorithmType: currentPagination.algorithmType
    })
  }

  const addGroup = async (data: GroupFormData) => {
    try {
      error.value = null
      const response = await testcasesApi.createGroup(data)
      if (response) {
        const id = (response as any).id || `group-${Date.now()}`
        fullGroupsMap.value[id] = {
          ...response,
          id,
          name: data.name
        } as TestCaseGroup
        allGroups.value = Object.keys(fullGroupsMap.value).map(k => fullGroupsMap.value[k].name)
      }
      return true
    } catch (err: any) {
      return handleError(err, '添加分组失败')
    }
  }

  const updateGroup = async (idOrName: string | number, data: GroupFormData) => {
    try {
      error.value = null
      let groupId: string | number

      if (typeof idOrName === 'string') {
        const groupEntry = Object.entries(fullGroupsMap.value).find(([_, group]) => group.name === idOrName)
        if (groupEntry) {
          groupId = groupEntry[0]
        } else {
          // fullGroupsMap 为空时（如按 algorithm_type 过滤后分组不匹配），从后端查找
          try {
            const resp = await testcasesApi.getGroups({ page: 1, perPage: 1000 })
            const found = resp?.items?.find((g: any) => g.name === idOrName)
            if (found) {
              groupId = found.id
            } else {
              throw new Error(`未找到名为 "${idOrName}" 的分组`)
            }
          } catch {
            throw new Error(`未找到名为 "${idOrName}" 的分组`)
          }
        }
      } else {
        groupId = idOrName
      }

      await testcasesApi.updateGroup(groupId, data)

      if (fullGroupsMap.value[groupId.toString()]) {
        fullGroupsMap.value[groupId.toString()].name = data.name
        fullGroupsMap.value[groupId.toString()].description = data.description
        if (data.algorithmType !== undefined) {
          fullGroupsMap.value[groupId.toString()].algorithmType = data.algorithmType
        }
      }
      organizeTestCasesByGroup()
      return true
    } catch (err: any) {
      return handleError(err, '更新分组失败')
    }
  }

  const deleteGroup = async (idOrName: string | number) => {
    try {
      error.value = null
      let groupId: string | number

      if (typeof idOrName === 'string') {
        const groupEntry = Object.entries(fullGroupsMap.value).find(([_, group]) => group.name === idOrName)
        if (groupEntry) {
          groupId = groupEntry[0]
        } else {
          // fullGroupsMap 为空时，从后端查找
          try {
            const resp = await testcasesApi.getGroups({ page: 1, perPage: 1000 })
            const found = resp?.items?.find((g: any) => g.name === idOrName)
            if (found) {
              groupId = found.id
            } else {
              throw new Error(`未找到名为 "${idOrName}" 的分组`)
            }
          } catch {
            throw new Error(`未找到名为 "${idOrName}" 的分组`)
          }
        }
      } else {
        groupId = idOrName
      }

      await testcasesApi.deleteGroup(groupId)

      delete fullGroupsMap.value[groupId.toString()]
      testCases.value = testCases.value.filter(tc => tc.groupId?.toString() !== groupId.toString())

      organizeTestCasesByGroup()
      notification.success('删除分组成功')
      return true
    } catch (err: any) {
      return handleError(err, '删除分组失败')
    }
  }

  return {
    fetchGroupsList,
    fetchCasesByGroup,
    loadMoreGroupCases,
    addGroup,
    updateGroup,
    deleteGroup
  }
}
