<template>
  <div class="account-settings">
    <div class="page-header">
      <h2 class="page-title">
        <i class="fas fa-user-circle"></i>
        账号设置
      </h2>
      <p class="page-description">管理当前账号信息与第三方账号绑定</p>
    </div>

    <p v-if="error" class="error-msg">{{ error }}</p>
    <p v-if="notice" class="success-msg">{{ notice }}</p>

    <div class="section-card">
      <h3>账号信息</h3>
      <div class="user-info">
        <div class="info-row">
          <span class="info-label">用户名</span>
          <span>{{ authStore.username }}</span>
        </div>
        <div class="info-row" v-if="authStore.roleName">
          <span class="info-label">角色</span>
          <span>{{ authStore.roleName }}</span>
        </div>
      </div>
    </div>

    <div class="section-card">
      <h3>第三方账号绑定</h3>
      <p class="section-hint">绑定后可使用对应第三方账号直接登录本账号</p>
      <table class="binding-table">
        <thead>
          <tr>
            <th>提供方</th>
            <th>第三方账号 ID</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!bindings.length">
            <td colspan="3" class="empty-row">暂无绑定，从下方列表添加</td>
          </tr>
          <tr v-for="b in bindings" :key="b.providerId">
            <td><i v-if="b.providerIcon" :class="b.providerIcon"></i> {{ b.providerName }}</td>
            <td><code>{{ b.providerUserId }}</code></td>
            <td>
              <button class="btn btn-sm btn-danger" :disabled="unbinding" @click="unbind(b)">
                解绑
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="bindableProviders.length" class="bind-section">
        <h4>添加绑定</h4>
        <div class="bind-list">
          <button
            v-for="p in bindableProviders"
            :key="p.slug"
            type="button"
            class="bind-btn"
            :disabled="binding"
            @click="startBind(p.slug)"
          >
            <i :class="p.icon || 'fas fa-link'"></i>
            绑定 {{ p.name }}
          </button>
        </div>
      </div>
    </div>

    <!-- INT-1140：Access Token 管理（联接你的 agent） -->
    <div class="section-card" ref="tokenSectionRef">
      <h3>Access Token <span class="section-badge">联接你的 agent</span></h3>
      <p class="section-hint">
        供 skill / MCP 调用本系统能力时鉴权；明文仅创建时显示一次，库中只存哈希。
      </p>

      <p v-if="tokenError" class="error-msg">{{ tokenError }}</p>
      <p v-if="tokenNotice" class="success-msg">{{ tokenNotice }}</p>

      <!-- 创建 -->
      <div class="token-create">
        <h4>创建 Access Token</h4>
        <div class="form-row">
          <label class="token-label">名称</label>
          <input v-model="createForm.name" type="text" class="form-input" placeholder="如：Claude Code 工作台" />
        </div>
        <div class="form-row">
          <label class="token-label">有效期</label>
          <select v-model="createForm.expiryMode" class="form-input token-expiry-select">
            <option value="default">默认有效期（后端配置，默认 30 天）</option>
            <option value="never">永不过期</option>
            <option value="custom">自定义过期时间</option>
          </select>
          <input
            v-if="createForm.expiryMode === 'custom'"
            v-model="createForm.customExpiresAt"
            type="datetime-local"
            class="form-input"
          />
        </div>
        <div class="scopes-catalog">
          <div class="scopes-actions">
            <span class="section-hint">权限（scopes）：不勾选 = 继承你的全部权限；勾选 = 仅限所选业务能力</span>
            <button type="button" class="btn btn-sm" @click="toggleAllScopes">
              {{ allScopesSelected ? '清空选择' : '全选' }}
            </button>
          </div>
          <div v-for="group in scopeGroups" :key="group.key" class="scope-group">
            <h5 class="scope-group-title">{{ group.label }}</h5>
            <div class="scope-checks">
              <label v-for="s in group.scopes" :key="s.code" class="scope-check">
                <input type="checkbox" :value="s.code" v-model="createForm.scopes" />
                <span class="scope-label">{{ s.label }}</span>
                <code class="scope-code">{{ s.code }}</code>
              </label>
            </div>
          </div>
        </div>
        <button type="button" class="btn btn-primary" :disabled="creating" @click="handleCreate">
          {{ creating ? '创建中…' : '创建 Access Token' }}
        </button>
      </div>

      <!-- 创建成功：明文仅一次 -->
      <div v-if="createdToken" class="token-created">
        <h4>创建成功，请立即复制保存</h4>
        <p class="section-hint">明文仅显示这一次，关闭后无法再查看；请妥善保管（等效账号口令）。</p>
        <div class="token-plaintext-row">
          <code class="token-plaintext">{{ createdToken.token }}</code>
          <button type="button" class="btn btn-sm" @click="copyPlaintext(createdToken.token)">复制</button>
        </div>
      </div>

      <!-- 列表 -->
      <div class="token-list">
        <h4>我的 Access Token</h4>
        <table class="binding-table token-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>Key</th>
              <th>权限</th>
              <th>状态</th>
              <th>有效期</th>
              <th>最后使用</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="tokenLoading">
              <td colspan="7" class="empty-row">加载中…</td>
            </tr>
            <tr v-else-if="!tokens.length">
              <td colspan="7" class="empty-row">暂无 Access Token，从上方创建</td>
            </tr>
            <tr v-for="t in tokens" :key="t.id">
              <td class="token-name">{{ t.name }}</td>
              <td><code class="token-hint">{{ maskToken(t) }}</code></td>
              <td class="token-scopes" :title="t.scopes.join(', ')">{{ scopeSummary(t) }}</td>
              <td>
                <span class="token-status" :class="t.status">
                  {{ t.status === 'enabled' ? '启用' : '停用' }}
                </span>
              </td>
              <td>{{ formatExpiry(t.expiresAt) }}</td>
              <td class="token-muted">{{ t.lastUsedAt ? formatDate(t.lastUsedAt) : '—' }}</td>
              <td class="token-actions">
                <button type="button" class="btn btn-sm" @click="openEdit(t)">编辑</button>
                <button type="button" class="btn btn-sm" @click="toggleStatus(t)">
                  {{ t.status === 'enabled' ? '停用' : '启用' }}
                </button>
                <button type="button" class="btn btn-sm btn-danger" @click="confirmDelete(t)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 编辑 -->
      <div v-if="editingToken" class="token-edit">
        <h4>编辑 Access Token：{{ editingToken.name }}</h4>
        <div class="form-row">
          <label class="token-label">名称</label>
          <input v-model="editForm.name" type="text" class="form-input" />
        </div>
        <div class="form-row">
          <label class="token-label">有效期</label>
          <select v-model="editForm.expiryMode" class="form-input token-expiry-select">
            <option value="never">永不过期</option>
            <option value="custom">自定义过期时间</option>
          </select>
          <input
            v-if="editForm.expiryMode === 'custom'"
            v-model="editForm.customExpiresAt"
            type="datetime-local"
            class="form-input"
          />
        </div>
        <div class="scopes-catalog">
          <div class="scopes-actions">
            <span class="section-hint">权限（scopes）：不勾选 = 继承你的全部权限</span>
            <button type="button" class="btn btn-sm" @click="toggleEditAllScopes">
              {{ editAllSelected ? '清空选择' : '全选' }}
            </button>
          </div>
          <div v-for="group in scopeGroups" :key="group.key" class="scope-group">
            <h5 class="scope-group-title">{{ group.label }}</h5>
            <div class="scope-checks">
              <label v-for="s in group.scopes" :key="s.code" class="scope-check">
                <input type="checkbox" :value="s.code" v-model="editForm.scopes" />
                <span class="scope-label">{{ s.label }}</span>
                <code class="scope-code">{{ s.code }}</code>
              </label>
            </div>
          </div>
        </div>
        <div class="edit-actions">
          <button type="button" class="btn btn-primary" :disabled="updating" @click="saveEdit">
            {{ updating ? '保存中…' : '保存' }}
          </button>
          <button type="button" class="btn" @click="closeEdit">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../store/authStore'
import { authPort } from '../../composables/auth/authPort'
import { accessTokenPort } from '../../composables/auth/accessTokenPort'
import { ACCESS_TOKEN_SCOPES, ALL_ACCESS_TOKEN_SCOPE_CODES } from '../../domain/model/accessToken'
import type { AccessToken, AccessTokenCreated, AccessTokenStatus } from '../../domain/model/accessToken'
import type { OAuthBinding, OAuthProvider } from '../../domain/model/auth'
import { useModalControl } from '../../composables/modal/useModal'
import { MODAL_TYPES } from '../../composables/modal/constants'
import { formatDate } from '../../utils/utils'

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const modalControl = useModalControl()

const bindings = ref<OAuthBinding[]>([])
const providers = ref<OAuthProvider[]>([])
const error = ref('')
const notice = ref('')
const loading = ref(false)
const binding = ref(false)
const unbinding = ref(false)

// ===== Access Token（INT-1140）=====
const tokenSectionRef = ref<HTMLElement | null>(null)
const tokens = ref<AccessToken[]>([])
const tokenLoading = ref(false)
const tokenError = ref('')
const tokenNotice = ref('')
const creating = ref(false)
const updating = ref(false)
const createdToken = ref<AccessTokenCreated | null>(null)
const editingToken = ref<AccessToken | null>(null)

const createForm = reactive({
  name: '',
  expiryMode: 'default' as 'default' | 'never' | 'custom',
  customExpiresAt: '',
  scopes: [] as string[],
})

const editForm = reactive({
  name: '',
  expiryMode: 'never' as 'never' | 'custom',
  customExpiresAt: '',
  scopes: [] as string[],
})

// 已绑定列表里的 scopes 全集是否被全选
const allScopesSelected = computed(
  () => ALL_ACCESS_TOKEN_SCOPE_CODES.length > 0
    && createForm.scopes.length === ALL_ACCESS_TOKEN_SCOPE_CODES.length,
)
const editAllSelected = computed(
  () => ALL_ACCESS_TOKEN_SCOPE_CODES.length > 0
    && editForm.scopes.length === ALL_ACCESS_TOKEN_SCOPE_CODES.length,
)
const scopeGroups = ACCESS_TOKEN_SCOPES

// 已绑定的提供方不再重复给出绑定入口
const bindableProviders = computed(() => {
  const boundSlugs = new Set(bindings.value.map(b => b.providerSlug))
  return providers.value.filter(p => !boundSlugs.has(p.slug))
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    bindings.value = await authPort.listOAuthBindings()
    providers.value = await authPort.listPublicOAuthProviders()
  } catch (e: any) {
    error.value = e?.detail || e?.message || '加载绑定信息失败'
  } finally {
    loading.value = false
  }
}

function startBind(slug: string) {
  // 整页跳转：授权 → intent=bind 回调 → 携 bind_ticket 回本页
  window.location.href = authPort.getOAuthAuthorizeUrl(slug, 'bind')
}

async function completeBind(ticket: string) {
  binding.value = true
  error.value = ''
  try {
    await authPort.completeOAuthBinding(ticket)
    notice.value = '绑定成功'
    await load()
  } catch (e: any) {
    error.value = e?.detail || e?.message || '绑定失败'
  } finally {
    binding.value = false
  }
}

async function unbind(b: OAuthBinding) {
  // INT-286：解绑改 BASIC_CONFIRM（danger）模态，替换原生 window.confirm
  try {
    await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '解绑第三方账号',
      content: `确认解绑「${b.providerName}」？解绑后将无法使用该第三方账号登录。`,
      confirmText: '解绑',
      cancelText: '取消',
      danger: true,
    })
  } catch {
    return // 用户取消
  }
  unbinding.value = true
  error.value = ''
  try {
    await authPort.unbindOAuthProvider(b.providerId)
    notice.value = '解绑成功'
    await load()
  } catch (e: any) {
    error.value = e?.detail || e?.message || '解绑失败'
  } finally {
    unbinding.value = false
  }
}

// ===== Access Token 逻辑（INT-1140）=====

async function loadTokens() {
  tokenLoading.value = true
  tokenError.value = ''
  try {
    tokens.value = await accessTokenPort.list()
  } catch (e: any) {
    tokenError.value = e?.detail || e?.message || '加载 Access Token 失败'
  } finally {
    tokenLoading.value = false
  }
}

/** datetime-local（YYYY-MM-DDTHH:mm）→ 后端 ISO 字符串 */
function toExpiresPayload(mode: string, custom: string): number | string | undefined {
  if (mode === 'never') return 0
  if (mode === 'custom') {
    const v = custom.trim()
    if (!v) return undefined
    return v.length === 16 ? `${v}:00` : v
  }
  return undefined
}

/** ISO → datetime-local（YYYY-MM-DDTHH:mm）回填 */
function toDateTimeLocal(value: number | string): string {
  const d = new Date(String(value).replace('Z', ''))
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function handleCreate() {
  const name = createForm.name.trim()
  if (!name) {
    tokenError.value = '请填写 Token 名称'
    return
  }
  creating.value = true
  tokenError.value = ''
  tokenNotice.value = ''
  try {
    const result = await accessTokenPort.create({
      name,
      scopes: createForm.scopes,
      expiresAt: toExpiresPayload(createForm.expiryMode, createForm.customExpiresAt),
    })
    createdToken.value = result
    createForm.name = ''
    createForm.expiryMode = 'default'
    createForm.customExpiresAt = ''
    createForm.scopes = []
    await loadTokens()
  } catch (e: any) {
    tokenError.value = e?.detail || e?.message || '创建失败'
  } finally {
    creating.value = false
  }
}

/** 复制明文（非安全上下文回退 execCommand） */
async function copyPlaintext(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  }
  tokenNotice.value = '明文已复制'
}

function maskToken(t: AccessToken): string {
  return `at_···${t.tokenHint || '****'}`
}

function scopeSummary(t: AccessToken): string {
  if (!t.scopes || !t.scopes.length) return '继承全部权限'
  if (t.scopes.length > 3) return `${t.scopes.length} 项权限`
  return t.scopes.join(', ')
}

function formatExpiry(expiresAt: number | string): string {
  if (expiresAt === 0 || expiresAt === '0' || expiresAt === null) return '永不过期'
  return formatDate(String(expiresAt))
}

function openEdit(t: AccessToken) {
  editingToken.value = t
  editForm.name = t.name
  editForm.scopes = [...(t.scopes || [])]
  if (t.expiresAt === 0 || t.expiresAt === '0') {
    editForm.expiryMode = 'never'
    editForm.customExpiresAt = ''
  } else {
    editForm.expiryMode = 'custom'
    editForm.customExpiresAt = toDateTimeLocal(t.expiresAt)
  }
}

function closeEdit() {
  editingToken.value = null
}

async function saveEdit() {
  if (!editingToken.value) return
  updating.value = true
  tokenError.value = ''
  tokenNotice.value = ''
  try {
    await accessTokenPort.update(editingToken.value.id, {
      name: editForm.name,
      scopes: editForm.scopes,
      expiresAt: toExpiresPayload(editForm.expiryMode, editForm.customExpiresAt),
    })
    tokenNotice.value = '更新成功'
    editingToken.value = null
    await loadTokens()
  } catch (e: any) {
    tokenError.value = e?.detail || e?.message || '更新失败'
  } finally {
    updating.value = false
  }
}

async function toggleStatus(t: AccessToken) {
  const next: AccessTokenStatus = t.status === 'enabled' ? 'disabled' : 'enabled'
  tokenError.value = ''
  tokenNotice.value = ''
  try {
    await accessTokenPort.update(t.id, { status: next })
    tokenNotice.value = next === 'enabled' ? '已启用' : '已停用'
    await loadTokens()
  } catch (e: any) {
    tokenError.value = e?.detail || e?.message || '操作失败'
  }
}

async function confirmDelete(t: AccessToken) {
  try {
    await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '删除 Access Token',
      content: `确认删除「${t.name}」？删除后持有该 Token 的外部 agent 将立即失效。`,
      confirmText: '删除',
      cancelText: '取消',
      danger: true,
    })
  } catch {
    return // 用户取消
  }
  tokenError.value = ''
  tokenNotice.value = ''
  try {
    await accessTokenPort.remove(t.id)
    tokenNotice.value = '删除成功'
    if (createdToken.value?.id === t.id) createdToken.value = null
    await loadTokens()
  } catch (e: any) {
    tokenError.value = e?.detail || e?.message || '删除失败'
  }
}

function toggleAllScopes() {
  createForm.scopes = allScopesSelected.value ? [] : [...ALL_ACCESS_TOKEN_SCOPE_CODES]
}

function toggleEditAllScopes() {
  editForm.scopes = editAllSelected.value ? [] : [...ALL_ACCESS_TOKEN_SCOPE_CODES]
}

onMounted(async () => {
  // intent=bind 回调回传：bind_ticket 完成绑定 / bind_error 展示原因；
  // 处理后清掉 query 避免刷新重复提交
  const bindTicket = route.query.bind_ticket as string | undefined
  const bindError = route.query.bind_error as string | undefined
  if (bindTicket || bindError) {
    router.replace({ query: {} })
  }
  if (bindError) {
    error.value = bindError
  }
  if (bindTicket) {
    await completeBind(bindTicket)
    return
  }
  await load()
  // INT-1140：个人配置页 Access Token 区块（入口页面「前往个人配置页管理」跳转定位）
  await loadTokens()
  if (route.query.tab === 'access-tokens' && tokenSectionRef.value) {
    await nextTick()
    tokenSectionRef.value.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
})
</script>

<style scoped>
.account-settings {
  padding: 24px;
  max-width: 900px;
  margin: 0 auto;
}
.page-header {
  margin-bottom: 20px;
}
.page-title {
  font-size: 20px;
  color: var(--primary-color, var(--foreground));
}
.page-title i {
  margin-right: 8px;
}
.page-description {
  margin-top: 4px;
  font-size: 13px;
  color: var(--color-gray-500);
}
.section-card {
  background: var(--card, #ffffff);
  border: 1px solid var(--color-gray-300);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}
.section-card h3 {
  margin: 0 0 12px;
  font-size: 16px;
}
.section-hint {
  font-size: 12px;
  color: var(--color-gray-400);
  margin: -6px 0 12px;
}
.user-info .info-row {
  display: flex;
  gap: 12px;
  padding: 6px 0;
  font-size: 14px;
}
.info-label {
  color: var(--color-gray-500);
  min-width: 64px;
}
.binding-table {
  width: 100%;
  border-collapse: collapse;
}
.binding-table th,
.binding-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--color-gray-200);
  text-align: left;
  font-size: 14px;
}
.binding-table th {
  background: var(--muted);
  font-weight: 600;
}
.empty-row {
  text-align: center;
  color: var(--color-gray-400);
  padding: 24px 0;
}
.bind-section h4 {
  margin: 16px 0 8px;
  font-size: 14px;
}
.bind-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.bind-btn {
  padding: 8px 14px;
  background: white;
  border: 1px solid var(--color-gray-300);
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
}
.bind-btn:hover {
  border-color: var(--secondary);
  color: var(--secondary);
}
.bind-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-sm {
  padding: 4px 10px;
  font-size: 13px;
}
.btn-danger {
  color: var(--destructive);
  border: 1px solid var(--destructive);
  border-radius: 4px;
  background: white;
  cursor: pointer;
}
.error-msg {
  color: var(--destructive);
  font-size: 14px;
  margin-bottom: 10px;
}
.success-msg {
  color: var(--success);
  font-size: 14px;
  margin-bottom: 10px;
}

/* ===== Access Token（INT-1140）===== */
.section-badge {
  display: inline-block;
  vertical-align: middle;
  margin-left: 8px;
  padding: 1px 8px;
  font-size: 11px;
  color: var(--magic-foreground, #fff);
  border-radius: 9999px;
  background: var(--magic-gradient);
}
.token-create,
.token-list,
.token-edit,
.token-created {
  margin-top: 16px;
  border-top: 1px dashed var(--color-gray-200);
  padding-top: 14px;
}
.token-create h4,
.token-list h4,
.token-edit h4,
.token-created h4 {
  margin: 0 0 10px;
  font-size: 14px;
}
.token-label {
  display: inline-block;
  min-width: 64px;
  font-size: 13px;
  color: var(--color-gray-500);
}
.token-expiry-select {
  width: auto;
  min-width: 220px;
  margin-right: 8px;
}
.scopes-catalog {
  margin: 12px 0;
}
.scopes-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.scopes-actions .section-hint {
  margin: 0;
  flex: 1;
}
.scope-group {
  margin-bottom: 10px;
}
.scope-group-title {
  margin: 0 0 6px;
  font-size: 13px;
  color: var(--color-gray-600);
  font-weight: 600;
}
.scope-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
}
.scope-check {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  cursor: pointer;
}
.scope-label {
  color: var(--foreground, #333);
}
.scope-code {
  font-size: 11px;
  color: var(--color-gray-400);
  background: var(--muted, #f5f5f5);
  padding: 0 4px;
  border-radius: 3px;
}
.token-plaintext-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.token-plaintext {
  flex: 1;
  min-width: 0;
  padding: 8px 12px;
  font-size: 13px;
  word-break: break-all;
  background: var(--muted, #f5f5f5);
  border: 1px dashed var(--color-gray-300);
  border-radius: 6px;
  color: var(--success-dark, #389e0d);
}
.token-table td {
  vertical-align: middle;
}
.token-name {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.token-hint {
  font-size: 12px;
  color: var(--color-gray-600);
}
.token-scopes {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--color-gray-600);
}
.token-status {
  display: inline-block;
  padding: 1px 8px;
  font-size: 12px;
  border-radius: 9999px;
}
.token-status.enabled {
  color: var(--success-dark, #389e0d);
  background: var(--success-light, rgba(82, 196, 26, 0.1));
}
.token-status.disabled {
  color: var(--color-gray-500);
  background: var(--muted, #f5f5f5);
}
.token-muted {
  color: var(--color-gray-400);
  font-size: 13px;
}
.token-actions {
  white-space: nowrap;
}
.token-actions .btn {
  margin-right: 6px;
}
.edit-actions {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}
</style>
