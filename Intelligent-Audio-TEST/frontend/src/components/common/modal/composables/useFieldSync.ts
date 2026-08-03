import { ref, watch, nextTick } from 'vue'

/**
 * 字段联动 composable
 * 负责 parentDimensionId 联动和 requiredInputs ↔ apiSettings 双向同步
 */
export function useFieldSync(props: any, formValues: any) {
  const syncing = ref(false) // 防止 apiSettings ↔ requiredInputs 双向联动死循环

  const setupParentDimensionSync = () => {
    watch(() => formValues.value.parentDimensionId, (newParentId) => {
      if (newParentId && props.fields) {
        const parentField = props.fields.find((f: any) => f.key === 'parentDimensionId')
        if (parentField && parentField.options) {
          const parentOption = parentField.options.find((opt: any) => opt.value === newParentId)
          if (parentOption) {
            if (!formValues.value.taskTypeCode && formValues.value.dimensionType === 'sub') {
              if (parentOption.taskTypeCode) {
                formValues.value.taskTypeCode = parentOption.taskTypeCode
              }
            }
            if (formValues.value.dimensionType === 'sub') {
              if (parentOption.apiSettings !== undefined && !formValues.value.apiSettings) {
                formValues.value.apiSettings = parentOption.apiSettings
              }
              if (parentOption.requiredInputs !== undefined && !formValues.value.requiredInputs) {
                formValues.value.requiredInputs = parentOption.requiredInputs
              }
            }
          }
        }
      }
    })
  }

  // 联动：requiredInputs 变化时，同步 apiSettings.body_template.rounds[0] 的 key（值用 {{key}} 占位符）
  const setupRequiredInputsSync = () => {
    watch(() => formValues.value.requiredInputs, (newInputs) => {
      if (syncing.value) return
      if (!Array.isArray(newInputs) || !formValues.value.apiSettings) return
      const apiSettings = formValues.value.apiSettings
      if (!apiSettings || typeof apiSettings !== 'object') return
      if (!apiSettings.body_template || typeof apiSettings.body_template !== 'object') {
        apiSettings.body_template = {}
      }
      const bodyTpl = apiSettings.body_template
      if (!bodyTpl.rounds) bodyTpl.rounds = [{}]
      if (!bodyTpl.rounds[0]) bodyTpl.rounds[0] = {}
      const roundTpl = bodyTpl.rounds[0]

      const inputKeys = new Set(newInputs.map((i: any) => i && i.param_code).filter((k: any) => k))

      // 新增缺失的 key（值用 {{key}} 占位符）
      newInputs.forEach((input: any) => {
        const key = input && input.param_code
        if (key && !(key in roundTpl)) {
          roundTpl[key] = `{{${key}}}`
        }
      })

      // 删除已不存在的参数 key（只删值是 {{xxx}} 占位符的，保留用户手写的非参数字段）
      Object.keys(roundTpl).forEach(key => {
        const val = roundTpl[key]
        if (typeof val === 'string' && val.match(/^{{(.+)}}$/) && !inputKeys.has(key)) {
          delete roundTpl[key]
        }
      })

      // 触发 APISettingsEditor 重新渲染（替换对象引用）
      syncing.value = true
      formValues.value.apiSettings = { ...apiSettings, body_template: { ...bodyTpl, rounds: [{ ...roundTpl }] } }
      nextTick(() => { syncing.value = false })
    }, { deep: true })
  }

  // 联动：apiSettings.body_template.rounds[0] 的 key 变化时，同步 requiredInputs 的参数键名
  const setupApiSettingsSync = () => {
    watch(() => {
      const apiSettings = formValues.value.apiSettings
      const round0 = apiSettings && apiSettings.body_template && apiSettings.body_template.rounds && apiSettings.body_template.rounds[0]
      if (!round0) return ''
      // 用 keys 签名捕获 key 增删/改名（值变化不触发）
      return Object.keys(round0).join('\n')
    }, (sig) => {
      if (syncing.value) return
      const inputs = formValues.value.requiredInputs
      if (!Array.isArray(inputs)) return

      const apiSettings = formValues.value.apiSettings
      const roundTpl = apiSettings?.body_template?.rounds?.[0] || {}

      // rounds[0] 的所有 key 都是参数键名（保留 round 中的顺序）
      const expectedKeys = Object.keys(roundTpl)

      const existingKeys = new Set(inputs.map((i: any) => i && i.param_code).filter(Boolean))
      let changed = false
      const newInputs = []

      // 按 expectedKeys 顺序映射：已有则保留，否则新增
      expectedKeys.forEach(key => {
        const existing = inputs.find((i: any) => i && i.param_code === key)
        if (existing) {
          newInputs.push(existing)
        } else {
          newInputs.push({
            param_code: key,
            param_name: '',
            field_type: 'text',
            required: true,
            default_value: '',
            help_text: ''
          })
          changed = true
        }
        existingKeys.delete(key)
      })

      // 原有但不在 expectedKeys 里的（用户在 JSON 里删/改了 key）→ 删除
      if (existingKeys.size > 0) {
        changed = true
      }

      if (changed || newInputs.length !== inputs.length) {
        syncing.value = true
        formValues.value.requiredInputs = newInputs
        nextTick(() => { syncing.value = false })
      }
    })
  }

  // props.mode 和 props.formData 的监听
  const setupPropsWatchers = (scanPlaybackDevices: any, scanTestDeviceSerials: any) => {
    watch(() => props.mode, async (newMode) => {
      if (newMode === 'create') {
        await scanPlaybackDevices()
        await scanTestDeviceSerials()
      }
    })

    watch(() => props.formData, (newFormData) => {
      if (newFormData && typeof newFormData === 'object') {
        const fieldKeys = Object.keys(newFormData)
        fieldKeys.forEach(key => {
          if (formValues.value[key] === undefined) {
            formValues.value[key] = newFormData[key]
          }
        })
      }
    }, { deep: true })
  }

  const setupAllWatchers = (scanPlaybackDevices: any, scanTestDeviceSerials: any) => {
    setupParentDimensionSync()
    setupRequiredInputsSync()
    setupApiSettingsSync()
    setupPropsWatchers(scanPlaybackDevices, scanTestDeviceSerials)
  }

  return {
    syncing,
    setupAllWatchers
  }
}
