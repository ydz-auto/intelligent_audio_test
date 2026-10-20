<template>
  <div class="settings-form-page">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <i class="fas fa-users"></i>
          用户管理
        </h2>
        <p class="page-description">管理系统用户账号、角色与附加权限</p>
      </div>
      <div class="header-right">
        <button class="btn btn-primary" @click="openCreate">
          <i class="fas fa-plus btn-icon"></i>新建用户
        </button>
      </div>
    </div>

    <p v-if="error" class="error-msg">{{ error }}</p>
    <p v-if="notice" class="success-msg">{{ notice }}</p>

    <!-- 筛选工具条 -->
    <div class="filter-bar">
      <div class="search-box">
        <i class="fas fa-search search-icon"></i>
        <input type="text" class="search-input" placeholder="搜索用户名或邮箱" v-model="query.keyword" @input="handleSearch" />
      </div>
      <select class="form-input" v-model="query.status" @change="handleFilter">
        <option value="">全部状态</option>
        <option value="active">正常</option>
        <option value="inactive">停用</option>
        <option value="locked">锁定</option>
      </select>
      <select class="form-input" v-model="query.role_id" @change="handleFilter">
        <option :value="0">全部角色</option>
        <option v-for="role in roles" :key="role.id" :value="role.id">{{ role.name }}</option>
      </select>
    </div>

    <div class="card">
      <div class="card-body">
        <div class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>用户名</th>
                <th>邮箱</th>
                <th>角色</th>
                <th>状态</th>
                <th>生效权限数</th>
                <th>注册时间</th>
                <th class="action-col">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="7" class="empty-row"><i class="fas fa-spinner fa-spin"></i> 加载中...</td>
              </tr>
              <tr v-else-if="!users.length">
                <td colspan="7" class="empty-row">暂无用户</td>
              </tr>
              <tr v-else v-for="user in users" :key="user.id">
                <td class="core-col">{{ user.username }}</td>
                <td class="secondary-col">{{ user.email || '-' }}</td>
                <td class="secondary-col">
                  <span v-if="user.roleName" class="status-tag">{{ user.roleName }}</span>
                  <span v-else class="text-muted">-</span>
                </td>
                <td class="secondary-col">
                  <span class="status-badge" :class="statusClass(user.status)">
                    {{ statusLabel(user.status) }}
                  </span>
                </td>
                <td class="secondary-col mono">{{ user.permissions?.length ?? 0 }}</td>
                <td class="secondary-col">{{ (user.createdAt || '').slice(0, 10) }}</td>
                <td class="core-col action-col">
                  <div class="table-actions">
                    <button class="btn btn-text btn-sm" @click="openEdit(user)">
                      <i class="fas fa-edit btn-icon"></i>编辑
                    </button>
                    <button class="btn btn-text btn-sm" @click="openPermissions(user)">
                      <i class="fas fa-key btn-icon"></i>附加权限
                    </button>
                    <button class="btn btn-text btn-sm btn-danger" @click="confirmDelete(user)">
                      <i class="fas fa-trash btn-icon"></i>删除
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="card-footer" v-if="total > pageSize">
        <PaginationComponent
          :current-page="page"
          :page-size="pageSize"
          :total-items="total"
          @prev-page="page = Math.max(1, page - 1); load()"
          @next-page="page++; load()"
          @go-to-page="page = $event; load()"
          @page-size-change="pageSize = $event; page = 1; load()"
        />
      </div>
    </div>

    <!-- 新建/编辑用户 -->
    <BasicModal :visible="formVisible" :title="editingId ? '编辑用户' : '新建用户'" :width="'560px'"
      :show-footer="false" @close="closeForm" @cancel="closeForm">
      <div class="user-form">
        <div class="form-row">
          <div class="form-group">
            <label>用户名 <span class="required">*</span></label>
            <input type="text" class="form-input" v-model="form.username" :disabled="!!editingId" placeholder="登录名" />
            <p v-if="editingId" class="field-hint">用户名创建后不可修改</p>
          </div>
          <div class="form-group">
            <label>邮箱</label>
            <input type="text" class="form-input" v-model="form.email" placeholder="user@example.com" />
          </div>
          <div class="form-group">
            <label>密码 {{ editingId ? '（留空不修改）' : '*' }}</label>
            <input type="password" class="form-input" v-model="form.password" placeholder="至少 6 位" />
          </div>
          <div class="form-group">
            <label>角色</label>
            <select class="form-input" v-model="form.role_id">
              <option v-for="role in roles" :key="role.id" :value="role.id">{{ role.name }}</option>
            </select>
          </div>
          <div class="form-group">
            <label>状态</label>
            <select class="form-input" v-model="form.status">
              <option value="active">正常</option>
              <option value="inactive">停用</option>
              <option value="locked">锁定</option>
            </select>
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

    <!-- 附加权限 -->
    <BasicModal :visible="permVisible" title="附加权限" :width="'640px'"
      :show-footer="false" @close="permVisible = false" @cancel="permVisible = false">
      <div class="perm-panel">
        <p class="field-hint">在角色基线权限基础上追加/收回该用户的额外权限（角色权限本身不受影响）</p>
        <div class="perm-groups">
          <div v-for="(group, module) in groupedPermissions" :key="module" class="perm-group">
            <div class="perm-group-header">{{ module || '未分组' }}</div>
            <div class="perm-options">
              <label v-for="perm in group" :key="perm.code" class="perm-option">
                <input type="checkbox" :value="perm.code" v-model="permSelected" />
                <span class="perm-code mono">{{ perm.code }}</span>
                <span v-if="perm.description" class="perm-desc">{{ perm.description }}</span>
              </label>
            </div>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" :disabled="permSaving" @click="savePermissions">
            <i class="fas fa-save btn-icon"></i>{{ permSaving ? '保存中...' : '保存' }}
          </button>
          <button class="btn btn-secondary" @click="permVisible = false">取消</button>
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
import PaginationComponent from '@/components/common/data/PaginationComponent.vue'
import BasicModal from '@/components/common/modal/BasicModal.vue'
import { usersPort } from '@/composables/system/usersPort'
import { rolesPort } from '@/composables/system/rolesPort'
import { useModalControl } from '@/composables/modal/useModal'
import { MODAL_TYPES } from '@/composables/modal/constants'
import type { SystemUser, SystemRole, PermissionItem } from '@/domain'

const modalControl = useModalControl()

const users = ref<SystemUser[]>([])
const roles = ref<SystemRole[]>([])
const permissions = ref<PermissionItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const saving = ref(false)
const permSaving = ref(false)
const error = ref('')
const notice = ref('')

const query = reactive<{ keyword: string; status: string; role_id: number }>({
  keyword: '',
  status: '',
  role_id: 0,
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await usersPort.getAll({
      page: page.value,
      page_size: pageSize.value,
      keyword: query.keyword || undefined,
      status: query.status || undefined,
      role_id: query.role_id || undefined,
    })
    users.value = result.items
    total.value = result.total
  } catch (e: any) {
    error.value = e?.detail || e?.message || '加载用户列表失败'
  } finally {
    loading.value = false
  }
}

async function loadMeta() {
  try {
    const roleList = await rolesPort.getAll()
    roles.value = roleList.roles
  } catch {
    roles.value = []
  }
  try {
    const permList = await rolesPort.getPermissions()
    permissions.value = permList.permissions
  } catch {
    permissions.value = []
  }
}

function handleSearch() {
  page.value = 1
  load()
}

function handleFilter() {
  page.value = 1
  load()
}

function statusLabel(status?: string): string {
  if (status === 'active') return '正常'
  if (status === 'inactive') return '停用'
  if (status === 'locked') return '锁定'
  return status || '正常'
}

function statusClass(status?: string): string {
  if (status === 'inactive') return 'inactive'
  if (status === 'locked') return 'warning'
  return 'active'
}

// —— 新建 / 编辑 ——
const formVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  username: '',
  email: '',
  password: '',
  role_id: 0 as number | undefined,
  status: 'active',
})

function openCreate() {
  editingId.value = null
  Object.assign(form, { username: '', email: '', password: '', role_id: undefined, status: 'active' })
  error.value = ''
  formVisible.value = true
}

function openEdit(user: SystemUser) {
  editingId.value = user.id
  Object.assign(form, {
    username: user.username,
    email: user.email || '',
    password: '',
    role_id: user.roleId ?? undefined,
    status: user.status || 'active',
  })
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
  if (!form.username) {
    error.value = '用户名必填'
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await usersPort.update(editingId.value, {
        email: form.email || undefined,
        status: form.status,
        password: form.password || undefined,
      })
      if (form.role_id && form.role_id !== undefined) {
        await usersPort.assignRole(editingId.value, form.role_id)
      }
      notice.value = '用户已更新'
    } else {
      await usersPort.create({
        username: form.username,
        email: form.email || undefined,
        password: form.password || undefined,
        role_id: form.role_id || undefined,
      })
      notice.value = '用户已创建'
    }
    closeForm()
    await load()
  } catch (e: any) {
    error.value = e?.detail || e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

// —— 删除 ——
async function confirmDelete(user: SystemUser) {
  try {
    await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认删除用户',
      content: `将删除用户「${user.username}」，该操作不可恢复。`,
      confirmText: '删除',
      cancelText: '取消',
      danger: true,
    })
  } catch {
    return
  }
  try {
    await usersPort.remove(user.id)
    notice.value = '用户已删除'
    await load()
  } catch (e: any) {
    error.value = e?.detail || e?.message || '删除失败'
  }
}

// —— 附加权限 ——
const permVisible = ref(false)
const permUser = ref<SystemUser | null>(null)
const permSelected = ref<string[]>([])

const groupedPermissions = computed(() => {
  const groups: Record<string, PermissionItem[]> = {}
  for (const p of permissions.value) {
    const module = p.module || '其他'
    if (!groups[module]) groups[module] = []
    groups[module].push(p)
  }
  return groups
})

async function openPermissions(user: SystemUser) {
  permUser.value = user
  permSelected.value = []
  error.value = ''
  permVisible.value = true
  // 基线用用户详情 overrides（granted 明细），而非列表行生效权限（会混入角色基线，INT-743 P2-2）
  try {
    const detail = await usersPort.getDetail(user.id)
    permUser.value = detail
    permSelected.value = [...(detail.extraPermissions ?? [])]
  } catch (e: any) {
    // 详情拉取失败：回退列表行基线并提示，页面仍可编辑
    permSelected.value = [...(user.permissions ?? [])]
    error.value = e?.detail || e?.message || '加载用户权限明细失败'
  }
}

async function savePermissions() {
  if (!permUser.value) return
  permSaving.value = true
  error.value = ''
  notice.value = ''
  try {
    // 差量同步（对齐 React grantPermissions）：新增逐码 POST 授予，移除按权限点 ID DELETE 撤销
    const current = new Set(permUser.value.extraPermissions ?? [])
    const next = new Set(permSelected.value)
    const toGrant = [...next].filter(p => !current.has(p) && p !== '*')
    const toRevoke = [...current].filter(p => !next.has(p) && p !== '*')
    const idByCode = new Map<string, number>()
    for (const p of permissions.value) {
      if (p.id != null) idByCode.set(p.code, p.id)
    }
    for (const code of toGrant) {
      await usersPort.grantPermission(permUser.value.id, code)
    }
    for (const code of toRevoke) {
      const permissionId = idByCode.get(code)
      if (permissionId != null) {
        await usersPort.revokePermission(permUser.value.id, permissionId)
      }
    }
    const total = toGrant.length + toRevoke.length
    notice.value = total
      ? `已同步 ${total} 项附加权限（授予 ${toGrant.length} / 收回 ${toRevoke.length}）`
      : '附加权限无变化'
    permVisible.value = false
    await load()
  } catch (e: any) {
    error.value = e?.detail || e?.message || '保存权限失败'
  } finally {
    permSaving.value = false
  }
}

onMounted(() => {
  load()
  loadMeta()
})
</script>

<style scoped>
.filter-bar {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

.filter-bar .search-box {
  flex: 1;
}

.filter-bar .form-input {
  width: 160px;
}

.user-form .form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-md);
}

.field-hint {
  font-size: 12px;
  color: var(--text-secondary);
  margin: var(--spacing-xs) 0 0;
}

.form-actions {
  display: flex;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-lg);
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

.perm-desc {
  color: var(--text-secondary);
  font-size: 12px;
}

.mono {
  font-family: var(--font-mono, monospace);
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
</style>
