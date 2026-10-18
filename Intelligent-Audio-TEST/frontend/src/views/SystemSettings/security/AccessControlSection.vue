<template>
  <SettingsFormPage
    title="访问控制"
    icon="fas fa-shield-halved"
    description="安全设置预留壳，随后端能力补齐"
    :fields="fields"
  />
</template>

<script setup lang="ts">
import SettingsFormPage, { type SettingsFormField } from '../SettingsFormPage.vue'
import type { SystemOptions } from '@/domain'

const boolVal = (key: string) => (o: SystemOptions) => {
  const v = o[key]
  if (v === undefined || v === null) return false
  if (typeof v === 'boolean') return v
  return v === 'true' || v === '1'
}

const fields: SettingsFormField[] = [
  {
    key: 'security.rate_limit',
    label: '接口速率限制',
    type: 'switch',
    hint: '启用后按用户与接口限制调用频率',
    toValue: boolVal('security.rate_limit'),
  },
]
</script>
