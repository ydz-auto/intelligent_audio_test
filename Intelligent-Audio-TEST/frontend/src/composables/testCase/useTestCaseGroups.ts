import { testcasesPort } from './testcasesPort'
import { groupsPort } from './groupsPort'
import { useNotification } from '../modal/useNotification'
import { toUserErrorMessage } from '../../utils/errorMessage'
import type { TestCase, TestCaseGroup, GroupFormData } from '../../domain'
import { TestType } from '@/domain/enums'
import { UNGROUPED_GROUP_ID, UNGROUPED_GROUP_NAME, UNGROUPED_GROUP_FETCH_SIZE } from '../../domain'
// 分组视图类型统一从 testCaseStore 导出（GroupWithCount = TestCaseGroup 展示子集，
// GroupPaginationInfo = PaginationInfo + 筛选字段），消除两处重复定义
import type { GroupWithCount, GroupPaginationInfo } from '../../store/testCaseStore'

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

      const response = await groupsPort.getAll({
        page,
        perPage,
        algorithmType: params.algorithmType
      })

      if (response && response.items) {
        groupsList.value = response.items.map((g: any) => ({
          id: g.id,
          name: g.name,
          description: g.description,
          testCaseCount: g.testCaseCount ?? 0
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
      // INT-972：分组列表加载失败同样降级为固定友好文案（容器错误横幅消费同一 error 状态）
      error.value = toUserErrorMessage(err, '用例服务暂不可用，请稍后重试')
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

      // INT-249：未分组虚拟分组 —— 后端 query_testcases 无 group_id IS NULL 口径，
      // 无法服务端分页查询无分组用例；去掉 groupId 过滤单次大页拉取后前端过滤，
      // 分页回写 pages=1 封口（规模上限见 UNGROUPED_GROUP_FETCH_SIZE 注释）
      const isUngroupedFetch = groupKey === UNGROUPED_GROUP_ID

      // TODO: testcasesPort.getAll 尚未做 camelCase→snake_case 查询参数转换，adapter 补齐后此处保持 camelCase
      const response = await testcasesPort.getAll({
        page: isUngroupedFetch ? 1 : page,
        perPage: isUngroupedFetch ? UNGROUPED_GROUP_FETCH_SIZE : perPage,
        groupId: isUngroupedFetch ? undefined : groupId,
        keyword: params.keyword,
        tag: params.tag,
        algorithmType: params.algorithmType,
        type: params.testType,
        dimensionId: params.dimensionId,
        includeDeleted: params.includeDeleted || false,
        // INT-526：回收站态分组展开/懒加载与主拉取 fetchTestCases 口径一致（§5.3 双视图贯通）
        onlyDeleted: params.onlyDeleted || false
      })

      let casesData: TestCase[] = []
      if (response && response.items) {
        casesData = response.items.map((tc: any) => {
          return {
            ...tc,
            type: tc.type || TestType.API,
            deleted: tc.deleted || false
          } as TestCase
        })
      }
      if (isUngroupedFetch) {
        // 过滤口径与 organizeTestCasesByGroup 的未分组归桶规则一致：
        // 无 groupName 且 groupId 解析不到已知分组（含分组行已删的孤儿用例）
        casesData = casesData.filter(tc => {
          if (tc.groupName) return false
          const gid = tc.groupId?.toString()
          return !gid || !fullGroupsMap.value[gid]
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
        pages: isUngroupedFetch ? 1 : (response?.pages || 1),
        perPage: response?.perPage || perPage,
        total: isUngroupedFetch ? casesData.length : (response?.total || 0),
        algorithmType: params.algorithmType,
        testType: params.testType,
        keyword: params.keyword,
        dimensionId: params.dimensionId,
        // INT-526：回收站态分页续拉需保留 onlyDeleted，避免翻页退化回活跃口径
        onlyDeleted: params.onlyDeleted || false
      }

      const group = fullGroupsMap.value[groupKey]
      const groupName = group?.name
        || (isUngroupedFetch ? UNGROUPED_GROUP_NAME : `分组-${groupKey}`)
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
      // INT-972：分组用例加载失败降级为固定友好文案（不向错误横幅直出原始 RPC/网络异常文本）
      error.value = toUserErrorMessage(err, '用例服务暂不可用，请稍后重试')
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
      algorithmType: currentPagination.algorithmType,
      testType: currentPagination.testType,
      keyword: currentPagination.keyword,
      dimensionId: currentPagination.dimensionId,
      // INT-526：分页续拉随首拉口径续传 onlyDeleted
      onlyDeleted: currentPagination.onlyDeleted
    })
  }

  const addGroup = async (data: GroupFormData) => {
    try {
      error.value = null
      const response = await testcasesPort.createGroup(data)
      if (response) {
        const id = (response as any).id || `group-${Date.now()}`
        fullGroupsMap.value[id] = {
          ...response,
          id,
          name: data.name
        } as TestCaseGroup
        // INT-1313：新分组同步进 groupsList（分组视图计数/展开按名称解析 id）
        groupsList.value.push({
          id: id.toString(),
          name: data.name,
          description: data.description,
          testCaseCount: 0
        })
        allGroups.value = Object.keys(fullGroupsMap.value).map(k => fullGroupsMap.value[k].name)
        // INT-1313：重跑本地整理，testCaseGroups 立即出现新分组（无需整页刷新）
        organizeTestCasesByGroup()
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
          // fullGroupsMap 为空时（如按 algorithmType 过滤后分组不匹配），从后端查找
          try {
            const resp = await testcasesPort.getGroups({ page: 1, perPage: 1000 })
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

      await testcasesPort.updateGroup(groupId, data)

      const groupKey = groupId.toString()
      if (fullGroupsMap.value[groupKey]) {
        fullGroupsMap.value[groupKey].name = data.name
        fullGroupsMap.value[groupKey].description = data.description
        if (data.algorithmType !== undefined) {
          // Domain 侧为 camelCase：algorithmType
          fullGroupsMap.value[groupKey].algorithmType = data.algorithmType
        }
      } else {
        // INT-1313：fullGroupsMap 缺失（如按 algorithmType 过滤后分组不在当前集合），
        // 补录新名称，保证 organizeTestCasesByGroup 重建 testCaseGroups 时新名称立即可见
        fullGroupsMap.value[groupKey] = {
          id: groupId,
          name: data.name,
          description: data.description,
          algorithmType: data.algorithmType,
        } as TestCaseGroup
      }
      // INT-1313：改名同步进 groupsList（分组视图计数/展开按名称解析 id）；
      // 独立于 fullGroupsMap 判断——后端查找兜底路径（fullGroupsMap 无该分组）也同步。
      // 兼容 id 数值/字符串两种形态（fetchGroupsList 存原始值、fetchTestCases 存 toString）
      const entry = groupsList.value.find(g => String(g.id) === groupKey)
      if (entry) {
        entry.name = data.name
        entry.description = data.description
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
            const resp = await testcasesPort.getGroups({ page: 1, perPage: 1000 })
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

      await testcasesPort.deleteGroup(groupId)

      delete fullGroupsMap.value[groupId.toString()]
      // Domain 侧为 camelCase：groupId
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
