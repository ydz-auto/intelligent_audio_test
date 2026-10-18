<template>
  <form class="edit-profile-form" novalidate @submit.prevent="handleSubmit">
    <p class="modal-desc">为账号 {{ username }} 更新个人资料</p>

    <div class="form-group">
      <label>用户名</label>
      <input type="text" :value="username" disabled />
      <p class="field-hint">用户名创建后不可修改，如需变更请联系管理员</p>
    </div>

    <div class="form-group">
      <label for="profile-email">邮箱</label>
      <input
        id="profile-email"
        v-model="form.email"
        type="email"
        placeholder="请输入邮箱"
        autocomplete="email"
      />
      <p class="field-hint">邮箱展示功能开发中（待后端立项），保存后由平台管理员确认生效</p>
      <p v-if="errors.email" class="error-text">{{ errors.email }}</p>
    </div>

    <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

    <div class="form-actions">
      <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
      <button type="submit" class="btn btn-primary" :disabled="saving">
        {{ saving ? '保存中…' : '保存' }}
      </button>
    </div>
  </form>
</template>

<script setup lang="ts">
/**
 * 编辑资料对话框壳（13_个人中心 §3.4 / 总表 §3.3 F3，自我资料更新）：
 * 用户名只读（平台口径不可改）+ 邮箱编辑。
 * ⚠️ 自我资料更新端点 F3 待 FEAT——本壳不造数据兜底、不出现假成功：
 * 提交走 profileApi 桩，调用即抛「待后端立项」错误提示。
 */
import { reactive, ref } from 'vue'
import { profilePort } from '@/composables/profile/profilePort'

const props = defineProps<{
  username?: string
}>()

const emit = defineEmits<{
  (e: 'confirm', data: Record<string, unknown>): void
  (e: 'cancel'): void
}>()

const form = reactive({
  email: '',
})
const errors = reactive<Record<string, string>>({})
const errorMessage = ref('')
const saving = ref(false)

function validate(): boolean {
  const nextErrors: Record<string, string> = {}
  if (form.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
    nextErrors.email = '邮箱格式不正确'
  }
  Object.assign(errors, nextErrors)
  return Object.keys(nextErrors).length === 0
}

async function handleSubmit() {
  errorMessage.value = ''
  if (!validate() || saving.value) return
  saving.value = true
  try {
    await profilePort.updateMyProfile({ email: form.email.trim() || undefined })
    // 桩未落地前不会走到这里（updateMyProfile 抛「待后端立项」）
    emit('confirm', { email: form.email.trim() })
  } catch (e: any) {
    errorMessage.value = e?.message || '保存失败，请重试'
  } finally {
    saving.value = false
  }
}

function handleCancel() {
  emit('cancel')
}
</script>

<style scoped>
.edit-profile-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modal-desc {
  margin: 0;
  font-size: 13px;
  color: var(--muted-foreground);
}

.form-group {
  position: relative;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  font-size: 14px;
  color: var(--foreground);
}

.form-group input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control, 8px);
  font-size: 14px;
  box-sizing: border-box;
  background: var(--background);
  color: var(--foreground);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.form-group input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ring) 15%, transparent);
}

.form-group input:disabled {
  background: var(--muted);
  color: var(--muted-foreground);
  cursor: not-allowed;
}

.field-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--muted-foreground);
}

.error-text {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--destructive);
}

.error-message {
  margin: 0;
  font-size: 13px;
  color: var(--destructive);
  background: var(--destructive-light);
  border-radius: var(--radius-control, 8px);
  padding: 8px 10px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 8px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.btn {
  padding: 8px 18px;
  border-radius: var(--radius-control, 8px);
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
  font-weight: 500;
}

.btn-primary {
  background: var(--primary);
  color: var(--primary-foreground);
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--gray-light);
  color: var(--foreground);
  border: 1px solid var(--border);
}

.btn-secondary:hover {
  background: var(--muted);
}
</style>
