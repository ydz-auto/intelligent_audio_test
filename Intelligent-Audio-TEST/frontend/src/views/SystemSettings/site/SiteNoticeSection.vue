<template>
  <SettingsFormPage
    title="站点公告"
    icon="fas fa-bullhorn"
    description="维护站内公告内容，通知中心「公告」页签与登录页展示该内容"
    :fields="fields"
  />
</template>

<script setup lang="ts">
import SettingsFormPage, { type SettingsFormField } from '../SettingsFormPage.vue'
import type { SystemOptions } from '@/domain'

const fields: SettingsFormField[] = [
  {
    key: 'site.notice',
    label: '公告内容',
    type: 'textarea',
    placeholder: '例如：本周五 22:00 计划性维护，届时系统暂不可用...',
    hint: '留空表示暂无公告',
    toValue: (o: SystemOptions) => (typeof o['site.notice'] === 'string' ? String(o['site.notice']) : ''),
  },
]
</script>
