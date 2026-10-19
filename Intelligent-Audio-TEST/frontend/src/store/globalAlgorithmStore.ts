/**
 * 全局算法切换器 Store（UX设计-VUE 总表 §2.4 ②）
 *
 * 切换一次全局生效：任务/用例/音频/设备/报告/日志列表请求自动附 algorithm_type；
 * 页面内不再各自做算法筛选（页面内筛选与全局切换联动）。
 * 持久化：localStorage `iatp:algorithm:v1`（只存 type 值，切换器回显经 /algorithm/options 解析）。
 * 按路由显隐：/reports 与 /rankings 不渲染右上角切换器（页内算法卡片网格），
 * /dashboard 工作台两者都要——显隐判定由布局组件按 route.path 处理，本 store 只管状态。
 *
 * INT-803 集成：INT-737 useMergedTestFlow 按 B03 契约读 `algorithmType`（null=全部），
 * 本 store 以 computed 别名暴露同一语义（selectedType 空串 ⇄ algorithmType null）。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { algorithmPort } from '../composables/algorithm/algorithmPort'
import type { AlgorithmOption } from '../domain/model/algorithm'

const ALGORITHM_STORAGE_KEY = 'iatp:algorithm:v1'

export const useGlobalAlgorithmStore = defineStore('globalAlgorithm', () => {
  const selectedType = ref<string>('')
  const algorithmList = ref<AlgorithmOption[]>([])
  const loaded = ref(false)

  /** 初始化：读取 localStorage 存量选中值（仅首次） */
  function init() {
    if (loaded.value) return
    loaded.value = true
    try {
      const saved = localStorage.getItem(ALGORITHM_STORAGE_KEY)
      if (saved) selectedType.value = saved
    } catch {
      // localStorage 不可用时忽略，保持未选中
    }
  }

  /** 拉取算法下拉（/algorithm/options，仅在线） */
  async function loadAlgorithms() {
    try {
      const result = await algorithmPort.getOptions()
      algorithmList.value = result?.algorithms ?? []
    } catch {
      algorithmList.value = []
    }
  }

  /** 切换全局算法（type=null 清空） */
  function setAlgorithm(type: string | null) {
    selectedType.value = type || ''
    try {
      if (type) {
        localStorage.setItem(ALGORITHM_STORAGE_KEY, type)
      } else {
        localStorage.removeItem(ALGORITHM_STORAGE_KEY)
      }
    } catch {
      // 忽略持久化失败
    }
  }

  /** 清空全局算法（列表恢复全部；INT-737 /start-test 流程用） */
  function clear() {
    setAlgorithm(null)
  }

  /** 选中算法展示名（未选中返回空串，调用方渲染「全部算法」） */
  const selectedName = computed(() => {
    if (!selectedType.value) return ''
    const found = algorithmList.value.find(a => a.value === selectedType.value)
    return found?.name || selectedType.value
  })

  /** B03 契约别名（INT-737 /start-test 合并流程读）：null = 未选择/全部 */
  const algorithmType = computed<string | null>(() => selectedType.value || null)

  return {
    selectedType,
    algorithmList,
    loaded,
    selectedName,
    algorithmType,
    init,
    loadAlgorithms,
    setAlgorithm,
    clear,
  }
})
