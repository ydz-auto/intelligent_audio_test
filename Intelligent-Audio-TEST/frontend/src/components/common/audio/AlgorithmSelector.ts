import { ref, watch, onMounted, computed, onUnmounted, nextTick } from 'vue'
import { useAlgorithmConfig } from '../../../composables/algorithm/useAlgorithmConfig'

interface AlgorithmOption {
  value: string
  name: string
  group_id?: number
  group_name?: string
}

interface AlgorithmRelation {
  algorithmType: string
  isPrimary: boolean
  weight: number
  params?: Record<string, any>
}

interface AlgorithmGroup {
  name: string
  algorithms: AlgorithmOption[]
}

export function useAlgorithmSelector(
  props: {
    modelValue?: string
    algorithmRelations?: AlgorithmRelation[]
    initialParams?: Record<string, any>
    showParams?: boolean
    single?: boolean
  },
  emit: (event: string, ...args: any[]) => void
) {
  const algorithmConfig = useAlgorithmConfig()
  const getAlgorithmOptions = algorithmConfig.getAlgorithmOptions
  const getFormSchema = algorithmConfig.getFormSchema
  const getAssociatedDimensions = algorithmConfig.getAssociatedDimensions
  const getCaseAlgorithmParams = algorithmConfig.getCaseAlgorithmParams
  const caseAlgorithmParamsDef = ref<any[]>([])

  const algorithmOptions = ref<AlgorithmOption[]>([])
  const selectedAlgorithms = ref<AlgorithmRelation[]>([...(props.algorithmRelations || [])])
  const algorithmFormSchema = ref<any>(null)
  const algorithmParams = ref<Record<string, any>>({ ...props.initialParams })
  // 记录最近一次应用的 initialParams 快照，避免 paramsChange 回流触发循环请求
  let lastAppliedInitialParams = ''
  const dynamicFormRef = ref<any>(null)
  const showDropdown = ref(false)
  const searchQuery = ref('')
  const dropdownRef = ref<HTMLElement | null>(null)
  const dropdownMenuRef = ref<HTMLElement | null>(null)
  const dropdownMenuStyle = ref<Record<string, string>>({})

  function updateDropdownPosition() {
    if (!dropdownRef.value || !showDropdown.value) return
    const rect = dropdownRef.value.getBoundingClientRect()
    const viewportHeight = window.innerHeight
    const menuMaxHeight = 300
    const spaceBelow = viewportHeight - rect.bottom
    const spaceAbove = rect.top
    const openUpward = spaceBelow < menuMaxHeight && spaceAbove > spaceBelow
    dropdownMenuStyle.value = {
      position: 'fixed',
      left: `${rect.left}px`,
      width: `${rect.width}px`,
      zIndex: '14000',
      ...(openUpward
        ? { bottom: `${viewportHeight - rect.top + 4}px`, top: 'auto' }
        : { top: `${rect.bottom + 4}px`, bottom: 'auto' })
    }
  }

  function toggleDropdown() {
    showDropdown.value = !showDropdown.value
    if (showDropdown.value) {
      searchQuery.value = ''
      nextTick(() => updateDropdownPosition())
    }
  }

  const primaryAlgorithmType = computed(() => {
    const primary = selectedAlgorithms.value.find(a => a.isPrimary)
    return primary ? primary.algorithmType : selectedAlgorithms.value[0]?.algorithmType || ''
  })

  const filteredGroups = computed(() => {
    const groups: Map<string, AlgorithmGroup> = new Map()

    const filtered = searchQuery.value
      ? algorithmOptions.value.filter(opt =>
          opt.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
          opt.value.toLowerCase().includes(searchQuery.value.toLowerCase())
        )
      : algorithmOptions.value

    filtered.forEach(opt => {
      const groupName = opt.group_name || '其他算法'
      if (!groups.has(groupName)) {
        groups.set(groupName, { name: groupName, algorithms: [] })
      }
      groups.get(groupName)!.algorithms.push(opt)
    })

    return Array.from(groups.values())
  })

  function getAlgorithmName(type: string): string {
    const opt = algorithmOptions.value.find(o => o.value === type)
    return opt ? opt.name : type
  }

  function isAlgorithmSelected(type: string): boolean {
    return selectedAlgorithms.value.some(a => a.algorithmType === type)
  }

  function isPrimaryAlgorithm(type: string): boolean {
    const algo = selectedAlgorithms.value.find(a => a.algorithmType === type)
    return algo ? algo.isPrimary : false
  }

  function closeDropdown(event: MouseEvent) {
    const target = event.target as Node
    if (dropdownRef.value && !dropdownRef.value.contains(target) &&
        dropdownMenuRef.value && !dropdownMenuRef.value.contains(target)) {
      showDropdown.value = false
    }
  }

  function toggleAlgorithm(type: string) {
    if (props.single) {
      if (selectedAlgorithms.value.length === 1 && selectedAlgorithms.value[0].algorithmType === type) {
        selectedAlgorithms.value = []
      } else {
        selectedAlgorithms.value = [{
          algorithmType: type,
          isPrimary: true,
          weight: 1.0
        }]
      }
    } else {
      const index = selectedAlgorithms.value.findIndex(a => a.algorithmType === type)
      if (index >= 0) {
        selectedAlgorithms.value.splice(index, 1)
        if (selectedAlgorithms.value.length > 0 && !selectedAlgorithms.value.some(a => a.isPrimary)) {
          selectedAlgorithms.value[0].isPrimary = true
        }
      } else {
        const isFirst = selectedAlgorithms.value.length === 0
        selectedAlgorithms.value.push({
          algorithmType: type,
          isPrimary: isFirst,
          weight: 1.0
        })
      }
    }
    emitChanges()
  }

  function removeAlgorithm(type: string) {
    const index = selectedAlgorithms.value.findIndex(a => a.algorithmType === type)
    if (index >= 0) {
      const wasPrimary = selectedAlgorithms.value[index].isPrimary
      selectedAlgorithms.value.splice(index, 1)
      if (wasPrimary && selectedAlgorithms.value.length > 0) {
        selectedAlgorithms.value[0].isPrimary = true
      }
      emitChanges()
    }
  }

  function setPrimaryAlgorithm(type: string) {
    selectedAlgorithms.value.forEach(a => {
      a.isPrimary = a.algorithmType === type
    })
    emitChanges()
  }

  function emitChanges() {
    const primaryType = primaryAlgorithmType.value
    emit('update:modelValue', primaryType)
    emit('update:algorithmRelations', [...selectedAlgorithms.value])
    emit('algorithmTypeChange', primaryType)

    if (primaryType) {
      loadAlgorithmFormSchema(primaryType)
    } else {
      algorithmFormSchema.value = null
      emit('dimensionsChange', [], [])
    }
  }

  async function loadAlgorithmOptions() {
    try {
      const options = await getAlgorithmOptions()
      algorithmOptions.value = (options || []).map((opt: any) => ({
        value: opt.value,
        name: opt.name || opt.label || opt.value,
        group_id: opt.group_id,
        group_name: opt.group_name
      }))
    } catch (error) {
      console.error('加载算法选项失败:', error)
      algorithmOptions.value = []
    }
  }

  async function loadAlgorithmFormSchema(algorithmType: string) {
    if (!algorithmType) {
      algorithmFormSchema.value = null
      caseAlgorithmParamsDef.value = []
      if (Object.keys(algorithmParams.value).length === 0) {
        algorithmParams.value = {}
      }
      emit('dimensionsChange', [], [])
      return
    }

    // showParams=false 场景（如音频上传）：不需要表单 schema 和默认值，
    // 用例参数应从标注 JSON 提取，不需要表单预填。只拉维度。
    if (!props.showParams) {
      algorithmFormSchema.value = null
      caseAlgorithmParamsDef.value = []
      algorithmParams.value = {}
      emit('paramsChange', {})
      try {
        const dimensionsData = await getAssociatedDimensions(algorithmType)
        if (dimensionsData) {
          const dimensions = dimensionsData.dimensions || []
          const dimensionIds = dimensionsData.dimension_ids || []
          emit('dimensionsChange', dimensions, dimensionIds)
        } else {
          emit('dimensionsChange', [], [])
        }
      } catch (error) {
        console.error('加载关联评估维度失败:', error)
        emit('dimensionsChange', [], [])
      }
      return
    }

    const savedParams = { ...algorithmParams.value }

    try {
      const [schema, caseParamsDef] = await Promise.all([
        getFormSchema(algorithmType),
        getCaseAlgorithmParams(algorithmType)
      ])
      algorithmFormSchema.value = schema
      caseAlgorithmParamsDef.value = caseParamsDef

      const newParams: Record<string, any> = {}

      if (schema?.fields) {
        schema.fields.forEach((field: any) => {
          const fieldCode = field.fieldCode
          if (savedParams[fieldCode] !== undefined) {
            newParams[fieldCode] = savedParams[fieldCode]
          } else if (field.defaultValue !== undefined) {
            newParams[fieldCode] = field.defaultValue
          }
        })

        for (const [key, value] of Object.entries(savedParams)) {
          if (newParams[key] === undefined) {
            newParams[key] = value
          }
        }
      }

      algorithmParams.value = newParams
      emit('paramsChange', {
        ...algorithmParams.value,
        caseAlgorithmParams: caseAlgorithmParamsDef.value,
        algorithmFormSchema: schema
      })
    } catch (error) {
      console.error('加载算法表单Schema失败:', error)
      algorithmFormSchema.value = null
      caseAlgorithmParamsDef.value = []
    }

    try {
      const dimensionsData = await getAssociatedDimensions(algorithmType)
      if (dimensionsData) {
        const dimensions = dimensionsData.dimensions || []
        const dimensionIds = dimensionsData.dimension_ids || []
        emit('dimensionsChange', dimensions, dimensionIds)
      } else {
        emit('dimensionsChange', [], [])
      }
    } catch (error) {
      console.error('加载关联评估维度失败:', error)
      emit('dimensionsChange', [], [])
    }
  }

  function onFieldChange(field: string, value: any) {
    algorithmParams.value[field] = value
    emit('paramsChange', {
      ...algorithmParams.value,
      caseAlgorithmParams: caseAlgorithmParamsDef.value,
      algorithmFormSchema: algorithmFormSchema.value
    })
  }

  watch(() => props.modelValue, (newValue) => {
    if (newValue && !selectedAlgorithms.value.some(a => a.algorithmType === newValue)) {
      selectedAlgorithms.value = [{
        algorithmType: newValue,
        isPrimary: true,
        weight: 1.0
      }]
    }
    if (newValue) {
      loadAlgorithmFormSchema(newValue)
    }
  })

  watch(() => props.algorithmRelations, (newValue) => {
    if (newValue && newValue.length > 0) {
      selectedAlgorithms.value = [...newValue]
      const primary = newValue.find(a => a.isPrimary)
      if (primary) {
        loadAlgorithmFormSchema(primary.algorithmType)
      }
    }
  }, { deep: true })

  watch(() => props.initialParams, (newValue) => {
    if (!newValue || Object.keys(newValue).length === 0) return
    // 内容未变化时跳过，避免 paramsChange 回流触发循环请求
    const snapshot = JSON.stringify(newValue)
    if (snapshot === lastAppliedInitialParams) return
    lastAppliedInitialParams = snapshot
    algorithmParams.value = { ...newValue }
    if (primaryAlgorithmType.value) {
      loadAlgorithmFormSchema(primaryAlgorithmType.value)
    }
  }, { deep: true })

  onMounted(async () => {
    document.addEventListener('click', closeDropdown)
    window.addEventListener('resize', updateDropdownPosition)
    window.addEventListener('scroll', updateDropdownPosition, true)
    await loadAlgorithmOptions()

    if (props.algorithmRelations && props.algorithmRelations.length > 0) {
      selectedAlgorithms.value = [...props.algorithmRelations]
      const primary = props.algorithmRelations.find(a => a.isPrimary)
      if (primary) {
        await loadAlgorithmFormSchema(primary.algorithmType)
      }
    } else if (props.modelValue) {
      selectedAlgorithms.value = [{
        algorithmType: props.modelValue,
        isPrimary: true,
        weight: 1.0
      }]
      await loadAlgorithmFormSchema(props.modelValue)
    }
  })

  onUnmounted(() => {
    document.removeEventListener('click', closeDropdown)
    window.removeEventListener('resize', updateDropdownPosition)
    window.removeEventListener('scroll', updateDropdownPosition, true)
  })

  return {
    selectedAlgorithms,
    showDropdown,
    searchQuery,
    dropdownRef,
    dropdownMenuRef,
    dropdownMenuStyle,
    toggleDropdown,
    filteredGroups,
    getAlgorithmName,
    isAlgorithmSelected,
    isPrimaryAlgorithm,
    toggleAlgorithm,
    removeAlgorithm,
    setPrimaryAlgorithm,
    primaryAlgorithmType,
    algorithmFormSchema,
    algorithmParams,
    dynamicFormRef,
    onFieldChange
  }
}
