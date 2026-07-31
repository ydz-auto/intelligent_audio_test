import { computed, type Ref } from 'vue'
import { storeToRefs } from 'pinia'
import { normalizeTestCaseConfig } from '../../utils/utils'
import { useTestCaseCard } from '../testCase/useTestCaseCard'
import { useTestCaseStore } from '../../store/testCaseStore'
import { useE2eTest } from '../e2e/useE2eTest'
import { useModalControl, MODAL_TYPES } from '../modal/useModal'
import { useDeleteConfirm } from '../modal/useDeleteConfirm'
import type { TestCase, TestCaseFormData } from '../../shared/types'

interface UseTestCaseOpsOptions {
  testType: 'e2e' | 'api'
  selectedAlgorithmType: Ref<string | null>
  addLog: (log: any) => void
}

/**
 * 测试用例通用操作：删除分组/用例、保存、编辑模态窗、标签筛选
 * 内部根据 testType 自动选择 e2e 或 api 的用例来源
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

  // e2e 模式使用 useE2eTest；api 模式直接使用 store
  const e2eTest = testType === 'e2e' ? useE2eTest() : null
  const storeRefs = testType === 'api' ? storeToRefs(testCaseStore) : null

  // 统一的访问器
  const testCaseGroups = computed<Record<string, TestCase[]>>(() => {
    if (testType === 'e2e') return (e2eTest!.e2eTestCaseGroups.value || {}) as Record<string, TestCase[]>
    return (storeRefs!.testCaseGroups.value || {}) as Record<string, TestCase[]>
  })

  const tags = computed<string[]>(() => {
    if (testType === 'e2e') return (e2eTest!.tags.value || []) as string[]
    return (storeRefs!.tags.value || []) as string[]
  })

  const tagViewData = computed(() => {
    if (testType === 'e2e') return (e2eTest!.tagViewData.value || {}) as any
    return (storeRefs!.tagViewData.value || {}) as any
  })

  const isLoading = computed(() => {
    if (testType === 'e2e') return !!e2eTest!.isLoading.value
    return !!storeRefs!.isLoading.value
  })

  const casePaginationInfo = computed(() => {
    if (testType === 'e2e') return e2eTest!.paginationInfo.value
    return storeRefs!.paginationInfo.value
  })

  /** 统一的初始化用例方法 */
  const initializeTestCases = async (algorithmType?: string) => {
    if (testType === 'e2e') {
      await e2eTest!.initializeE2eTests(algorithmType)
    } else {
      await testCaseStore.fetchTestCases({ algorithmType })
    }
  }

  /** 统一的 fetchTagView */
  const fetchTagView = async (params: Record<string, any> = {}) => {
    if (testType === 'e2e') {
      await e2eTest!.fetchTagView(params)
    } else {
      await testCaseStore.fetchTagView(params)
    }
  }

  /** 标签筛选变化（仅 testType 不同） */
  const handleTagFilterChange = (filters: { keyword?: string; testType?: string; algorithmType?: string }) => {
    fetchTagView({
      keyword: filters.keyword,
      testType,
      algorithmType: filters.algorithmType || selectedAlgorithmType.value || undefined,
    })
  }

  /** 删除分组 */
  const handleDeleteGroup = async (groupName: string) => {
    try {
      const confirmed = await confirmDeleteGroup(groupName)
      if (confirmed) {
        await testCaseStore.deleteGroup(groupName)
        await initializeTestCases(selectedAlgorithmType.value || undefined)
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
        await initializeTestCases(selectedAlgorithmType.value || undefined)
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
        await initializeTestCases(selectedAlgorithmType.value || undefined)
      }
    } catch (error) {
      console.error('[useTestCaseOps] 保存失败:', error)
      const errorMessage = error instanceof Error ? error.message : '保存失败，请重试'
      addLog({ content: errorMessage, level: 'error' })
    }
  }

  /** 编辑用例模态窗：e2e 自定义打开流程，api 直接复用 useTestCaseCard */
  const handleOpenEditModal = async (testCase: TestCase) => {
    if (testType === 'e2e') {
      editingTestCase.value = testCase

      const normalized = normalizeTestCaseConfig(testCase.config || {})
      const testCaseType = (testCase as any).test_type || (testCase as any).testType || 'e2e'

      formData.value = {
        id: testCase.id,
        name: testCase.name || '',
        group: testCase.groupName || '',
        groupId: testCase.groupId || '',
        description: testCase.description || '',
        tags: (testCase.tags || []).map(t => typeof t === 'string' ? t : t.name),
        tagsInput: (testCase.tags || []).map(t => typeof t === 'string' ? t : t.name).join(', '),
        config: normalized as TestCaseFormData['config'],
        algorithmType: (testCase as any).algorithmType || (testCase as any).algorithm_type || '',
        test_type: testCaseType as 'api' | 'e2e',
        algorithm_params: Array.isArray((testCase as any).algorithmParams || (testCase as any).algorithm_params)
          ? ((testCase as any).algorithmParams || (testCase as any).algorithm_params)
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
          await handleModalSave(result)
        }
      } catch (error) {
        console.error('[useTestCaseOps] 打开编辑用例模态窗失败:', error)
      }
    } else {
      openEditTestCaseModal(testCase)
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
    isLoading,
    casePaginationInfo,
    e2eTestCases: computed(() => e2eTest?.e2eTestCases.value || []),
    initializeTestCases,
    fetchTagView,
    handleTagFilterChange,
    handleDeleteGroup,
    handleDeleteTestCase,
    handleSaveModal,
    handleOpenEditModal,
    showTestCaseDetails,
    openAddTestCaseModal,
    openCreateGroupModal,
    openEditGroupModal,
    openImportTestCaseModal,
    openExportTestCaseModal,
  }
}
