<template>
  <div class="settings-form-page">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <i class="fas fa-user-shield"></i>
          角色权限管理
        </h2>
        <p class="page-description">角色权限变更后即时生效，用户归属角色决定其基线权限范围</p>
      </div>
      <div class="header-right">
        <button class="btn btn-primary" @click="openCreate">
          <i class="fas fa-plus btn-icon"></i>新建角色
        </button>
      </div>
    </div>

    <p v-if="error && !loadFailed" class="error-msg">{{ error }}</p>
    <p v-if="notice" class="success-msg">{{ notice }}</p>

    <!-- INT-900：后端 500 / 非 JSON 响应时友好降级（不直出 client 层原始 JS 错误串），固定文案 + 重试 -->
    <div v-if="loadFailed" class="load-error-state">
      <i class="fas fa-exclamation-triangle load-error-icon" aria-hidden="true"></i>
      <h4 class="load-error-title">加载失败</h4>
      <p class="load-error-desc">{{ SERVER_UNAVAILABLE_COPY }}</p>
      <button type="button" class="btn btn-primary" @click="load">
        <i class="fas fa-sync-alt btn-icon"></i>重试
      </button>
    </div>

    <template v-else>
    <div class="card">
      <div class="card-body">
        <div class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>角色名称</th>
                <th>描述</th>
                <th>类型</th>
                <th>权限数</th>
                <th>用户数</th>
                <th class="action-col">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="6" class="empty-row"><i class="fas fa-spinner fa-spin"></i> 加载中...</td>
              </tr>
              <tr v-else-if="!roles.length">
                <td colspan="6" class="empty-row">暂无角色</td>
              </tr>
              <tr v-else v-for="role in roles" :key="role.id">
                <td class="core-col">
                  {{ role.name }}
                  <span v-if="role.isSystem" class="status-tag">系统内置</span>
                </td>
                <td class="secondary-col">{{ role.description || '-' }}</td>
                <td class="secondary-col">
                  <span class="status-tag" :class="role.isSystem ? 'system' : 'custom'">
                    {{ role.isSystem ? '系统内置' : '自定义' }}
                  </span>
                </td>
                <td class="secondary-col mono">{{ role.permissions?.length ?? 0 }}</td>
                <td class="secondary-col mono">{{ role.userCount ?? 0 }}</td>
                <td class="core-col action-col">
                  <div class="table-actions">
                    <button class="btn btn-text btn-sm" @click="openEdit(role)">
                      <i class="fas fa-edit btn-icon"></i>编辑
                    </button>
                    <button
                      class="btn btn-text btn-sm btn-danger"
                      :disabled="role.isSystem"
                      @click="confirmDelete(role)"
                    >
                      <i class="fas fa-trash btn-icon"></i>删除
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    </template>

    <!-- 新建/编辑角色 -->
    <BasicModal :visible="formVisible" :title="editingId ? '编辑角色' : '新建角色'" :width="'720px'"
      :show-footer="false" @close="closeForm" @cancel="closeForm">
      <div class="role-form">
        <div class="role-basic">
          <div class="form-group">
            <label>角色名称 <span class="required">*</span></label>
            <input type="text" class="form-input" v-model="form.name" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <input type="text" class="form-input" v-model="form.description" placeholder="角色职责说明" />
          </div>
        </div>

        <div class="perm-block">
          <div class="perm-block-header">
            <span class="perm-block-title">权限配置</span>
            <span class="perm-count">已选 {{ selectedPerms.length }} / {{ permissions.length }}</span>
          </div>
          <p class="field-hint">超级管理员持有全部权限（通配 *），不可修改</p>
          <div class="perm-groups">
            <div v-for="(group, module) in groupedPermissions" :key="module" class="perm-group">
              <div class="perm-group-header">{{ module || '未分组' }}</div>
              <div class="perm-options">
                <label
                  v-for="perm in group"
                  :key="perm.code"
                  class="perm-option"
                  :class="{ disabled: perm.code === '*' }"
                >
                  <input
                    type="checkbox"
                    :value="perm.code"
                    v-model="selectedPerms"
                    :disabled="perm.code === '*'"
                  />
                  <span class="perm-code mono">{{ perm.code }}</span>
                  <span v-if="perm.description" class="perm-desc">{{ perm.description }}</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        <div class="form-actions">
          <button class="btn btn-primary" :disabled="saving" @click="save">
            <i class="fas fa-save btn-icon"></i>{{ saving ? '保存中...' : '保存' }}
          </button>
          <button class="btn btn-secondary" @click="closeForm">取消</button>
        </div>
      </div>
    </BasicModal>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/components/form.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'
import "../../../assets/styles/tasks/task-status.css"
import { computed, onMounted, reactive, ref } from 'vue'
import BasicModal from '@/components/common/modal/BasicModal.vue'
import { rolesPort } from '@/composables/system/rolesPort'
import { useModalControl } from '@/composables/modal/useModal'
import { MODAL_TYPES } from '@/composables/modal/constants'
import { SERVER_UNAVAILABLE_COPY, isServerFailure, friendlyApiError } from '../errorState'
import type { SystemRole, PermissionItem } from '@/domain'

const modalControl = useModalControl()

const roles = ref<SystemRole[]>([])
const permissions = ref<PermissionItem[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')
const loadFailed = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  loadFailed.value = false
  try {
    const list = await rolesPort.getAll()
    roles.value = list.roles
  } catch (e: any) {
    // INT-900：后端 500 / 非 JSON 响应不直出 client 层原始 JS 错误串，走友好错误态
    loadFailed.value = isServerFailure(e)
    error.value = loadFailed.value ? '' : friendlyApiError(e, '加载角色列表失败')
  } finally {
    loading.value = false
  }
}

async function loadPermissions() {
  try {
    const list = await rolesPort.getPermissions()
    permissions.value = list.permissions
  } catch {
    permissions.value = []
  }
}

const groupedPermissions = computed(() => {
  const groups: Record<string, PermissionItem[]> = {}
  for (const p of permissions.value) {
    const module = p.module || '其他'
    if (!groups[module]) groups[module] = []
    groups[module].push(p)
  }
  return groups
})

// —— 新建 / 编辑 ——
const formVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({ name: '', description: '' })
const selectedPerms = ref<string[]>([])

function openCreate() {
  editingId.value = null
  form.name = ''
  form.description = ''
  selectedPerms.value = []
  error.value = ''
  formVisible.value = true
}

function openEdit(role: SystemRole) {
  editingId.value = role.id
  form.name = role.name
  form.description = role.description || ''
  selectedPerms.value = [...(role.permissions ?? [])]
  error.value = ''
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
  editingId.value = null
}

async function save() {
  error.value = ''
  notice.value = ''
  if (!form.name) {
    error.value = '角色名称必填'
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await rolesPort.update(editingId.value, {
        name: form.name,
        description: form.description,
      })
      await rolesPort.assignPermissions(editingId.value, selectedPerms.value)
      notice.value = '角色已更新'
    } else {
      await rolesPort.create({
        name: form.name,
        description: form.description,
        permission_codes: selectedPerms.value,
      })
      notice.value = '角色已创建'
    }
    closeForm()
    await load()
  } catch (e: any) {
    error.value = friendlyApiError(e, '保存失败')
  } finally {
    saving.value = false
  }
}

// —— 删除 ——
async function confirmDelete(role: SystemRole) {
  if (role.isSystem) {
    error.value = '系统内置角色不可删除'
    return
  }
  if ((role.userCount ?? 0) > 0) {
    error.value = '该角色仍有用户归属，请先转移用户'
    return
  }
  try {
    await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认删除角色',
      content: `将删除角色「${role.name}」，该操作不可恢复。`,
      confirmText: '删除',
      cancelText: '取消',
      danger: true,
    })
  } catch {
    return
  }
  try {
    await rolesPort.remove(role.id)
    notice.value = '角色已删除'
    await load()
  } catch (e: any) {
    error.value = friendlyApiError(e, '删除失败')
  }
}

onMounted(() => {
  load()
  loadPermissions()
})
</script>

<style scoped>
.role-basic {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.perm-block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-xs);
}

.perm-block-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
}

.perm-count {
  font-size: 13px;
  color: var(--text-secondary);
}

.field-hint {
  font-size: 12px;
  color: var(--text-secondary);
  margin: var(--spacing-xs) 0 var(--spacing-sm);
}

.perm-group {
  margin-bottom: var(--spacing-md);
}

.perm-group-header {
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground);
  margin-bottom: var(--spacing-xs);
}

.perm-options {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-xs);
}

.perm-option {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--foreground);
  cursor: pointer;
}

.perm-option.disabled {
  opacity: 0.6;
}

.perm-desc {
  color: var(--text-secondary);
  font-size: 12px;
}

.mono {
  font-family: var(--font-mono, monospace);
}

.form-actions {
  display: flex;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-lg);
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

/* INT-900：后端 500 友好错误态（固定文案 + 重试按钮，不直出原始 JS 错误串） */
.load-error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xl);
  border: 1px dashed var(--border);
  border-radius: var(--radius-lg);
  background: var(--card);
  text-align: center;
}

.load-error-icon {
  font-size: 32px;
  color: var(--destructive);
}

.load-error-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
}

.load-error-desc {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

</style>
