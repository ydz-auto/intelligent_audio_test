<template>
  <SettingsFormPage
    title="导航模块"
    icon="fas fa-compass"
    description="配置站内导航模块的显示开关"
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
    key: 'site.navigation.show_breadcrumb',
    label: '面包屑导航',
    type: 'switch',
    hint: '页面顶部显示当前所在位置',
    toValue: boolVal('site.navigation.show_breadcrumb'),
  },
  {
    key: 'site.navigation.show_algorithm_switcher',
    label: '全局算法切换器',
    type: 'switch',
    hint: '导航栏右上角显示全局算法切换入口',
    toValue: boolVal('site.navigation.show_algorithm_switcher'),
  },
]
</script>
