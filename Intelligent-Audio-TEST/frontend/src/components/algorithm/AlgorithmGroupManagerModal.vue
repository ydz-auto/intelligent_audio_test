<template>
  <BasicModal
    :visible="visible"
    title="算法分组管理"
    :width="'720px'"
    :show-footer="false"
    @close="handleClose"
    @cancel="handleClose"
  >
    <div class="group-manager">
      <div class="group-toolbar">
        <span class="group-count">共 {{ groups.length }} 个分组</span>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="fas fa-plus btn-icon"></i>新建分组
        </button>
      </div>

      <p v-if="error" class="error-msg">{{ error }}</p>
      <p v-if="notice" class="success-msg">{{ notice }}</p>

      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th>分组名称</th>
              <th>描述</th>
              <th>排序</th>
              <th>算法数</th>
              <th class="action-col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="5" class="empty-row"><i class="fas fa-spinner fa-spin"></i> 加载中...</td>
            </tr>
            <tr v-else-if="!groups.length">
              <td colspan="5" class="empty-row">暂无分组</td>
            </tr>
            <tr v-else v-for="group in groups" :key="group.id">
              <td class="core-col">{{ group.name }}</td>
              <td class="secondary-col">{{ group.description || '-' }}</td>
              <td class="secondary-col mono">{{ group.displayOrder }}</td>
              <td class="secondary-col mono">{{ group.algorithmCount ?? 0 }}</td>
              <td class="core-col action-col">
                <div class="table-actions">
                  <button class="btn btn-text btn-sm" @click="openEdit(group)">
                    <i class="fas fa-edit btn-icon"></i>编辑
                  </button>
                  <button class="btn btn-text btn-sm btn-danger" @click="confirmDelete(group)">
                    <i class="fas fa-trash btn-icon"></i>删除
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 新建/编辑分组表单 -->
      <div v-if="formVisible" class="group-form">
        <div class="form-row">
          <div class="form-group">
            <label>分组名称 <span class="required">*</span></label>
            <input type="text" class="form-input" v-model="form.name" placeholder="如：语音识别" />
          </div>
          <div class="form-group">
            <label>排序</label>
            <input type="number" class="form-input" v-model.number="form.displayOrder" min="0" />
          </div>
          <div class="form-group">
            <label>图标（可选）</label>
            <input type="text" class="form-input" v-model="form.icon" placeholder="Font Awesome class" />
          </div>
          <div class="form-group full-width">
            <label>描述</label>
            <textarea class="form-input" v-model="form.description" rows="2"></textarea>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary btn-sm" :disabled="saving" @click="save">
            <i class="fas fa-save btn-icon"></i>{{ saving ? '保存中...' : '保存' }}
          </button>
          <button class="btn btn-secondary btn-sm" @click="closeForm">取消</button>
        </div>
      </div>
    </div>
  </BasicModal>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { onMounted, reactive, ref, watch } from 'vue'
import BasicModal from '../common/modal/BasicModal.vue'
import { algorithmPort } from '../../composables/algorithm/algorithmPort'
import { useModalControl } from '../../composables/modal/useModal'
import { MODAL_TYPES } from '../../composables/modal/constants'
import type { AlgorithmGroup } from '@/domain'

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', visible: boolean): void
  (e: 'success'): void
}>()

const modalControl = useModalControl()
const groups = ref<AlgorithmGroup[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')

const formVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  name: '',
  description: '',
  icon: '',
  displayOrder: 0,
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await algorithmPort.getGroups()
    groups.value = (result?.data ?? []) as AlgorithmGroup[]
  } catch (e: any) {
    error.value = e?.detail || e?.message || '加载分组失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', description: '', icon: '', displayOrder: nextOrder() })
  error.value = ''
  formVisible.value = true
}

function openEdit(group: AlgorithmGroup) {
  editingId.value = group.id
  Object.assign(form, {
    name: group.name,
    description: group.description || '',
    icon: group.icon || '',
    displayOrder: group.displayOrder,
  })
  error.value = ''
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
  editingId.value = null
}

function nextOrder(): number {
  return groups.value.reduce((max, g) => Math.max(max, g.displayOrder ?? 0), 0) + 1
}

async function save() {
  error.value = ''
  notice.value = ''
  if (!form.name) {
    error.value = '分组名称必填'
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await algorithmPort.updateGroup(editingId.value, {
        name: form.name,
        description: form.description,
        icon: form.icon,
        displayOrder: form.displayOrder,
      })
      notice.value = '分组已更新'
    } else {
      await algorithmPort.createGroup({
        name: form.name,
        description: form.description,
        icon: form.icon,
        displayOrder: form.displayOrder,
      })
      notice.value = '分组已创建'
    }
    closeForm()
    await load()
    emit('success')
  } catch (e: any) {
    error.value = e?.detail || e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function confirmDelete(group: AlgorithmGroup) {
  error.value = ''
  const content = (group.algorithmCount ?? 0) > 0
    ? `分组「${group.name}」包含 ${group.algorithmCount} 个算法。删除分组不会删除算法（算法将变为未分组），确定删除吗？`
    : `确定要删除分组「${group.name}」吗？`
  let confirmed: unknown = null
  try {
    confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认删除分组',
      content,
      confirmText: '删除',
      cancelText: '取消',
      danger: true,
    })
  } catch {
    return // 异常路径兜底：视为取消
  }
  if (!confirmed) return // 用户取消
  try {
    await algorithmPort.deleteGroup(group.id)
    notice.value = '分组已删除'
    await load()
    emit('success')
  } catch (e: any) {
    error.value = e?.detail || e?.message || '删除失败'
  }
}

function handleClose() {
  emit('update:visible', false)
}

watch(() => props.visible, (v) => {
  if (v) load()
})

onMounted(() => {
  if (props.visible) load()
})
</script>

<style scoped>
.group-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-md);
}

.group-count {
  font-size: 14px;
  color: var(--muted-foreground);
}

.group-form {
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--gray-light);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-md);
}

.form-group.full-width {
  grid-column: 1 / -1;
}

.form-actions {
  display: flex;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-md);
}

.error-msg {
  color: var(--destructive);
  font-size: 14px;
  margin-bottom: var(--spacing-sm);
}

.success-msg {
  color: var(--success-dark);
  font-size: 14px;
  margin-bottom: var(--spacing-sm);
}

.mono {
  font-family: var(--font-mono, monospace);
}
</style>
