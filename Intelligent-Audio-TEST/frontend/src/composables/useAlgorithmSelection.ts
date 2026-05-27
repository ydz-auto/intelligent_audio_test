import { ref, computed } from 'vue'

export interface AlgorithmOption {
  value: string
  name: string
  group_id?: number
  group_name?: string
}

export interface UseAlgorithmSelectionOptions {
  onSelectCallback?: (type: string | null) => Promise<void> | void
}

export function useAlgorithmSelection(options: UseAlgorithmSelectionOptions = {}) {
  const algorithmList = ref<AlgorithmOption[]>([])
  const selectedAlgorithmType = ref<string | null>(null)
  const algorithmModalVisible = ref(false)
  const algorithmModalMode = ref<'list' | 'create' | 'edit'>('list')
  const algorithmEditData = ref<AlgorithmOption | null>(null)
  const algorithmSearchQuery = ref('')
  const editingAlgorithm = ref<AlgorithmOption | null>(null)

  const filteredAlgorithmList = computed(() => {
    if (!algorithmSearchQuery.value.trim()) {
      return algorithmList.value
    }
    const query = algorithmSearchQuery.value.toLowerCase().trim()
    return algorithmList.value.filter(algo =>
      algo.name?.toLowerCase().includes(query) ||
      algo.group_name?.toLowerCase().includes(query) ||
      algo.value?.toLowerCase().includes(query)
    )
  })

  async function loadAlgorithms() {
    try {
      const response = await fetch('/api/v1/algorithm/options')
      const result = await response.json()
      if (result.success) {
        algorithmList.value = result.data.algorithms || []
      }
    } catch (error) {
      console.error('加载算法列表失败:', error)
      algorithmList.value = []
    }
  }

  async function selectAlgorithm(type: string) {
    if (selectedAlgorithmType.value === type) {
      selectedAlgorithmType.value = null
      if (options.onSelectCallback) {
        await options.onSelectCallback(null)
      }
    } else {
      selectedAlgorithmType.value = type
      if (options.onSelectCallback) {
        await options.onSelectCallback(type)
      }
    }
  }

  function getAlgorithmName(type: string): string {
    const algo = algorithmList.value.find(a => a.value === type)
    return algo?.name || type || '未知算法'
  }

  function openAlgorithmModal() {
    algorithmModalMode.value = 'list'
    algorithmEditData.value = null
    algorithmModalVisible.value = true
  }

  function openCreateAlgorithmModal() {
    algorithmModalMode.value = 'create'
    algorithmEditData.value = null
    algorithmModalVisible.value = true
  }

  function closeAlgorithmModal() {
    algorithmModalVisible.value = false
    algorithmModalMode.value = 'list'
    algorithmEditData.value = null
    editingAlgorithm.value = null
  }

  async function openAlgorithmConfigModal(algo?: AlgorithmOption) {
    if (algo) {
      try {
        const response = await fetch(`/api/v1/algorithm/definitions/${algo.value}`)
        const result = await response.json()
        if (result.success && result.data) {
          editingAlgorithm.value = result.data
          algorithmEditData.value = result.data
        } else {
          editingAlgorithm.value = algo
          algorithmEditData.value = algo as any
        }
      } catch (error) {
        console.error('加载算法详情失败:', error)
        editingAlgorithm.value = algo
        algorithmEditData.value = algo as any
      }
      algorithmModalMode.value = 'edit'
    } else {
      algorithmModalMode.value = 'list'
      algorithmEditData.value = null
      editingAlgorithm.value = null
    }
    algorithmModalVisible.value = true
  }

  function searchAlgorithms() {
  }

  return {
    algorithmList,
    selectedAlgorithmType,
    algorithmModalVisible,
    algorithmModalMode,
    algorithmEditData,
    algorithmSearchQuery,
    editingAlgorithm,
    filteredAlgorithmList,
    loadAlgorithms,
    selectAlgorithm,
    getAlgorithmName,
    openAlgorithmModal,
    openCreateAlgorithmModal,
    closeAlgorithmModal,
    openAlgorithmConfigModal,
    searchAlgorithms
  }
}