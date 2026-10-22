import { computed, type Ref } from 'vue'
import { storeToRefs } from 'pinia'
import { normalizeTestCaseConfig } from '../../utils/utils'
import { useTestCaseCard } from '../testCase/useTestCaseCard'
import { useTestCaseStore } from '../../store/testCaseStore'
import { useE2eTest } from '../e2e/useE2eTest'
import { useModalControl, MODAL_TYPES } from '../modal/useModal'
import { useDeleteConfirm } from '../modal/useDeleteConfirm'
import type { TestCase, TestCaseFormData } from '../../domain'
import { TestType } from '@/domain/enums'

interface UseTestCaseOpsOptions {
  /** 'all' = 合并流程（/start-test INT-486 口径）：用例不分类型，走 store 路径且不附 test_type */
  testType: typeof TestType[keyof typeof TestType] | 'all'
  selectedAlgorithmType: Ref<string | null>
  addLog: (log: any) => void
}

/**
 * 测试用例通用操作：删除分组/用例、保存、编辑模态窗、标签筛选
 * 内部根据 testType 自动选择 e2e 或 api 的用例来源；'all'（合并流程）走 store 路径、不附类型过滤
 */
export function useTestCaseOps(options: UseTestCaseOpsOptions) {
  const { testType, selectedAlgorithmType, addLog } = options
  const modalManager = useModalControl()
  const testCaseStore = useTestCaseStore()
  const { confirmDeleteGroup, confirmDeleteTestCase } = useDeleteConfirm()

  const {
    formData,
    groupFormData,
    editingTestCase,
    editingGroup,
    openAddTestCaseModal,
    openEditTestCaseModal,
    openCreateGroupModal,
    openEditGroupModal,
    openImportTestCaseModal,
    openExportTestCaseModal,
    handleModalSave,
    handleTestCaseAction,
  } = useTestCaseCard()

  // e2e 模式使用 useE2eTest；api / all（合并流程）模式直接使用 store
  const e2eTest = testType === TestType.E2E ? useE2eTest() : null
  const storeRefs = testType !== TestType.E2E ? storeToRefs(testCaseStore) : null
  /** 合并流程（'all'）请求不附 test_type：后端返回全类型用例 */
  const filterTestType = testType === 'all' ? undefined : testType

  // 统一的访问器
  const testCaseGroups = computed<Record<string, TestCase[]>>(() => {
    if (testType === TestType.E2E) return (e2eTest!.e2eTestCaseGroups.value || {}) as Record<string, TestCase[]>
    return (storeRefs!.testCaseGroups.value || {}) as Record<string, TestCase[]>
  })

  const tags = computed<string[]>(() => {
    if (testType === TestType.E2E) return (e2eTest!.tags.value || []) as string[]
    return (storeRefs!.tags.value || []) as string[]
  })

  const tagViewData = computed(() => {
    if (testType === TestType.E2E) return (e2eTest!.tagViewData.value || {}) as any
    return (storeRefs!.tagViewData.value || {}) as any
  })

  const tagViewPagination = computed(() => {
    if (testType === TestType.E2E) return (e2eTest!.tagViewPagination.value || {}) as any
    return (storeRefs!.tagViewPagination.value || {}) as any
  })

  const tagViewLoading = computed(() => {
    if (testType === TestType.E2E) return !!e2eTest!.tagViewLoading.value
    return !!storeRefs!.tagViewLoading.value
  })

  const isLoading = computed(() => {
    if (testType === TestType.E2E) return !!e2eTest!.isLoading.value
    return !!storeRefs!.isLoading.value
  })

  /** 分组视图加载错误（合并流程 store 路径；容器错误横幅消费） */
  const error = computed<string | null>(() => {
    if (testType === TestType.E2E) return null
    return (storeRefs!.error.value ?? null) as string | null
  })

  /** INT-1314：标签视图首拉失败（独立于分组 error；容器据此自动降级到分组视图） */
  const tagViewError = computed<string | null>(() => {
    if (testType === TestType.E2E) return null
    return (storeRefs!.tagViewError.value ?? null) as string | null
  })

  const casePaginationInfo = computed(() => {
    if (testType === TestType.E2E) return e2eTest!.paginationInfo.value
    return storeRefs!.paginationInfo.value
  })

  /** 统一的初始化用例方法 */
  const initializeTestCases = async (algorithmType?: string) => {
    if (testType === TestType.E2E) {
      await e2eTest!.initializeE2eTests(algorithmType)
    } else {
      await testCaseStore.fetchTestCases({ algorithmType })
    }
  }

  /** 统一的 fetchTagView */
  const fetchTagView = async (params: Record<string, any> = {}) => {
    if (testType === TestType.E2E) {
      await e2eTest!.fetchTagView(params)
    } else {
      await testCaseStore.fetchTagView(params)
    }
  }

  /** 统一的 loadMoreTagView（标签视图后端分页追加加载） */
  const loadMoreTagView = async () => {
    if (testType === TestType.E2E) {
      await e2eTest!.loadMoreTagView()
    } else {
      await testCaseStore.loadMoreTagView()
    }
  }

  /**
   * CRUD 成功后统一刷新数据：标签视图（按上次过滤参数）+ 分组视图。
   * 标签视图与分组视图共用同一 store，按上次过滤参数拉取即可保持当前标签页的筛选上下文。
   */
  const refreshAfterOps = async () => {
    await testCaseStore.refreshTagView()
    await initializeTestCases(selectedAlgorithmType.value || undefined)
  }

  /** 标签筛选变化（仅 testType 不同） */
  const handleTagFilterChange = (filters: { keyword?: string; testType?: string; algorithmType?: string; dimensionId?: number }) => {
    fetchTagView({
      keyword: filters.keyword,
      testType: filterTestType,
      algorithmType: filters.algorithmType || selectedAlgorithmType.value || undefined,
      dimensionId: filters.dimensionId,
    })
  }

  /** 分组视图筛选变化时重新请求数据 */
  const handleGroupFilterChange = (filters: { keyword?: string; testType?: string; algorithmType?: string; dimensionId?: number }) => {
    if (testType === TestType.E2E) {
      e2eTest!.initializeE2eTests(
        filters.algorithmType || selectedAlgorithmType.value || undefined,
        filters.keyword,
        filters.dimensionId
      )
    } else {
      testCaseStore.fetchTestCases({
        keyword: filters.keyword,
        testType: filterTestType,
        algorithmType: filters.algorithmType || selectedAlgorithmType.value || undefined,
        dimensionId: filters.dimensionId,
      })
    }
  }

  /** 删除分组 */
  const handleDeleteGroup = async (groupName: string) => {
    try {
      const confirmed = await confirmDeleteGroup(groupName)
      if (confirmed) {
        await testCaseStore.deleteGroup(groupName)
        await refreshAfterOps()
      }
    } catch (error) {
      console.error('[useTestCaseOps] 删除分组失败:', error)
      const errorMessage = error instanceof Error ? error.message : '删除分组失败，请重试'
      addLog({ content: errorMessage, level: 'error' })
    }
  }

  /** 删除测试用例 */
  const handleDeleteTestCase = async (testCase: TestCase) => {
    try {
      const confirmed = await confirmDeleteTestCase(testCase.name)
      if (confirmed) {
        await testCaseStore.deleteTestCase(testCase.id)
        await refreshAfterOps()
      }
    } catch (error) {
      console.error('[useTestCaseOps] 删除测试用例失败:', error)
      const errorMessage = error instanceof Error ? error.message : '删除测试用例失败，请重试'
      addLog({ content: errorMessage, level: 'error' })
    }
  }

  /** 保存模态窗 */
  const handleSaveModal = async (data: any) => {
    try {
      const result = await handleModalSave(data)
      if (result?.needRefresh) {
        await refreshAfterOps()
      }
    } catch (error) {
      console.error('[useTestCaseOps] 保存失败:', error)
      const errorMessage = error instanceof Error ? error.message : '保存失败，请重试'
      addLog({ content: errorMessage, level: 'error' })
    }
  }

  /** 打开新增用例模态窗，保存成功后按当前视图刷新（含标签视图） */
  const handleOpenAddModal = async (group = '', options?: { algorithmType?: string; testType?: typeof TestType[keyof typeof TestType]; tags?: string[] }) => {
    const result = await openAddTestCaseModal(group, options)
    if (result?.needRefresh) {
      await refreshAfterOps()
    }
  }

  /** 编辑用例模态窗：e2e 自定义打开流程，api 直接复用 useTestCaseCard；保存成功后按视图刷新 */
  const handleOpenEditModal = async (testCase: TestCase) => {
    if (testType === TestType.E2E) {
      editingTestCase.value = testCase

      const normalized = normalizeTestCaseConfig(testCase.config || {})
      // 编辑回填只信任域模型 testType（adapter 已从列表项 type 派生，INT-196）；
      // 不再 || TestType.E2E 兜底——API 用例曾被恒锁成 E2E 表单
      const testCaseType = testCase.testType

      formData.value = {
        id: testCase.id,
        name: testCase.name || '',
        group: testCase.groupName || '',
        // INT-195：不回填 groupId——同 useTestCaseCard，groupId 由保存边界按所选分组名收敛
        description: testCase.description || '',
        tags: (testCase.tags || []).map(t => typeof t === 'string' ? t : t.name),
        tagsInput: (testCase.tags || []).map(t => typeof t === 'string' ? t : t.name).join(', '),
        config: normalized as TestCaseFormData['config'],
        algorithmType: testCase.algorithmType || '',
        testType: testCaseType,
        algorithmParams: Array.isArray(testCase.algorithmParams)
          ? testCase.algorithmParams
          : [],
      } as TestCaseFormData

      try {
        const result = await modalManager.open(MODAL_TYPES.TEST_CASE_RELATED, {
          visible: true,
          mode: 'case',
          testType: testCaseType,
          formData: formData.value,
          title: '编辑测试用例',
          width: '1800px',
          maxWidth: '98vw',
        })

        if (result) {
          const saveResult = await handleModalSave(result)
          if (saveResult?.needRefresh) {
            await refreshAfterOps()
          }
        }
      } catch (error) {
        console.error('[useTestCaseOps] 打开编辑用例模态窗失败:', error)
      }
    } else {
      const saveResult = await openEditTestCaseModal(testCase)
      if (saveResult?.needRefresh) {
        await refreshAfterOps()
      }
    }
  }

  /** 显示用例详情 */
  const showTestCaseDetails = (testCaseId: string | number, taskId: string | number | null) => {
    if (taskId) {
      modalManager.open(MODAL_TYPES.TEST_CASE_DETAIL, {
        taskId,
        caseId: testCaseId,
      })
    }
  }

  return {
    formData,
    groupFormData,
    editingTestCase,
    editingGroup,
    testCaseGroups,
    tags,
    tagViewData,
    tagViewPagination,
    tagViewLoading,
    isLoading,
    error,
    tagViewError,
    casePaginationInfo,
    e2eTestCases: computed(() => e2eTest?.e2eTestCases.value || []),
    initializeTestCases,
    fetchTagView,
    loadMoreTagView,
    handleTagFilterChange,
    handleGroupFilterChange,
    handleDeleteGroup,
    handleDeleteTestCase,
    handleSaveModal,
    handleOpenAddModal,
    handleOpenEditModal,
    showTestCaseDetails,
    openCreateGroupModal,
    openEditGroupModal,
    openImportTestCaseModal,
    openExportTestCaseModal,
  }
}
