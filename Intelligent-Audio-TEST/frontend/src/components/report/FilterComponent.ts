import { ref, computed } from 'vue'

export function useFilterComponent(props: any, emit: any) {
  // 初始化筛选值
  const initFilterValues = () => {
    const initialFilterValues: any = {}
    props.filterGroups.forEach((group: any) => {
      if (group.type === 'checkbox' || group.type === 'tagCloud') {
        initialFilterValues[group.key] = []
      } else if (group.type === 'dateRange' || group.type === 'range') {
        initialFilterValues[group.key] = {
          min: group.initialMin || (group.type === 'dateRange' ? '' : group.min),
          max: group.initialMax || (group.type === 'dateRange' ? '' : group.max)
        }
      } else {
        initialFilterValues[group.key] = group.initialValue || ''
      }
    })
    return initialFilterValues
  }

  const filterValues = ref(initFilterValues())

  // 处理筛选值变化
  const handleFilterChange = () => {
    emit('filterChange', filterValues.value)
  }

  // 应用筛选
  const applyFilters = () => {
    emit('apply', filterValues.value)
  }

  // 重置筛选
  const resetFilters = () => {
    // 重置筛选值
    props.filterGroups.forEach((group: any) => {
      if (group.type === 'checkbox' || group.type === 'tagCloud') {
        filterValues.value[group.key] = []
      } else if (group.type === 'dateRange' || group.type === 'range') {
        filterValues.value[group.key] = {
          min: group.initialMin || (group.type === 'dateRange' ? '' : group.min),
          max: group.initialMax || (group.type === 'dateRange' ? '' : group.max)
        }
      } else {
        filterValues.value[group.key] = group.initialValue || ''
      }
    })

    emit('reset')
    emit('filterChange', filterValues.value)
  }

  // 切换标签选择
  const toggleTag = (groupKey: any, tagValue: any) => {
    const index = filterValues.value[groupKey].indexOf(tagValue)
    if (index > -1) {
      filterValues.value[groupKey].splice(index, 1)
    } else {
      filterValues.value[groupKey].push(tagValue)
    }
    handleFilterChange()
  }

  // 移除单个筛选条件
  const removeFilter = (key: any) => {
    const group = props.filterGroups.find((g: any) => g.key === key)
    if (group) {
      if (group.type === 'checkbox' || group.type === 'tagCloud') {
        filterValues.value[key] = []
      } else if (group.type === 'dateRange' || group.type === 'range') {
        filterValues.value[key] = {
          min: group.initialMin || (group.type === 'dateRange' ? '' : group.min),
          max: group.initialMax || (group.type === 'dateRange' ? '' : group.max)
        }
      } else {
        filterValues.value[key] = group.initialValue || ''
      }
      handleFilterChange()
    }
  }

  // 获取已选筛选条件
  const getActiveFilters = () => {
    const activeFilters: any = {}
    Object.entries(filterValues.value).forEach(([key, value]: any) => {
      if (Array.isArray(value)) {
        if (value.length > 0) {
          activeFilters[key] = value
        }
      } else if (typeof value === 'object') {
        if (value.min || value.max) {
          activeFilters[key] = value
        }
      } else if (value) {
        activeFilters[key] = value
      }
    })
    return activeFilters
  }

  // 获取筛选条件标签
  const getFilterLabel = (key: any) => {
    const group = props.filterGroups.find((g: any) => g.key === key)
    return group ? group.label : key
  }

  // 获取筛选值显示文本
  const getFilterDisplayValue = (key: any, value: any) => {
    const group = props.filterGroups.find((g: any) => g.key === key)
    if (!group) return String(value)

    if (Array.isArray(value)) {
      return value
        .map((v: any) => {
          const option = group.options.find((o: any) => o.value === v)
          return option ? option.label : v
        })
        .join(', ')
    } else if (typeof value === 'object') {
      if (group.type === 'dateRange') {
        return `${value.min || '不限'} - ${value.max || '不限'}`
      } else if (group.type === 'range') {
        return `${value.min} - ${value.max}`
      }
    } else {
      const option = group.options.find((o: any) => o.value === value)
      return option ? option.label : value
    }

    return String(value)
  }

  // 计算已选筛选条件数量
  const activeFilterCount = computed(() => {
    return Object.keys(getActiveFilters()).length
  })

  return {
    filterValues,
    activeFilterCount,
    handleFilterChange,
    applyFilters,
    resetFilters,
    toggleTag,
    removeFilter,
    getActiveFilters,
    getFilterLabel,
    getFilterDisplayValue
  }
}
