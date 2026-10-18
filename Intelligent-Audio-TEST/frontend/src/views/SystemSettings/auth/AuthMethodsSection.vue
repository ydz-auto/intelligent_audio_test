<template>
  <SettingsFormPage
    title="认证方式"
    icon="fas fa-shield-alt"
    description="配置登录与注册相关开关"
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
    key: 'auth.password_login',
    label: '密码登录',
    type: 'switch',
    hint: '允许用户使用账号密码登录',
    toValue: boolVal('auth.password_login'),
  },
  {
    key: 'auth.registration',
    label: '注册开关',
    type: 'switch',
    hint: '允许新用户自助注册',
    toValue: boolVal('auth.registration'),
  },
  {
    key: 'auth.email_verification',
    label: '邮箱验证',
    type: 'switch',
    hint: '注册需邮箱验证码',
    toValue: boolVal('auth.email_verification'),
  },
]
</script>
