import { ref, computed, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { reportService } from '../../services/reportService'
import { useModalControl, MODAL_TYPES } from '../../composables/useModal'
import { useDeleteConfirm } from '../../composables/useDeleteConfirm'
import { useTestCaseStore } from '../../store/testCaseStore'
import { useTestCaseCard } from '../../composables/useTestCaseCard'
import { useDeviceManagement } from '../../composables/useDeviceManagement'
import { useTaskProgress } from '../../composables/useTaskProgress'
import { useTestControl } from '../../composables/useTestControl'
import { useAlgorithmSelection } from '../../composables/useAlgorithmSelection'
import { useTestReport } from '../../composables/useTestReport'
import { apisApi, tasksApi, reportsApi } from '../../utils/api'
import { generateDeviceFields } from '../../utils/utils'
import type { 
  TestCase, 
  Report, 
  APIConfig, 
  DeviceAPIComparisonItem,
  CaseExecutionItem,
  ModalSaveData, 
  ReportSummary
} from '../../shared/types'

interface Step {
  number: number;
  title: string;
  description: string;
}

interface AssociatedCase extends TestCase {
  status: string;
  duration?: string;
  executionStatus: string;
  evaluationStatus: string;
}

interface WindowWithTaskTime {
  taskExpectedCompleteTimeDisplay?: string
}

export function useApiTest() {
  const router = useRouter()
  const testCaseStore = useTestCaseStore()
  const {
    testCaseGroups,
    tags,
    isLoading,
    paginationInfo
  } = storeToRefs(testCaseStore)

  const {
    fetchTestCases,
    deleteGroup,
    deleteTestCase
  } = testCaseStore

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
    handleTestCaseAction
  } = useTestCaseCard();

  const currentStep = ref(0)
  const steps : Step[] = [
    { number: 0, title: '选择算法', description: '选择测试所使用的算法' },
    { number: 1, title: '选择用例', description: '选择需要执行的测试用例' },
    { number: 2, title: '配置参数', description: '配置执行参数和设备' },
    { number: 3, title: '执行测试', description: '运行测试并监控进度' },
    { number: 4, title: '查看报告', description: '查看和导出测试报告' }
  ]

  const {
    algorithmList,
    selectedAlgorithmType,
    algorithmModalVisible,
    algorithmSearchQuery,
    editingAlgorithm,
    filteredAlgorithmList,
    loadAlgorithms,
    selectAlgorithm,
    getAlgorithmName,
    openAlgorithmModal,
    openAlgorithmConfigModal,
    closeAlgorithmModal
  } = useAlgorithmSelection({
    onSelectCallback: async (type: string | null) => {
      if (type) {
        await fetchTestCases({ algorithmType: type })
      } else {
        await fetchTestCases()
      }
    }
  })

  const apis = ref<APIConfig[]>([])
  const apiSearchQuery = ref('')
  const apiFilter = ref('all')
  const selectedAPIIds = ref<(string | number)[]>([])
  const selectedTestCaseIds = ref<(string | number)[]>([])
  const activeTab = ref('cases')
  const taskName = ref('API测试任务')
  const concurrentTasks = ref(5)
  const currentTaskId = ref<string | number | null>(null)
  const isExecuting = computed(() => taskStatus.value === 'running' || taskStatus.value === 'starting' || taskStatus.value === 'pending')
  const executionProgress = computed(() => progressPercentage.value)
  
  const {
    isPaused,
    isControlling,
    pauseTest,
    resumeTest,
    stopTest
  } = useTestControl({
    currentTaskId,
    onStopped: () => {
      isExecuting.value = false
    }
  })
  
  // 分页状态
  const apiCurrentPage = ref(1)
  const apiPageSize = ref(12)
  const apiTotalItems = ref(0)
  const apiTotalPages = computed(() => Math.ceil(apiTotalItems.value / apiPageSize.value))

  const modalManager = useModalControl()
  
  const {
    progressPercentage,
    completedTests,
    inProgressTests,
    pendingTests,
    executionFailedTests,
    evaluationFailedTests,
    totalTestCases,
    taskStatus,
    elapsedTime,
    estimatedTime,
    expectedCompleteTime,
    logs,
    associatedCases,
    apiResources,
  } = useTaskProgress({
    testType: 'API',
    currentTaskId: currentTaskId,
    onCompleted: async () => {
      console.log('[API测试] 任务完成，加载报告数据并跳转')
      try {
        if (currentTaskId.value) {
          const reportData = await reportService.viewTaskReport({ 
            id: currentTaskId.value,
            name: taskName.value || 'API测试任务',
            type: 'api',
            status: 'completed',
            progress: 100,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString()
          } as any)
          report.value = { ...report.value, ...reportData }
          if (report.value?.id) {
            router.push({ name: 'reportView', params: { id: report.value.id } })
          } else {
            currentStep.value = 4
          }
        }
      } catch (error) {
        console.error('[API测试] 加载报告数据失败:', error)
        currentStep.value = 4
      }
    },
    onFailed: async (progressData) => {
      console.error('[API测试] 任务执行失败:', progressData)
      try {
        if (currentTaskId.value) {
          const reportData = await reportService.viewTaskReport({ 
            id: currentTaskId.value,
            name: taskName.value || 'API测试任务',
            type: 'api',
            status: 'failed',
            progress: progressPercentage.value,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString()
          } as any)
          report.value = { ...report.value, ...reportData }
          if (report.value?.id) {
            router.push({ name: 'reportView', params: { id: report.value.id } })
          } else {
            currentStep.value = 4
          }
        }
      } catch (error) {
        console.error('[API测试] 加载报告数据失败:', error)
        currentStep.value = 4
      }
    }
  })

  const allFilteredAPIs = computed(() => {
    return apis.value.filter(api => {
      if (!api) return false
      
      let matchesAlgorithm = true
      if (selectedAlgorithmType.value) {
        matchesAlgorithm = api.algorithmType === selectedAlgorithmType.value
      }
      
      let matchesStatus = true
      if (apiFilter.value !== 'all') {
        const normalizedStatus = api.status === 'online' ? 'online' : 'offline'
        matchesStatus = normalizedStatus === apiFilter.value
      }
      
      let matchesSearch = true
      if (apiSearchQuery.value) {
        const query = apiSearchQuery.value.toLowerCase()
        matchesSearch = Boolean(
          (api.name && api.name.toLowerCase().includes(query)) ||
          (api.apiEndpoints && api.apiEndpoints.some((ep: any) => {
            const urlValue = ep.url || ep.endpoint || '';
            return urlValue.toLowerCase().includes(query);
          }))
        )
      }
      
      return matchesAlgorithm && matchesStatus && matchesSearch
    })
  })

  // 分页后的API列表
  const filteredAPIs = computed(() => {
    const start = (apiCurrentPage.value - 1) * apiPageSize.value;
    const end = start + apiPageSize.value;
    return allFilteredAPIs.value.slice(start, end);
  })

  // 更新总数
  watch(allFilteredAPIs, (newVal) => {
    apiTotalItems.value = newVal.length;
    if (apiCurrentPage.value > apiTotalPages.value && apiTotalPages.value > 0) {
      apiCurrentPage.value = 1;
    }
  }, { immediate: true });

  // 分页方法
  const handleApiPageChange = (page: number) => {
    if (page >= 1 && page <= apiTotalPages.value) {
      apiCurrentPage.value = page;
    }
  };

  const handleApiPageSizeChange = (size: number) => {
    apiPageSize.value = size;
    apiCurrentPage.value = 1;
  };

  const handleApiPrevPage = () => {
    if (apiCurrentPage.value > 1) {
      apiCurrentPage.value--;
    }
  };

  const handleApiNextPage = () => {
    if (apiCurrentPage.value < apiTotalPages.value) {
      apiCurrentPage.value++;
    }
  };

  const deviceManagement = useDeviceManagement('api')

  const updateSelectedCases = (caseIds: (string | number)[]) => {
    selectedTestCaseIds.value = caseIds
    console.log('useAPITest: 更新选中的测试用例:', selectedTestCaseIds.value)
  }

  const openAPIEditModal = (apiData: APIConfig | null = null) => {
    console.log('openAPIEditModal called with apiData:', apiData)
    if (apiData && apiData.id) {
      console.log('Calling editDevice with id:', apiData.id)
      deviceManagement.editDevice(apiData.id, 'api')
    } else {
      console.log('Opening add API modal directly')
      modalManager.open(MODAL_TYPES.CRUD_FORM, {
        title: '添加测试API',
        entity: 'device',
        entityName: '测试API',
        mode: 'create',
        deviceType: 'api',
        fields: generateDeviceFields('api'),
        options: { closable: true, width: '800px' },
        onSubmit: async (deviceData: APIConfig, submitMode: 'create' | 'edit') => {
          try {
            let response
            if (submitMode === 'create') {
              response = await apisApi.create(deviceData)
            } else if (submitMode === 'edit' && deviceData.id) {
              response = await apisApi.update(deviceData.id, deviceData)
            }
            
            const apiDataResult = await apisApi.getAll()
            apis.value = (apiDataResult.items || apiDataResult) as APIConfig[]
            
            return response
          } catch (error) {
            console.error('API操作失败:', error)
            return null
          }
        }
      })
    }
  }

  const searchAPIs = () => {
    console.log('Searching APIs with query:', apiSearchQuery.value)
  }

  const filterAPIs = () => {
    console.log('Filtering APIs with status:', apiFilter.value)
  }

  const deleteAPI = async (apiId: string | number) => {
    console.log('deleteAPI called with apiId:', apiId)
    modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认删除',
      content: '确定要删除该测试API吗？此操作不可恢复。',
      confirmText: '删除',
      cancelText: '取消',
      options: { closable: true },
      onConfirm: async () => {
        try {
          console.log('Deleting API with id:', apiId)
          await apisApi.delete(apiId)
          const apiDataResult = await apisApi.getAll()
          apis.value = (apiDataResult.items || apiDataResult) as APIConfig[]
          console.log('API deleted successfully')
        } catch (error) {
          console.error('删除API失败:', error)
        }
      }
    })
  }

  const testAPI = async (apiId: string | number) => {
    if (deviceManagement && typeof deviceManagement.testDeviceConnection === 'function') {
      await deviceManagement.testDeviceConnection(apiId, 'api')
    } else {
      console.warn('设备管理组合式函数中未找到 testDeviceConnection 方法')
    }
  }

  const healthCheck = async (apiId: string | number) => {
    return testAPI(apiId)
  }

  const showAPIDetails = (apiId: string | number) => {
    const api = apis.value.find(a => String(a.id) === String(apiId))
    if (api) {
      modalManager.open(MODAL_TYPES.DETAIL_VIEW, {
        title: 'API详情',
        deviceId: String(apiId),
        options: { closable: true, width: '800px' }
      })
    }
  }

  const editAPI = (apiId: string | number) => {
    deviceManagement.editDevice(apiId, 'api')
  }

  const nextStep = async () => {
    if (currentStep.value === 2) {
      try {
        if (selectedTestCaseIds.value.length === 0) {
          alert('请至少选择一个测试用例')
          return
        }

        if (selectedAPIIds.value.length === 0) {
          alert('请至少选择一个在线API')
          return
        }

        const selectedApis = selectedAPIIds.value.map((id) => apis.value.find((a) => String(a?.id) === String(id))).filter(Boolean) as APIConfig[]
        const missingIds = selectedAPIIds.value.filter((id) => !apis.value.some((a) => String(a?.id) === String(id)))
        if (missingIds.length > 0) {
          alert('存在未找到的API，请重新选择')
          return
        }

        const nonOnlineApis = selectedApis.filter((a) => a.status !== 'online')
        if (nonOnlineApis.length > 0) {
          alert(`以下API处于离线状态，无法执行测试：${nonOnlineApis.map((a) => a.name).join(', ')}`)
          return
        }
        
        const taskData = { 
          name: taskName.value || 'API测试任务', 
          description: '通过API测试任务', 
          type: 'api', 
          caseIds: selectedTestCaseIds.value, 
          apiIds: selectedAPIIds.value, 
          tags: [] 
        }
        
        const taskResponse = await tasksApi.create(taskData)
        const taskId = taskResponse.id
        currentTaskId.value = taskId
        
        associatedCases.value = selectedTestCaseIds.value
          .map(id => {
            const allCases = Object.values(testCaseGroups.value as Record<string, TestCase[]>).flat()
            const testCase = allCases.find(tc => String(tc.id) === String(id))
            return testCase ? {
              ...testCase,
              status: 'pending',
              duration: '0',
              executionStatus: 'pending',
              evaluationStatus: 'pending'
            } as AssociatedCase : undefined
          })
          .filter((item): item is AssociatedCase => item !== undefined)
        
        totalTestCases.value = associatedCases.value.length
        pendingTests.value = totalTestCases.value
        
        const maxConcurrent = selectedApis.reduce((sum, api) => {
          return sum + (api.maxConcurrent || api.currentConcurrent || 5)
        }, 0)
        concurrentTasks.value = maxConcurrent
        
        const startResponse = await tasksApi.start(taskId)
        console.log('API测试任务已创建并启动:', taskId, startResponse)
        
        // 更新时间估计数据
        if (startResponse.expectedTotalTime) {
          estimatedTime.value = startResponse.expectedTotalTime
        }
        if (startResponse.expectedCompleteTime) {
          expectedCompleteTime.value = startResponse.expectedCompleteTime
        }
      } catch (error) {
        console.error('创建或启动API测试任务失败:', error)
        // 不再使用 alert 弹窗
      }
    }
    
    if (currentStep.value < 4) {
      currentStep.value++
    }
  }

  const prevStep = () => {
    if (currentStep.value > 1) {
      currentStep.value--
    }
  }

  const goToStep = (step: number) => {
    currentStep.value = step
  }

  const {
    report,
    isEditingReport,
    isEditingConclusion,
    analysisContent,
    setReport,
    toggleEditReport,
    toggleEditConclusion,
    cancelEditReport,
    cancelEditConclusion,
    saveConclusion,
    exportResults,
    publishReport,
    startNewTest
  } = useTestReport()

  const { confirmDeleteGroup, confirmDeleteTestCase } = useDeleteConfirm();

  const handleDeleteGroup = async (groupName: string) => {
    try {
      const confirmed = await confirmDeleteGroup(groupName);
      if (confirmed) {
        deleteGroup(groupName);
        await fetchTestCases();
      }
    } catch (error) {
      console.error('删除分组失败:', error);
      alert('删除分组失败: ' + (error instanceof Error ? error.message : '未知错误'));
    }
  };

  const handleDeleteTestCase = async (testCase: TestCase) => {
    try {
      const confirmed = await confirmDeleteTestCase(testCase.name);
      if (confirmed) {
        deleteTestCase(testCase.id);
        await fetchTestCases();
      }
    } catch (error) {
      console.error('删除测试用例失败:', error);
      alert('删除测试用例失败: ' + (error instanceof Error ? error.message : '未知错误'));
    }
  };

  const handleOpenEditModal = (testCase: TestCase) => {
    openEditTestCaseModal(testCase);
  };

  const handleSaveModal = async (data: ModalSaveData) => {
    const result = await handleModalSave(data);
    if (result?.needRefresh) {
      await fetchTestCases();
    }
  };

  const toggleAPISelection = (apiId: string | number) => {
    const api = apis.value.find((a) => String(a?.id) === String(apiId))
    if (!api || api.status !== 'online') {
      alert('只能选择在线API')
      return
    }
    const index = selectedAPIIds.value.indexOf(apiId)
    if (index === -1) {
      selectedAPIIds.value.push(apiId)
    } else {
      selectedAPIIds.value.splice(index, 1)
    }
  }

  const showTestCaseDetails = (testCaseId: string | number) => {
    if (currentTaskId.value) {
      modalManager.open(MODAL_TYPES.TEST_CASE_DETAIL, {
        taskId: currentTaskId.value,
        caseId: testCaseId,
        options: { width: '1200px' }
      });
    }
  }

  const deviceApiComparisonData = computed(() => reportService.deviceApiComparisonData.value)
  const caseExecutionData = computed(() => reportService.caseExecutionData.value)

  const saveReport = async () => {
    try {
      if (!report.value?.id) {
        console.warn('无法保存报告：报告ID为空')
        alert('无法保存报告：请先查看报告')
        return
      }
      await reportsApi.update(report.value.id, report.value)
      isEditingReport.value = false
      alert('报告已保存')
    } catch (error: any) {
      console.error('保存报告失败:', error)
      alert('保存报告失败: ' + (error.message || '未知错误'))
    }
  }

  const skipTestCase = (testCaseId: string | number) => {
    console.log(`Skipping test case ${testCaseId}...`)
  }

  const showAddTestCaseModalHandler = () => {
    openAddTestCaseModal('默认分组')
  }

  const removeTestCase = (testCaseId: string | number) => {
    console.log(`Removing test case ${testCaseId}...`)
  }

  const deviceAPIColumns = [
    { key: 'name', label: '名称', type: 'text', sortable: true },
    { key: 'type', label: '类型', type: 'text', sortable: true },
    { key: 'version', label: '版本', type: 'text', sortable: true },
    { key: 'status', label: '状态', type: 'status', sortable: true },
    { key: 'totalCases', label: '总用例数', type: 'number', sortable: true },
    { key: 'completedCases', label: '已完成用例数', type: 'number', sortable: true },
    { key: 'failedCases', label: '失败用例数', type: 'number', sortable: true },
    { key: 'successRate', label: '成功率(%)', type: 'number', sortable: true },
    { key: 'avgResponseTime', label: '平均响应时间(ms)', type: 'number', sortable: true },
    { key: 'stability', label: '稳定性(%)', type: 'number', sortable: true }
  ]

  const caseExecutionColumns = [
    { key: 'name', label: '名称', type: 'text', sortable: true },
    { key: 'total', label: '总用例数', type: 'number', sortable: true },
    { key: 'executed', label: '已执行', type: 'number', sortable: true },
    { key: 'passed', label: '通过', type: 'number', sortable: true },
    { key: 'failed', label: '失败', type: 'number', sortable: true },
    { key: 'successRate', label: '成功率', type: 'percentage', sortable: true },
    { key: 'failedRate', label: '失败率', type: 'percentage', sortable: true }
  ]

  const initAPITest = async () => {
    await loadAlgorithms()
    const algorithmType = selectedAlgorithmType.value || undefined
    await fetchTestCases({ algorithmType })

    try {
      const apiDataResult = await apisApi.getAll()
      // 确保正确处理API响应数据
      if (Array.isArray(apiDataResult)) {
        apis.value = apiDataResult as APIConfig[]
      } else if (apiDataResult && (apiDataResult as any).items) {
        apis.value = (apiDataResult as any).items as APIConfig[]
      } else if (apiDataResult && (apiDataResult as any).data) {
        apis.value = (apiDataResult as any).data as APIConfig[]
      } else {
        apis.value = []
      }
    } catch (error) {
      console.error('获取API数据失败:', error)
    }
  }

  return {
    currentStep,
    steps,
    apis,
    apiSearchQuery,
    apiFilter,
    selectedAPIIds,
    selectedTestCaseIds,
    activeTab,
    taskName,
    concurrentTasks,
    currentTaskId,
    isPaused,
    isControlling,
    isExecuting,
    executionProgress,
    report,
    isEditingReport,
    filteredAPIs,
    allFilteredAPIs,
    // API分页相关
    apiCurrentPage,
    apiPageSize,
    apiTotalItems,
    apiTotalPages,
    handleApiPageChange,
    handleApiPageSizeChange,
    handleApiPrevPage,
    handleApiNextPage,
    deviceApiComparisonData,
    caseExecutionData,
    analysisContent,
    progressPercentage,
    completedTests,
    inProgressTests,
    pendingTests,
    executionFailedTests,
    evaluationFailedTests,
    totalTestCases,
    taskStatus,
    elapsedTime,
    estimatedTime,
    expectedCompleteTime,
    logs,
    associatedCases,
    apiResources,
    testCaseGroups,
    tags,
    isLoading,
    casePaginationInfo: paginationInfo,
    formData,
    groupFormData,
    editingTestCase,
    editingGroup,
    initAPITest,
    nextStep,
    prevStep,
    goToStep,
    updateSelectedCases,
    toggleAPISelection,
    openAPIEditModal,
    deleteAPI,
    testAPI,
    healthCheck,
    showAPIDetails,
    editAPI,
    pauseTest,
    stopTest,
    resumeTest,
    showTestCaseDetails,
    toggleEditReport,
    cancelEditReport,
    handleDeleteGroup,
    handleDeleteTestCase,
    openAddTestCaseModal,
    handleOpenEditModal,
    openCreateGroupModal,
    openEditGroupModal,
    openImportTestCaseModal,
    openExportTestCaseModal,
    publishReport,
    saveReport,
    isEditingConclusion,
    toggleEditConclusion,
    cancelEditConclusion,
    saveConclusion,
    exportResults,
    skipTestCase,
    removeTestCase,
    startNewTest,
    deviceAPIColumns,
    caseExecutionColumns,
    algorithmList,
    filteredAlgorithmList,
    algorithmSearchQuery,
    selectedAlgorithmType,
    loadAlgorithms,
    selectAlgorithm,
    getAlgorithmName,
    openAlgorithmModal,
    openAlgorithmConfigModal,
    closeAlgorithmModal,
    algorithmModalVisible,
    editingAlgorithm
  }
}
