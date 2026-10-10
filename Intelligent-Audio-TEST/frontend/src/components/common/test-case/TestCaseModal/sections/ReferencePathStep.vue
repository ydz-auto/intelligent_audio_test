<template>
  <div class="rce-step" id="step-ref">
    <div class="rce-step-header">
      <i class="fas fa-file-alt rce-step-icon"></i>
      <span class="rce-step-title">参考参数</span>
      <span class="rce-tag rce-tag-gray">referenceParamsPath · 自动生成</span>
    </div>
    <div v-if="round.referenceParamsPath" class="rce-ref-info">
      <i class="fas fa-folder-open"></i>
      <span>{{ round.referenceParamsPath }}</span>
      <button
        v-if="testCaseId"
        type="button"
        class="rce-ref-btn"
        :disabled="loading"
        @click="toggleEditor"
      >
        <i class="fas" :class="editorVisible ? 'fa-chevron-up' : 'fa-pen-to-square'"></i>
        {{ editorVisible ? '收起' : '查看/编辑' }}
      </button>
    </div>
    <div v-else class="rce-ref-empty">
      <i class="fas fa-info-circle"></i>
      参考参数将在音频关联后自动生成
    </div>

    <div v-if="editorVisible" class="rce-ref-editor">
      <textarea
        v-model="refParamsText"
        class="rce-ref-textarea"
        :disabled="loading || saving"
        spellcheck="false"
      ></textarea>
      <div class="rce-ref-actions">
        <button
          type="button"
          class="rce-ref-btn rce-ref-btn-primary"
          :disabled="loading || saving"
          @click="saveRefParams"
        >
          <i class="fas fa-save"></i>
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { RoundConfigItem } from '@/domain'
import { testcasesPort } from '@/composables/testCase/testcasesPort'
import { useNotification } from '@/composables/modal/useNotification'

const props = defineProps<{
  round: RoundConfigItem
  /** 编辑态用例 ID；新增态无 ID，不启用读写 */
  testCaseId?: string | number
}>()

const notification = useNotification()

const editorVisible = ref(false)
const loading = ref(false)
const saving = ref(false)
const refParamsText = ref('')

async function toggleEditor() {
  if (editorVisible.value) {
    editorVisible.value = false
    return
  }
  editorVisible.value = true
  await loadRefParams()
}

async function loadRefParams() {
  if (!props.testCaseId) return
  loading.value = true
  try {
    const data = await testcasesPort.getRefParams(props.testCaseId, props.round.roundNumber ?? 1)
    refParamsText.value = JSON.stringify(data.referenceParams ?? {}, null, 2)
  } catch (error: any) {
    editorVisible.value = false
    notification.error('参考参数加载失败', error?.message || '参考参数加载失败')
  } finally {
    loading.value = false
  }
}

async function saveRefParams() {
  if (!props.testCaseId) return
  let parsed: unknown
  try {
    parsed = JSON.parse(refParamsText.value)
  } catch {
    notification.error('参考参数不是合法 JSON，请检查后重试')
    return
  }
  saving.value = true
  try {
    await testcasesPort.updateRefParams(props.testCaseId, props.round.roundNumber ?? 1, parsed)
    notification.success('参考参数已保存')
  } catch (error: any) {
    notification.error('参考参数保存失败', error?.message || '')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.rce-step {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--gray-light);
}
.rce-step:last-child { border-bottom: none; }

.rce-step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.rce-step-icon { font-size: 14px; color: var(--primary-color, var(--primary)); }
.rce-step-title { font-size: 14px; font-weight: 600; color: var(--text-primary, var(--foreground)); }

.rce-tag {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 500;
}
.rce-tag-gray { background: var(--muted); color: var(--color-gray-400); }

.rce-ref-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--background-secondary, var(--muted));
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary, var(--color-gray-500));
}
.rce-ref-info i { color: var(--text-light, var(--color-gray-400)); }

.rce-ref-btn {
  margin-left: auto;
  padding: 4px 10px;
  border: 1px solid var(--border-color, var(--border));
  border-radius: 6px;
  background: var(--background-primary, var(--background));
  color: var(--text-secondary, var(--color-gray-500));
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.rce-ref-btn:hover:not(:disabled) { color: var(--primary-color, var(--primary)); }
.rce-ref-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.rce-ref-btn-primary { margin-left: 0; color: var(--primary-color, var(--primary)); }

.rce-ref-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-light, var(--color-gray-400));
  font-size: 13px;
}
.rce-ref-empty i { margin-right: 4px; }

.rce-ref-editor {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rce-ref-textarea {
  width: 100%;
  min-height: 200px;
  padding: 10px;
  border: 1px solid var(--border-color, var(--border));
  border-radius: 6px;
  font-family: monospace;
  font-size: 12px;
  line-height: 1.5;
  resize: vertical;
  box-sizing: border-box;
}
.rce-ref-actions { display: flex; justify-content: flex-end; }
</style>
