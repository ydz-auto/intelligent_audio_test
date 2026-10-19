import { ref, computed, onMounted } from 'vue'
import { TestType } from '@/domain/enums'
import { algorithmPort } from '../../composables/algorithm/algorithmPort'
import { useModalControl, MODAL_TYPES } from '../../composables/modal/useModal'
import { useNotification } from '../../composables/modal/useNotification'
import { usePagination } from '../../composables/usePagination'
import { toUserErrorMessage } from '@/utils/errorMessage'
import type { AlgorithmGroup, AlgorithmDefinition } from '@/domain'

/** INT-899（INT-858 N1）：错误消息安全化——原始 gRPC 异常文本不直出 Toast；
 *  非 Error 抛出（字符串等）保持「未知错误」兜底口径（INT-291 契约）。 */
function errorText(error: unknown): string {
  if (!(error instanceof Error)) return '未知错误'
  return toUserErrorMessage(error, '算法服务暂不可用，请稍后重试')
}

export function useAlgorithmConfigPage() {
  const modalControl = useModalControl()
  const notification = useNotification()

  const tabs = [
    { key: 'list', label: '算法列表' },
  ]

  const mappingTabs = [
    { key: 'device', label: '设备参数' },
    { key: TestType.API, label: 'API参数' },
    { key: 'evaluation', label: '评估参数' }
  ]

  const activeTab = ref('list')
  const activeMappingTab = ref('device')
  const loading = ref(false)
  const algorithms = ref<AlgorithmDefinition[]>([])
  const groups = ref<AlgorithmGroup[]>([])
  const currentAlgorithm = ref<AlgorithmDefinition | null>(null)
  const searchKeyword = ref('')
  const groupFilter = ref<number | string>('')
  const statusFilter = ref<string>('')

  const modalVisible = ref(false)
  const modalMode = ref<'list' | 'create' | 'edit'>('list')

  const filteredAlgorithms = computed(() => {
    let result = algorithms.value

    if (searchKeyword.value) {
      const keyword = searchKeyword.value.toLowerCase()
      result = result.filter(a =>
        a.type.toLowerCase().includes(keyword) ||
        a.name.toLowerCase().includes(keyword)
      )
    }

    if (groupFilter.value !== '') {
      result = result.filter(a => a.groupId === Number(groupFilter.value))
    }

    if (statusFilter.value !== '') {
      result = result.filter(a => a.status === statusFilter.value)
    }

    return result
  })

  // 使用通用分页 composable
  const { currentPage, pageSize, totalPages, paginatedItems: paginatedAlgorithms } = usePagination(filteredAlgorithms, ref(10))

  function getGroupName(group: string | undefined): string {
    const names: Record<string, string> = {
      basic: '基本配置',
      model: '模型配置',
      advanced: '高级选项'
    }
    return names[group || ''] || group || '-'
  }

  async function loadAlgorithms() {
    loading.value = true
    try {
      const result = await algorithmPort.getDefinitions()
      algorithms.value = (result?.data ?? []) as AlgorithmDefinition[]
    } catch (error) {
      console.error('加载算法列表失败:', error)
      // INT-291：失败必须可见——原先仅 console.error，列表落「暂无数据」与空态不可区分
      // INT-899：原始 gRPC 异常文本经 errorText 降级为固定文案，不直出 Toast
      notification.error('加载算法列表失败: ' + errorText(error))
    } finally {
      loading.value = false
    }
  }

  async function loadGroups() {
    try {
      const result = await algorithmPort.getGroups()
      groups.value = result?.data ?? []
    } catch (error) {
      console.error('加载分组列表失败:', error)
      notification.error('加载分组列表失败: ' + errorText(error))
    }
  }

  function handleCreate() {
    modalMode.value = 'create'
    currentAlgorithm.value = null
    modalVisible.value = true
  }

  function handleEdit(record: AlgorithmDefinition) {
    modalMode.value = 'edit'
    currentAlgorithm.value = JSON.parse(JSON.stringify(record))
    loadAlgorithmDetail(record.type).then(() => {
      modalVisible.value = true
    })
  }

  async function loadAlgorithmDetail(algoType: string) {
    try {
      const result = await algorithmPort.getDefinition(algoType)
      if (result) {
        currentAlgorithm.value = result as unknown as AlgorithmDefinition
      }
    } catch (error) {
      console.error('加载算法详情失败:', error)
      // 加载失败时弹窗仍以列表行浅数据打开，提示避免用户误以为主数据完整
      notification.error('加载算法详情失败: ' + errorText(error))
    }
  }

  function handleView(record: AlgorithmDefinition) {
    currentAlgorithm.value = record
    activeTab.value = 'detail'
  }

  /** 复制=纯新建：剔除行级 id。副本载荷若携带源算法行 id，后端 _update_params/_update_case_params/
   *  _update_mappings 的 id 对账分支按全局 id 取行且不校验归属，会改写源算法参数行而副本不产生
   *  自己的行（INT-211）。维度关联不用行 id 对账（adapter 恒传 dimension_id），无需处理。 */
  function stripRowIds(items: any[] | undefined | null): any[] | undefined | null {
    if (!items) return items
    return items.map((item: any) => {
      const next = { ...item }
      delete next.id
      return next
    })
  }

  async function handleClone(record: AlgorithmDefinition) {
    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认复制',
      content: `确定要复制算法「${record.name}」吗？`,
      confirmText: '复制',
      cancelText: '取消'
    })

    if (!confirmed) return

    try {
      const detail = await algorithmPort.getDefinition(record.type)
      const cloneData: any = detail ? { ...detail } : { ...record }
      cloneData.type = `${record.type}_copy`
      cloneData.name = `${record.name} (副本)`
      cloneData.deviceParams = stripRowIds(cloneData.deviceParams)
      cloneData.apiParams = stripRowIds(cloneData.apiParams)
      cloneData.caseParams = stripRowIds(cloneData.caseParams)
      if (cloneData.mappings) {
        cloneData.mappings = Object.fromEntries(
          Object.entries(cloneData.mappings).map(([sourceType, list]) => [
            sourceType,
            stripRowIds(list as any[]),
          ])
        )
      }
      await algorithmPort.createDefinition(cloneData)
      loadAlgorithms()
    } catch (error) {
      console.error('复制失败:', error)
      // INT-291：失败必须可见；loadAlgorithms 仅在成功路径调用，列表现状不被误清
      notification.error('复制算法失败: ' + errorText(error))
    }
  }

  async function confirmDelete(record: AlgorithmDefinition) {
    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认删除',
      content: `确定要删除算法「${record.name}」吗？此操作不可恢复。`,
      confirmText: '删除',
      cancelText: '取消',
      danger: true
    })

    if (confirmed) {
      await executeDelete(record)
    }
  }

  async function executeDelete(record: AlgorithmDefinition) {
    if (!record) return

    try {
      await algorithmPort.deleteDefinition(record.type)
      loadAlgorithms()
      if (activeTab.value === 'detail') {
        activeTab.value = 'list'
      }
    } catch (error) {
      console.error('删除失败:', error)
      // INT-291：失败必须可见；loadAlgorithms 仅在成功路径调用，列表现状不被误清
      notification.error('删除算法失败: ' + errorText(error))
    }
  }

  function handleSelect(data: AlgorithmDefinition) {
    console.log('Selected algorithm:', data)
  }

  function handleSearch() {
    currentPage.value = 1
  }

  function handleFilter() {
    currentPage.value = 1
  }

  function handleTabChange(tabKey: string) {
    activeTab.value = tabKey
    if (tabKey === 'list') {
      currentAlgorithm.value = null
    }
  }

  function handlePrevPage() {
    if (currentPage.value > 1) {
      currentPage.value--
    }
  }

  function handleNextPage() {
    if (currentPage.value < totalPages.value) {
      currentPage.value++
    }
  }

  function handleGoToPage(page: number) {
    currentPage.value = page
  }

  function handlePageSizeChange(newSize: number) {
    pageSize.value = newSize
    currentPage.value = 1
  }

  onMounted(() => {
    loadAlgorithms()
    loadGroups()
  })

  return {
    tabs,
    mappingTabs,
    activeTab,
    activeMappingTab,
    loading,
    algorithms,
    groups,
    currentAlgorithm,
    searchKeyword,
    groupFilter,
    statusFilter,
    modalVisible,
    modalMode,
    currentPage,
    pageSize,
    filteredAlgorithms,
    paginatedAlgorithms,
    getGroupName,
    loadAlgorithms,
    handleCreate,
    handleEdit,
    handleView,
    handleClone,
    confirmDelete,
    handleSelect,
    handleSearch,
    handleFilter,
    handleTabChange,
    handlePrevPage,
    handleNextPage,
    handleGoToPage,
    handlePageSizeChange
  }
}
