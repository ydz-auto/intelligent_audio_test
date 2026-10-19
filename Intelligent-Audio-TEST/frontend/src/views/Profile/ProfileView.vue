<template>
  <div class="profile-page">
    <!-- 加载态骨架（身份数据未就绪，照 13_个人中心 §3.2） -->
    <div v-if="!user" class="profile-card identity-card">
      <div class="skeleton-row" aria-label="正在加载个人信息">
        <div class="skeleton skeleton-avatar"></div>
        <div class="skeleton-lines">
          <div class="skeleton skeleton-line-w"></div>
          <div class="skeleton skeleton-line-l"></div>
        </div>
      </div>
    </div>

    <template v-else>
      <!-- 用户身份卡 + 个人数据快捷条（§3.2/§3.3） -->
      <div class="profile-card identity-card">
        <div class="identity-row">
          <div
            class="avatar"
            :style="{ backgroundColor: avatarStyle }"
          >{{ avatarFallback }}</div>
          <div class="identity-info">
            <div class="identity-main">
              <span class="username">{{ username }}</span>
              <span v-if="roleName" class="badge role-badge">{{ roleName }}</span>
              <span class="badge id-badge">
                <span class="id-text">用户 ID {{ user.id }}</span>
                <button type="button" class="copy-btn" aria-label="复制用户 ID" title="复制用户 ID" @click="copyUserId">
                  <i class="fas fa-copy"></i>
                </button>
              </span>
            </div>
            <div class="identity-sub">@{{ username }}</div>
          </div>
        </div>

        <!-- 个人数据快捷条（整格可点，hover 浮起 primary） -->
        <div class="quick-stats">
          <div ref="favoritesWrap" class="quick-stat-wrap">
            <button
              type="button"
              class="quick-stat"
              aria-label="我的收藏"
              @click="togglePopover('favorites')"
            >
              <div class="quick-stat-head">
                <span class="stat-icon chart-4"><i class="fas fa-heart"></i></span>
                <span class="stat-label">我的收藏</span>
              </div>
              <div class="stat-value">{{ favoritesLoading ? '…' : favoritesTotal }}</div>
              <div class="stat-desc">任务 · 报告 · 用例</div>
            </button>

            <div v-if="activePopover === 'favorites'" class="popover-panel favorites-popover">
              <div class="popover-title">我的收藏</div>
              <div v-if="favoriteRows.length === 0" class="popover-empty">
                <p class="empty-title">暂无收藏内容</p>
                <p class="empty-desc">在列表页点击收藏，相关内容会显示在这里</p>
              </div>
              <div v-else class="popover-rows">
                <router-link
                  v-for="row in favoriteRows"
                  :key="row.key"
                  :to="row.to"
                  class="popover-row"
                >
                  <i :class="row.icon" class="row-icon"></i>
                  <span class="row-label">{{ row.label }}</span>
                  <span class="row-count" :class="{ zero: row.count === 0 }">{{ row.count }}</span>
                  <i class="fas fa-chevron-right chevron"></i>
                </router-link>
              </div>
            </div>
          </div>

          <router-link v-if="canSeeMyTasks" to="/tasks?scope=mine" class="quick-stat">
            <div class="quick-stat-head">
              <span class="stat-icon info"><i class="fas fa-clipboard-list"></i></span>
              <span class="stat-label">我的任务</span>
            </div>
            <div class="stat-value muted">查看全部</div>
            <div class="stat-desc">我创建的任务</div>
          </router-link>

          <router-link v-if="canSeeMyReports" to="/history-reports?scope=mine" class="quick-stat">
            <div class="quick-stat-head">
              <span class="stat-icon success"><i class="fas fa-file-chart-line"></i></span>
              <span class="stat-label">我的报告</span>
            </div>
            <div class="stat-value muted">查看全部</div>
            <div class="stat-desc">我生成的报告</div>
          </router-link>
        </div>
      </div>

      <div class="profile-grid">
        <!-- 左列：个人信息 + 账号安全 -->
        <div class="profile-left">
          <div class="profile-card section-card">
            <div class="card-header">
              <div class="card-heading">
                <span class="card-icon info"><i class="fas fa-user-cog"></i></span>
                <div class="card-title-group">
                  <span class="card-title">个人信息</span>
                  <span class="card-desc">账号基础信息与权限概览</span>
                </div>
              </div>
              <button
                type="button"
                class="btn btn-outline btn-sm"
                title="自我资料更新 F3 待后端立项（当前为壳）"
                @click="openEditProfile"
              >
                <i class="fas fa-pen"></i> 编辑资料
              </button>
            </div>

            <div class="info-rows">
              <div class="info-row">
                <div class="info-label-group">
                  <span class="info-label">用户名</span>
                  <span class="info-note">用户名创建后不可修改，如需变更请联系管理员</span>
                </div>
                <span class="info-value">@{{ username }}</span>
              </div>
              <div class="info-row">
                <div class="info-label-group">
                  <span class="info-label">角色</span>
                </div>
                <span class="info-value">
                  <span v-if="roleName" class="badge role-badge">{{ roleName }}</span>
                  <template v-else>—</template>
                </span>
              </div>
              <div class="info-row">
                <div class="info-label-group">
                  <span class="info-label">用户 ID</span>
                </div>
                <span class="info-value mono">
                  {{ user.id }}
                  <button type="button" class="copy-btn" aria-label="复制用户 ID" title="复制用户 ID" @click="copyUserId">
                    <i class="fas fa-copy"></i>
                  </button>
                </span>
              </div>
              <div class="info-row">
                <div class="info-label-group">
                  <span class="info-label">邮箱</span>
                  <span class="info-note">待开放</span>
                </div>
                <span class="info-value muted" title="邮箱展示功能开发中">—</span>
              </div>
              <div class="info-row">
                <div class="info-label-group">
                  <span class="info-label">权限概览</span>
                </div>
                <div ref="permissionWrap" class="permission-trigger-wrap">
                  <button
                    type="button"
                    class="permission-trigger"
                    aria-label="查看权限清单"
                    @click="togglePopover('permissions')"
                  >
                    <span class="badge count-badge">{{ permissions.length }} 项权限</span>
                    <i class="fas fa-chevron-right chevron"></i>
                  </button>

                  <div v-if="activePopover === 'permissions'" class="popover-panel permission-popover">
                    <div class="popover-title">权限清单</div>
                    <div class="popover-desc">当前账号在角色权限基础上生效的权限码</div>
                    <p v-if="isWildcard" class="wildcard-copy">超级管理员持有全部权限（通配 *）</p>
                    <div v-else class="permission-groups">
                      <div v-for="g in groupedPermissions" :key="g.module" class="permission-group">
                        <p class="group-title">{{ g.module }}（{{ g.codes.length }}）</p>
                        <div class="group-codes">
                          <code v-for="c in g.codes" :key="c" class="code-chip">{{ c }}</code>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="card-footnote">
              <i class="fas fa-info-circle"></i>
              <span>当前页面为只读展示。如需修改用户名、邮箱或重置密码，请联系平台管理员。</span>
            </div>
          </div>

          <div class="profile-card section-card">
            <div class="card-header">
              <div class="card-heading">
                <span class="card-icon info"><i class="fas fa-shield-alt"></i></span>
                <div class="card-title-group">
                  <span class="card-title">账号安全</span>
                  <span class="card-desc">登录密码与第三方账号绑定</span>
                </div>
              </div>
            </div>

            <!-- 区块：登录与认证 -->
            <div class="security-section">
              <h4 class="section-title">登录与认证</h4>

              <!-- 修改密码行（F2 待 FEAT 壳；入口保留、提交提示待后端立项） -->
              <div class="security-row">
                <span class="row-icon neutral"><i class="fas fa-key"></i></span>
                <div class="row-copy">
                  <span class="row-title">修改密码</span>
                  <span class="row-desc">更新登录密码，保护账号安全</span>
                  <span class="pending-badge">待后端立项</span>
                </div>
                <button
                  type="button"
                  class="btn btn-outline btn-sm"
                  @click="openChangePassword"
                >修改密码</button>
              </div>

              <!-- 第三方账号绑定（§3.5.2，全量可用） -->
              <div class="bindings-block">
                <h4 class="section-title">第三方账号绑定</h4>
                <span class="section-hint">绑定后可使用对应第三方账号直接登录本账号</span>

                <div v-if="loadingBindings" class="bindings-loading">
                  <i class="fas fa-spinner fa-spin"></i> 加载中…
                </div>
                <div v-else-if="emptyBindings" class="bindings-empty">
                  <p class="empty-title">当前没有可绑定的第三方登录方式</p>
                  <p class="empty-desc">请联系管理员在系统设置中添加 OAuth 提供方</p>
                </div>
                <ul v-else class="bindings-grid">
                  <li v-for="{ provider, binding } in bindingRows" :key="provider.id" class="binding-row">
                    <div class="binding-left">
                      <span class="provider-icon"><i :class="provider.icon || 'fas fa-link'"></i></span>
                      <div class="provider-copy">
                        <div class="provider-name-line">
                          <span class="provider-name">{{ provider.name }}</span>
                          <span v-if="binding" class="badge bound-badge">已绑定</span>
                        </div>
                        <span class="provider-sub">{{ binding ? binding.providerUserId : '未绑定' }}</span>
                      </div>
                    </div>
                    <button
                      v-if="binding"
                      type="button"
                      class="btn btn-ghost-danger btn-sm"
                      :disabled="bindingsLocked"
                      :aria-label="bindingsLocked ? '正在处理' : `解绑 ${provider.name}`"
                      @click="unbind(binding)"
                    >
                      <i class="fas fa-unlink"></i> 解绑
                    </button>
                    <button
                      v-else
                      type="button"
                      class="btn btn-outline btn-sm"
                      :disabled="bindingsLocked"
                      :aria-label="bindingsLocked ? '正在处理' : `绑定 ${provider.name}`"
                      @click="startBind(provider.slug)"
                    >绑定</button>
                  </li>
                </ul>
              </div>
            </div>

            <!-- 区块：会话与访问（后端无 JWT 会话端点，壳标注待后端立项） -->
            <div class="security-section">
              <h4 class="section-title">会话与访问</h4>
              <div class="security-row">
                <span class="row-icon neutral"><i class="fas fa-laptop"></i></span>
                <div class="row-copy">
                  <span class="row-title">登录会话</span>
                  <span class="row-desc">查看当前账号的登录设备与会话（JWT 无状态，后端未具端点）</span>
                  <span class="pending-badge">待后端立项</span>
                </div>
                <button type="button" class="btn btn-outline btn-sm" disabled>查看会话</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 右列：快捷入口 + 外观提示（§3.6） -->
        <div class="profile-right">
          <div class="profile-card section-card quick-links-card">
            <div class="card-header">
              <div class="card-heading">
                <span class="card-icon neutral"><i class="fas fa-rocket"></i></span>
                <div class="card-title-group">
                  <span class="card-title">快捷入口</span>
                </div>
              </div>
            </div>
            <div class="quick-links">
              <router-link to="/dashboard" class="quick-link">
                <span class="ql-icon neutral"><i class="fas fa-th-large"></i></span>
                <span class="ql-copy">
                  <span class="ql-title">工作台</span>
                  <span class="ql-desc">平台概览与快捷操作</span>
                </span>
                <i class="fas fa-chevron-right chevron"></i>
              </router-link>
              <router-link v-if="canSeeSettingsQuickLink" to="/system-settings/site" class="quick-link">
                <span class="ql-icon neutral"><i class="fas fa-cog"></i></span>
                <span class="ql-copy">
                  <span class="ql-title">系统设置</span>
                  <span class="ql-desc">站点、用户与权限、认证、外观与主题等</span>
                </span>
                <i class="fas fa-chevron-right chevron"></i>
              </router-link>
              <router-link to="/user-guide" class="quick-link">
                <span class="ql-icon neutral"><i class="fas fa-book-open"></i></span>
                <span class="ql-copy">
                  <span class="ql-title">使用文档</span>
                  <span class="ql-desc">使用手册与 API 手册</span>
                </span>
                <i class="fas fa-chevron-right chevron"></i>
              </router-link>
              <router-link to="/about" class="quick-link">
                <span class="ql-icon neutral"><i class="fas fa-info-circle"></i></span>
                <span class="ql-copy">
                  <span class="ql-title">关于平台</span>
                  <span class="ql-desc">平台版本与服务状态</span>
                </span>
                <i class="fas fa-chevron-right chevron"></i>
              </router-link>
            </div>
          </div>

          <div class="appearance-alert">
            <i class="fas fa-palette"></i>
            <div>
              <p class="alert-title">外观与主题</p>
              <p class="alert-desc">主题、字体、圆角、密度等外观偏好，可在右上角主题面板或「系统设置 → 外观与主题」中调整。</p>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

/**
 * 个人中心页（13_个人中心 INT-358 / 总表 §3 J01/J02 / 卡 INT-744）：
 * 身份卡 + 个人数据快捷区 + 个人信息卡（F3 编辑壳）+ 账号安全卡（F2 改密壳/会话壳/OAuth 绑定）。
 * 原 Vue 风格（tokens.css 语义令牌 + components/common 模态窗系统 + Font Awesome），
 * 不引入 React/newAPI 形态。深色模式经 tokens.css .dark 自动适配。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useAuthStore } from '../../store/authStore'
import { useProfilePage } from '../../composables/profile/useProfilePage'

const authStore = useAuthStore()
const {
  user,
  username,
  roleName,
  permissions,
  avatarStyle,
  avatarFallback,
  favorites,
  favoritesLoading,
  favoritesTotal,
  canSeeMyTasks,
  canSeeMyReports,
  bindingRows,
  emptyBindings,
  loadingBindings,
  bindingsLocked,
  startBind,
  unbind,
  openChangePassword,
  openEditProfile,
  groupedPermissions,
  isWildcard,
  canSeeSettingsQuickLink,
  copyUserId,
} = useProfilePage()

// ===== 我的收藏明细 Popover（§3.3.1；按实体 read 权限码过滤）=====
const activePopover = ref<'favorites' | 'permissions' | null>(null)
const favoritesWrap = ref<HTMLElement | null>(null)
const permissionWrap = ref<HTMLElement | null>(null)

const favoriteRows = computed(() => {
  const rows = [
    {
      key: 'task',
      icon: 'fas fa-clipboard-list',
      label: '收藏的任务',
      count: favorites.value.task,
      visible: authStore.hasPermission('task:read'),
      to: { path: '/tasks', query: { favorite: '1' } },
    },
    {
      key: 'report',
      icon: 'fas fa-file-chart-line',
      label: '收藏的报告',
      count: favorites.value.report,
      visible: authStore.hasPermission('report:read'),
      // 报告列表现为 /history-reports（总表 G02 后续并轨 /report-center，旧链 redirect）
      to: { path: '/history-reports', query: { favorite: '1' } },
    },
    {
      key: 'testcase',
      icon: 'fas fa-list-check',
      label: '收藏的用例',
      count: favorites.value.testcase,
      visible: authStore.hasPermission('testcase:read'),
      to: { path: '/TestCaseManager', query: { favorite: '1' } },
    },
  ]
  return rows.filter((row) => row.visible)
})

function togglePopover(name: 'favorites' | 'permissions') {
  activePopover.value = activePopover.value === name ? null : name
}

function handleOutsideClick(event: MouseEvent) {
  if (!activePopover.value) return
  const wrap = activePopover.value === 'favorites' ? favoritesWrap.value : permissionWrap.value
  if (wrap && !wrap.contains(event.target as Node)) {
    activePopover.value = null
  }
}

onMounted(() => {
  document.addEventListener('click', handleOutsideClick)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', handleOutsideClick)
})
</script>

<style scoped>
.profile-page {
  padding: 24px;
  max-width: 1120px;
  margin: 0 auto;
}

.profile-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-card, 16px);
  overflow: hidden;
}

/* ===== 用户身份卡 ===== */
.identity-card {
  margin-bottom: 20px;
}

.identity-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
}

.avatar {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-card, 16px);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  font-weight: 600;
  color: var(--color-white);
  flex-shrink: 0;
  box-shadow: 0 0 0 2px var(--card);
}

.identity-info {
  min-width: 0;
  flex: 1;
}

.identity-main {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.username {
  font-size: 22px;
  font-weight: 600;
  color: var(--foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.identity-sub {
  margin-top: 4px;
  font-size: 13px;
  color: var(--muted-foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ===== 徽章 ===== */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-tag, 4px);
  font-size: 12px;
  font-weight: 500;
}

.role-badge {
  background: var(--muted);
  color: var(--muted-foreground);
}

.id-badge {
  background: var(--secondary-light);
  color: var(--secondary);
}

.id-text {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.copy-btn {
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  color: inherit;
  font-size: 12px;
  line-height: 1;
}

.copy-btn:hover {
  color: var(--primary);
}

.bound-badge {
  background: var(--success-light);
  color: var(--success);
}

.count-badge {
  background: var(--muted);
  color: var(--foreground);
}

/* ===== 个人数据快捷条 ===== */
.quick-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-top: 1px solid var(--border);
}

.quick-stat-wrap {
  position: relative;
}

.quick-stat {
  display: block;
  width: 100%;
  text-align: left;
  padding: 14px 20px;
  background: none;
  border: none;
  border-right: 1px solid var(--border);
  cursor: pointer;
  font: inherit;
  color: var(--foreground);
  transition: color 0.2s;
}

.quick-stat-wrap:last-child .quick-stat,
.quick-stat:nth-child(3) {
  border-right: none;
}

.quick-stat:hover {
  color: var(--primary);
}

.quick-stat-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-icon {
  width: 24px;
  height: 24px;
  border-radius: var(--radius-control, 8px);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex-shrink: 0;
}

.stat-icon.chart-4 {
  background: var(--destructive-light);
  color: var(--chart-4);
}

.stat-icon.info {
  background: var(--secondary-light);
  color: var(--secondary);
}

.stat-icon.success {
  background: var(--success-light);
  color: var(--success);
}

.stat-label {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--muted-foreground);
}

.stat-value {
  margin-top: 6px;
  font-family: var(--font-mono, monospace);
  font-size: 22px;
  font-weight: 700;
  color: var(--foreground);
}

.stat-value.muted {
  font-size: 16px;
  color: var(--muted-foreground);
}

.stat-desc {
  margin-top: 2px;
  font-size: 12px;
  color: var(--muted-foreground);
  opacity: 0.8;
}

/* ===== 双列栅格 ===== */
.profile-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 20px;
  align-items: start;
}

.profile-left,
.profile-right {
  display: grid;
  gap: 20px;
}

.profile-right {
  position: sticky;
  top: 20px;
}

/* ===== 卡片头 ===== */
.section-card {
  padding: 20px;
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.card-heading {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.card-icon {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-control, 8px);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  flex-shrink: 0;
}

.card-icon.info {
  background: var(--secondary-light);
  color: var(--secondary);
}

.card-icon.neutral {
  background: var(--muted);
  color: var(--muted-foreground);
}

.card-title-group {
  display: grid;
  gap: 2px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--foreground);
}

.card-desc {
  font-size: 12px;
  color: var(--muted-foreground);
}

/* ===== 个人信息卡 ===== */
.info-rows {
  display: grid;
}

.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 0;
  border-bottom: 1px solid var(--muted);
}

.info-row:last-child {
  border-bottom: none;
}

.info-label-group {
  display: grid;
  gap: 2px;
}

.info-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--foreground);
}

.info-note {
  font-size: 12px;
  color: var(--muted-foreground);
}

.info-value {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--muted-foreground);
}

.info-value.mono {
  font-family: var(--font-mono, monospace);
  font-variant-numeric: tabular-nums;
}

.info-value.muted {
  color: var(--muted-foreground);
}

.permission-trigger-wrap {
  position: relative;
}

.permission-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  font: inherit;
  color: var(--foreground);
  transition: color 0.2s;
}

.permission-trigger:hover {
  color: var(--primary);
}

.card-footnote {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 12px;
  padding: 10px 12px;
  background: var(--muted);
  border-radius: var(--radius-control, 8px);
  font-size: 12px;
  color: var(--muted-foreground);
  line-height: 1.5;
}

/* ===== 账号安全卡 ===== */
.security-section {
  padding: 12px 0 4px;
}

.security-section + .security-section {
  border-top: 1px solid var(--muted);
}

.section-title {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
}

.section-hint {
  font-size: 12px;
  color: var(--muted-foreground);
  display: block;
  margin: -6px 0 12px;
}

.security-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
}

.row-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-control, 8px);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
}

.row-icon.neutral {
  background: var(--muted);
  color: var(--muted-foreground);
}

.row-copy {
  display: grid;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.row-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--foreground);
}

.row-desc {
  font-size: 12px;
  color: var(--muted-foreground);
}

.pending-badge {
  display: inline-block;
  width: fit-content;
  margin-top: 2px;
  padding: 1px 6px;
  border-radius: var(--radius-tag, 4px);
  font-size: 11px;
  background: var(--warning-light);
  color: var(--warning-dark);
}

/* ===== 第三方绑定 ===== */
.bindings-block {
  margin-top: 4px;
}

.bindings-grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.binding-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-card, 16px);
  padding: 10px 12px;
}

.binding-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.provider-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-control, 8px);
  background: var(--muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--muted-foreground);
  font-size: 14px;
  flex-shrink: 0;
}

.provider-copy {
  min-width: 0;
}

.provider-name-line {
  display: flex;
  align-items: center;
  gap: 6px;
}

.provider-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.provider-sub {
  font-size: 12px;
  font-family: var(--font-mono, monospace);
  color: var(--muted-foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bindings-loading,
.bindings-empty {
  padding: 20px 0;
  text-align: center;
  color: var(--muted-foreground);
  font-size: 13px;
}

.bindings-empty .empty-title {
  margin: 0 0 4px;
  font-weight: 500;
  color: var(--foreground);
}

.bindings-empty .empty-desc {
  margin: 0;
  font-size: 12px;
  color: var(--muted-foreground);
}

/* ===== 按钮 ===== */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.2s;
  white-space: nowrap;
}

.btn-sm {
  padding: 5px 12px;
  font-size: 12px;
}

.btn-outline {
  background: var(--card);
  border-color: var(--border);
  color: var(--foreground);
}

.btn-outline:hover:not(:disabled) {
  border-color: var(--secondary);
  color: var(--secondary);
}

.btn-outline:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-ghost-danger {
  background: none;
  border: none;
  color: var(--destructive);
}

.btn-ghost-danger:hover:not(:disabled) {
  background: var(--destructive-light);
}

.btn-ghost-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ===== 快捷入口 ===== */
.quick-links {
  display: grid;
  gap: 2px;
}

.quick-link {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-control, 8px);
  color: var(--foreground);
  text-decoration: none;
  transition: background 0.2s;
}

.quick-link:hover {
  background: var(--muted);
}

.ql-icon {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-control, 8px);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  flex-shrink: 0;
  background: var(--muted);
  color: var(--muted-foreground);
}

.ql-copy {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 2px;
}

.ql-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--foreground);
}

.ql-desc {
  font-size: 12px;
  color: var(--muted-foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chevron {
  font-size: 12px;
  color: var(--muted-foreground);
  flex-shrink: 0;
}

/* ===== 外观提示 ===== */
.appearance-alert {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-card, 16px);
  background: var(--card);
  color: var(--muted-foreground);
}

.appearance-alert > i {
  color: var(--warning);
  margin-top: 2px;
}

.alert-title {
  margin: 0 0 2px;
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground);
}

.alert-desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
}

/* ===== Popover（原风格轻量实现，无 React Popover） ===== */
.popover-panel {
  position: absolute;
  z-index: 100;
  background: var(--popover);
  border: 1px solid var(--border);
  border-radius: var(--radius-control, 8px);
  box-shadow: var(--shadow-md);
  padding: 12px;
}

.favorites-popover {
  top: calc(100% + 4px);
  left: 0;
  min-width: 240px;
}

.permission-popover {
  top: calc(100% + 4px);
  right: 0;
  min-width: 280px;
  max-width: 320px;
}

.popover-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
  margin-bottom: 6px;
}

.popover-desc {
  font-size: 12px;
  color: var(--muted-foreground);
  margin-bottom: 10px;
}

.popover-rows {
  display: grid;
  gap: 2px;
}

.popover-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border-radius: var(--radius-control, 8px);
  color: var(--foreground);
  text-decoration: none;
  transition: background 0.2s;
}

.popover-row:hover {
  background: var(--muted);
}

.row-icon {
  font-size: 14px;
  color: var(--muted-foreground);
  flex-shrink: 0;
}

.row-label {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-count {
  font-family: var(--font-mono, monospace);
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.row-count.zero {
  color: var(--muted-foreground);
  font-weight: 500;
}

.popover-empty {
  text-align: left;
}

.popover-empty .empty-title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
}

.popover-empty .empty-desc {
  margin: 0;
  font-size: 12px;
  color: var(--muted-foreground);
}

.wildcard-copy {
  margin: 0;
  font-size: 13px;
  color: var(--foreground);
}

.permission-groups {
  max-height: 280px;
  overflow-y: auto;
  display: grid;
  gap: 10px;
}

.permission-group .group-title {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--muted-foreground);
}

.group-codes {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.code-chip {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  background: var(--muted);
  color: var(--foreground);
  border-radius: var(--radius-tag, 4px);
  padding: 2px 6px;
}

/* ===== 加载骨架 ===== */
.skeleton-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
}

.skeleton {
  background: var(--muted);
  border-radius: var(--radius-card, 16px);
  animation: skeleton-pulse 1.4s ease-in-out infinite;
}

.skeleton-avatar {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-card, 16px);
}

.skeleton-lines {
  display: grid;
  gap: 8px;
  flex: 1;
}

.skeleton-line-w {
  height: 20px;
  width: 160px;
}

.skeleton-line-l {
  height: 14px;
  width: 240px;
}

@keyframes skeleton-pulse {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

/* ===== 响应式 ===== */
@media (max-width: 900px) {
  .profile-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .profile-right {
    position: static;
  }
}

@media (max-width: 640px) {
  .quick-stats {
    grid-template-columns: 1fr;
  }
  .quick-stat {
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  .bindings-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
