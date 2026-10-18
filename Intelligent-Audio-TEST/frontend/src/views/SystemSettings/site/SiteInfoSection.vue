<template>
  <SettingsFormPage
    title="站点信息"
    icon="fas fa-info-circle"
    description="配置站内各处显示的名称、Logo 与页脚"
    :fields="fields"
  />
</template>

<script setup lang="ts">
import SettingsFormPage, { type SettingsFormField } from '../SettingsFormPage.vue'
import type { SystemOptions } from '@/domain'

const str = (key: string) => (o: SystemOptions) =>
  typeof o[key] === 'string' ? String(o[key]) : ''

const fields: SettingsFormField[] = [
  {
    key: 'site.name',
    label: '站点名称',
    type: 'text',
    required: true,
    placeholder: '如：智能语音测试平台',
    hint: '站内各处显示的名称',
    toValue: str('site.name'),
  },
  {
    key: 'site.logo',
    label: 'Logo 地址',
    type: 'text',
    placeholder: 'https://example.com/logo.png',
    hint: 'Logo 图片 URL，选填',
    toValue: str('site.logo'),
  },
  {
    key: 'site.support_email',
    label: '支持邮箱',
    type: 'text',
    placeholder: 'support@example.com',
    hint: '对外展示的技术支持邮箱',
    toValue: str('site.support_email'),
  },
  {
    key: 'site.footer',
    label: '页脚内容',
    type: 'text',
    placeholder: '如：© 2026 智能语音测试平台',
    hint: '公共页页脚展示的版权/说明文案',
    toValue: str('site.footer'),
  },
]
</script>
