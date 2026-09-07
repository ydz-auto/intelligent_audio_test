import { ref, computed, onMounted } from 'vue'
import { TestType } from '@/domain/enums'
import { algorithmPort } from '../../composables/algorithm/algorithmPort'
import { useModalControl, MODAL_TYPES } from '../../composables/modal/useModal'
import { usePagination } from '../../composables/usePagination'
import type { AlgorithmGroup, AlgorithmDefinition } from '@/domain'

export function useAlgorithmConfigPage() {
  const modalControl = useModalControl()

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
    }
  }

  function handleView(record: AlgorithmDefinition) {
    currentAlgorithm.value = record
    activeTab.value = 'detail'
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
      await algorithmPort.createDefinition(cloneData)
      loadAlgorithms()
    } catch (error) {
      console.error('复制失败:', error)
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
