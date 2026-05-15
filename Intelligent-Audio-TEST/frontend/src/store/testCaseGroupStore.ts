import { defineStore } from 'pinia'
import { ref, reactive, computed, watch } from 'vue'

export interface TestCaseGroup {
  id: string | number;
  name: string;
  description?: string;
  cases?: any[];
  expanded?: boolean;
  [key: string]: any;
}

export const useTestCaseGroupStore = defineStore('testCaseGroup', () => {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const groups = reactive<Record<string | number, TestCaseGroup>>({})

  const STORAGE_KEY = 'test-case-groups-store'
  const autoSave = ref(true)

  const groupsArray = computed(() => Object.values(groups))

  const loadFromStorage = () => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        const data = JSON.parse(stored)
        Object.assign(groups, data.groups || {})
        if (typeof data.autoSave !== 'undefined') {
          autoSave.value = data.autoSave
        }
      }
    } catch (e) {
      console.warn('[TestCaseGroupStore] Failed to load from storage:', e)
    }
  }

  const saveToStorage = () => {
    if (!autoSave.value) return
    try {
      const data = {
        groups: { ...groups },
        autoSave: autoSave.value
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    } catch (e) {
      console.warn('[TestCaseGroupStore] Failed to save to storage:', e)
    }
  }

  const setGroups = (groupList: TestCaseGroup[]) => {
    Object.keys(groups).forEach(key => delete groups[key])
    groupList.forEach(group => {
      groups[group.id] = { ...group, expanded: groups[group.id]?.expanded ?? false }
    })
    saveToStorage()
  }

  const addGroup = (group: Partial<TestCaseGroup>) => {
    const id = group.id || `group-${Date.now()}`
    groups[id] = { id, name: group.name || '未命名分组', description: group.description || '', cases: [], ...group, expanded: false }
    saveToStorage()
    return groups[id]
  }

  const updateGroup = (groupId: string | number, updates: Partial<TestCaseGroup>) => {
    if (groups[groupId]) {
      Object.assign(groups[groupId], updates)
      saveToStorage()
      return true
    }
    return false
  }

  const deleteGroup = (groupId: string | number) => {
    if (groups[groupId]) {
      delete groups[groupId]
      saveToStorage()
      return true
    }
    return false
  }

  const toggleGroupExpansion = (groupId: string | number) => {
    if (groups[groupId]) {
      groups[groupId].expanded = !groups[groupId].expanded
      saveToStorage()
    }
  }

  const getGroup = (groupId: string | number) => {
    return groups[groupId] || null
  }

  const resetState = () => {
    Object.keys(groups).forEach(key => delete groups[key])
    error.value = null
    saveToStorage()
  }

  watch(groups, () => {
    saveToStorage()
  }, { deep: true })

  loadFromStorage()

  return { groups, groupsArray, loading, error, setGroups, addGroup, updateGroup, deleteGroup, toggleGroupExpansion, getGroup, resetState, saveToStorage, loadFromStorage }
})
