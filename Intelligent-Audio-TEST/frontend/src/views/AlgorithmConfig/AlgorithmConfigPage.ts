import { ref, computed, onMounted } from 'vue'
import { useModalControl, MODAL_TYPES } from '../../composables/modal/useModal'

interface AlgorithmRecord {
  type: string
  name: string
  group_id?: number
  group_name?: string
  description?: string
  status: string
  icon?: string
  display_order: number
  params?: any[]
  mappings?: {
    device: any[]
    api: any[]
    evaluation: any[]
  }
}

interface AlgorithmGroup {
  id: number
  name: string
  description?: string
  icon?: string
  display_order: number
}

export function useAlgorithmConfigPage() {
  const modalControl = useModalControl()

  const tabs = [
    { key: 'list', label: '算法列表' },
  ]

  const mappingTabs = [
    { key: 'device', label: '设备参数' },
    { key: 'api', label: 'API参数' },
    { key: 'evaluation', label: '评估参数' }
  ]

  const activeTab = ref('list')
  const activeMappingTab = ref('device')
  const loading = ref(false)
  const algorithms = ref<AlgorithmRecord[]>([])
  const groups = ref<AlgorithmGroup[]>([])
  const currentAlgorithm = ref<AlgorithmRecord | null>(null)
  const searchKeyword = ref('')
  const groupFilter = ref<number | string>('')
  const statusFilter = ref<string>('')

  const modalVisible = ref(false)
  const modalMode = ref<'list' | 'create' | 'edit'>('list')

  const currentPage = ref(1)
  const pageSize = ref(10)

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
      result = result.filter(a => a.group_id === Number(groupFilter.value))
    }

    if (statusFilter.value !== '') {
      result = result.filter(a => a.status === statusFilter.value)
    }

    return result
  })

  const paginatedAlgorithms = computed(() => {
    const start = (currentPage.value - 1) * pageSize.value
    const end = start + pageSize.value
    return filteredAlgorithms.value.slice(start, end)
  })

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
      const response = await fetch('/api/v1/algorithm/definitions')
      const result = await response.json()
      if (result.success) {
        algorithms.value = (result.data.data || []).map(normalizeAlgorithmFields)
      }
    } catch (error) {
      console.error('加载算法列表失败:', error)
    } finally {
      loading.value = false
    }
  }

  function normalizeAlgorithmFields(algo: any) {
    return {
      ...algo,
      group_id: algo.groupId ?? algo.group_id,
      group_name: algo.groupName ?? algo.group_name,
      display_order: algo.displayOrder ?? algo.display_order,
      device_params: algo.deviceParams ?? algo.device_params ?? [],
      api_params: algo.apiParams ?? algo.api_params ?? [],
      case_params: algo.caseParams ?? algo.case_params ?? [],
      params: algo.params ?? [],
      mappings: algo.mappings ?? { device: [], api: [], evaluation: [] },
      associated_dimensions: algo.associatedDimensions ?? algo.associated_dimensions ?? [],
      reference_params: algo.referenceParams ?? algo.reference_params ?? []
    }
  }

  async function loadGroups() {
    try {
      const response = await fetch('/api/v1/algorithm/groups')
      const result = await response.json()
      if (result.success) {
        groups.value = result.data?.data || []
      }
    } catch (error) {
      console.error('加载分组列表失败:', error)
    }
  }

  function handleCreate() {
    modalMode.value = 'create'
    currentAlgorithm.value = null
    modalVisible.value = true
  }

  function handleEdit(record: AlgorithmRecord) {
    modalMode.value = 'edit'
    currentAlgorithm.value = JSON.parse(JSON.stringify(record))
    loadAlgorithmDetail(record.type).then(() => {
      modalVisible.value = true
    })
  }

  async function loadAlgorithmDetail(algoType: string) {
    try {
      const response = await fetch(`/api/v1/algorithm/definitions/${algoType}`)
      const result = await response.json()
      if (result.success && result.data) {
        currentAlgorithm.value = normalizeAlgorithmFields(result.data)
      }
    } catch (error) {
      console.error('加载算法详情失败:', error)
    }
  }

  function handleView(record: AlgorithmRecord) {
    currentAlgorithm.value = record
    activeTab.value = 'detail'
  }

  async function handleClone(record: AlgorithmRecord) {
    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认复制',
      content: `确定要复制算法「${record.name}」吗？`,
      confirmText: '复制',
      cancelText: '取消'
    })

    if (!confirmed) return

    try {
      const detailResponse = await fetch(`/api/v1/algorithm/definitions/${record.type}`)
      const detailResult = await detailResponse.json()
      let cloneData: any = { ...record }
      if (detailResult.success && detailResult.data) {
        cloneData = normalizeAlgorithmFields(detailResult.data)
      }

      const response = await fetch('/api/v1/algorithm/definitions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...cloneData,
          type: `${record.type}_copy`,
          name: `${record.name} (副本)`
        })
      })
      const result = await response.json()
      if (result.success) {
        loadAlgorithms()
      } else {
        console.error('复制失败:', result.message)
      }
    } catch (error) {
      console.error('复制失败:', error)
    }
  }

  async function confirmDelete(record: AlgorithmRecord) {
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

  async function executeDelete(record: AlgorithmRecord) {
    if (!record) return

    try {
      const response = await fetch(`/api/v1/algorithm/definitions/${record.type}`, {
        method: 'DELETE'
      })
      const result = await response.json()
      if (result.success) {
        loadAlgorithms()
        if (activeTab.value === 'detail') {
          activeTab.value = 'list'
        }
      } else {
        console.error('删除失败:', result.message)
      }
    } catch (error) {
      console.error('删除失败:', error)
    }
  }

  function handleSelect(data: AlgorithmRecord) {
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
    const totalPages = Math.ceil(filteredAlgorithms.value.length / pageSize.value)
    if (currentPage.value < totalPages) {
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
