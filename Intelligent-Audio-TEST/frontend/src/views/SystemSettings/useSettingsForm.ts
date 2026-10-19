/**
 * 系统设置 KV 表单共用 composable —— 站点设置/认证方式/安全/运维保留天数的读写骨架
 * 对齐 React useSettingsForm + useUpdateOption：基线 = 服务端值，只提交「脏且不同」的键。
 */
import { ref, computed, onMounted } from 'vue'
import { optionsPort } from '@/composables/system/optionsPort'
import type { SystemOptions } from '@/domain'

export interface OptionFieldDef {
  /** option KV 键（如 site.name / auth.password_login） */
  key: string
  /** 从全量 KV 中取该字段当前值（后端返回基线 ∪ 领域默认） */
  toValue: (o: SystemOptions) => string | number | boolean | undefined
  /** 类型（保存时决定原始类型回传） */
  type: 'text' | 'textarea' | 'switch' | 'number'
}

function parseValue(v: string | number | boolean, type: OptionFieldDef['type']) {
  if (type === 'number') {
    const n = Number(v)
    return Number.isFinite(n) ? n : 0
  }
  if (type === 'switch') {
    if (typeof v === 'boolean') return v
    return v === 'true' || v === '1'
  }
  return typeof v === 'string' ? v : String(v ?? '')
}

function looseEquals(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (typeof a === 'number' || typeof b === 'number') return Number(a) === Number(b)
  if (typeof a === 'boolean' || typeof b === 'boolean') return !!a === !!b
  return String(a ?? '') === String(b ?? '')
}

export function useOptionForm(fields: OptionFieldDef[]) {
  const values = ref<Record<string, string | number | boolean>>({})
  const original = ref<Record<string, string | number | boolean>>({})
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')
  const notice = ref('')

  const dirty = computed(() =>
    fields.some(f => !looseEquals(values.value[f.key], original.value[f.key]))
  )

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const options = await optionsPort.getAll()
      const next: Record<string, string | number | boolean> = {}
      for (const f of fields) {
        next[f.key] = parseValue(f.toValue(options) ?? '', f.type)
      }
      values.value = next
      original.value = { ...next }
    } catch (e: any) {
      error.value = e?.detail || e?.message || '加载设置失败'
    } finally {
      loading.value = false
    }
  }

  async function save() {
    error.value = ''
    notice.value = ''
    const changed = fields.filter(
      f => !looseEquals(values.value[f.key], original.value[f.key])
    )
    if (!changed.length) {
      notice.value = '没有需要保存的更改'
      return
    }
    saving.value = true
    try {
      for (const f of changed) {
        await optionsPort.update(f.key, values.value[f.key])
      }
      notice.value = '设置已更新'
      await load()
    } catch (e: any) {
      error.value = e?.detail || e?.message || '保存失败'
    } finally {
      saving.value = false
    }
  }

  function reset() {
    values.value = { ...original.value }
    notice.value = '表单已重置为已保存的值'
    error.value = ''
  }

  onMounted(load)

  return {
    values,
    loading,
    saving,
    dirty,
    error,
    notice,
    load,
    save,
    reset,
  }
}
