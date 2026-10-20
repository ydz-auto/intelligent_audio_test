<template>
  <div v-if="visible" class="dg-overlay" @click.self="close">
    <div class="dg-modal">
      <div class="dg-header">
        <h3><i class="fas fa-layer-group"></i> 设备分组管理</h3>
        <button class="dg-close" @click="close"><i class="fas fa-times"></i></button>
      </div>

      <div class="dg-body">
        <!-- 分组列表 -->
        <div class="dg-toolbar">
          <input class="form-input dg-search" v-model="searchKeyword" placeholder="搜索分组名称..." />
          <button class="btn btn-primary" @click="startCreate">
            <i class="fas fa-plus btn-icon"></i> 新建分组
          </button>
        </div>

        <div v-if="editing" class="dg-form">
          <div class="dg-form-row">
            <label>分组名称</label>
            <input class="form-input" v-model="form.name" placeholder="分组名称" />
          </div>
          <div class="dg-form-row">
            <label>父分组</label>
            <select class="form-input" v-model="form.parentId">
              <option value="">根分组（顶层）</option>
              <option v-for="opt in parentOptions" :key="opt.id" :value="opt.id">{{ opt.name }}</option>
            </select>
          </div>
          <div class="dg-form-row">
            <label>分组类型</label>
            <select class="form-input" v-model="form.groupType">
              <option value="test">测试设备组</option>
              <option value="playback">播放设备组</option>
            </select>
          </div>
          <div class="dg-form-row">
            <label>描述</label>
            <input class="form-input" v-model="form.description" placeholder="分组描述（可选）" />
          </div>
          <div class="dg-form-actions">
            <button class="btn btn-primary" @click="saveGroup" :disabled="saving || !form.name.trim()">
              {{ editingId ? '保存' : '创建' }}
            </button>
            <button class="btn btn-secondary" @click="cancelEdit">取消</button>
          </div>
        </div>

        <!-- 移动分组（INT-832：选目标父分组，根=移到顶层） -->
        <div v-if="movingGroupId" class="dg-form">
          <div class="dg-form-row">
            <label>移动分组</label>
            <span class="dg-move-source">{{ movingGroupName }}</span>
          </div>
          <div class="dg-form-row">
            <label>目标父分组</label>
            <select class="form-input" v-model="moveParentId">
              <option value="">根分组（顶层）</option>
              <option v-for="opt in moveTargetOptions" :key="opt.id" :value="opt.id">{{ opt.name }}</option>
            </select>
          </div>
          <div class="dg-form-actions">
            <button class="btn btn-primary" @click="confirmMove" :disabled="moving">
              <i class="fas fa-arrows-alt btn-icon"></i> 移动
            </button>
            <button class="btn btn-secondary" @click="cancelMove">取消</button>
          </div>
        </div>

        <table class="dg-table" v-if="visibleRows.length > 0">
          <thead>
            <tr>
              <th>分组名称</th>
              <th>类型</th>
              <th>设备数</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in visibleRows" :key="row.group.id">
              <tr>
                <td>
                  <span class="dg-tree-indent" :style="{ width: row.depth * 18 + 'px' }"></span>
                  <button
                    v-if="row.hasChildren"
                    class="dg-chevron"
                    :aria-label="row.expanded ? '收起子分组' : '展开子分组'"
                    @click="toggleTreeExpand(row.group.id)"
                  >
                    <i class="fas" :class="row.expanded ? 'fa-chevron-down' : 'fa-chevron-right'"></i>
                  </button>
                  <span v-else class="dg-chevron-spacer"></span>
                  <span class="dg-name" :class="{ 'dg-root': row.depth === 0 }">{{ row.group.name }}</span>
                </td>
                <td>
                  <span class="dg-type-badge" :class="row.group.groupType === 'playback' ? 'is-playback' : 'is-test'">
                    {{ row.group.groupType === 'playback' ? '播放设备组' : '测试设备组' }}
                  </span>
                </td>
                <td>{{ row.group.deviceCount ?? 0 }}</td>
                <td class="dg-actions">
                  <button class="btn btn-secondary btn-sm" @click="toggleExpand(row.group)">
                    <i class="fas" :class="expandedId === row.group.id ? 'fa-eye-slash' : 'fa-eye'"></i>
                    {{ expandedId === row.group.id ? '收起' : '成员' }}
                  </button>
                  <button class="btn btn-secondary btn-sm" @click="startEdit(row.group)">
                    <i class="fas fa-edit"></i> 编辑
                  </button>
                  <button class="btn btn-secondary btn-sm" @click="startMove(row.group)">
                    <i class="fas fa-arrows-alt"></i> 移动
                  </button>
                  <button class="btn btn-danger btn-sm" @click="deleteGroup(row.group)">
                    <i class="fas fa-trash"></i> 删除
                  </button>
                </td>
              </tr>
              <tr v-if="expandedId === row.group.id">
                <td :colspan="4" class="dg-members-cell">
                  <div class="dg-members">
                    <span class="dg-member-tag" v-for="device in expandedDevices" :key="device.id">
                      {{ device.name }}
                      <i class="fas fa-times dg-remove" @click="removeMember(row.group, device.id)"></i>
                    </span>
                    <span v-if="expandedDevices.length === 0" class="dg-empty">暂无成员设备</span>
                  </div>
                  <div class="dg-add-member">
                    <select class="form-input" v-model="addMemberId">
                      <option value="">选择要添加的设备...</option>
                      <option v-for="device in addableDevices" :key="device.id" :value="device.id">
                        {{ device.name }}
                      </option>
                    </select>
                    <button class="btn btn-primary btn-sm" :disabled="!addMemberId" @click="addMember(row.group)">
                      添加
                    </button>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
        <div v-else class="dg-empty-state">
          <i class="fas fa-info-circle"></i>
          <p>{{ loading ? '加载中...' : '暂无设备分组' }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

/**
 * 设备分组管理弹窗（INT-80 设备分组；INT-863 嵌套/移动）
 * 与用例分组（TestCaseManager）相互独立：走 /test-devices/device-groups 契约。
 * INT-863：扁平列表 → 按 parent_id 建树渲染（Chevron 展开子分组）；
 * 「移动」接 PUT /test-devices/device-groups/{id}/move（目标父分组，根=顶层）；
 * 删除含子分组文案升级（cascade=true 软删整棵子树，设备保留）。
 */
import { ref, computed, watch } from 'vue'
import { devicesPort } from '../../composables/device/devicesPort'
import type { DeviceGroup, TestDeviceView } from '../../domain/model/device'
import { useNotification } from '../../composables/modal/useNotification'
import { useModalControl } from '../../composables/modal/useModal'
import { MODAL_TYPES } from '../../composables/modal/constants'

const props = defineProps<{ visible: boolean; testDevices?: TestDeviceView[] }>()
const emit = defineEmits<{ (e: 'update:visible', value: boolean): void; (e: 'changed'): void }>()

const notification = useNotification()
const modalControl = useModalControl()

const groups = ref<DeviceGroup[]>([])
const loading = ref(false)
const saving = ref(false)
const moving = ref(false)
const searchKeyword = ref('')
const editing = ref(false)
const editingId = ref<string | null>(null)
const form = ref<{ name: string; description: string; groupType: string; parentId: string }>({
  name: '', description: '', groupType: 'test', parentId: '',
})

const expandedId = ref<string | null>(null)
const expandedDevices = ref<TestDeviceView[]>([])
const addMemberId = ref<string | number | ''>('')

/** 树形展开的分组 ID 集合（INT-863） */
const expandedTreeIds = ref<string[]>([])
/** 移动分组（INT-863）：当前待移动分组 id 与目标父分组 id */
const movingGroupId = ref<string | null>(null)
const moveParentId = ref('')

interface TreeRow {
  group: DeviceGroup
  depth: number
  hasChildren: boolean
  expanded: boolean
}

/** 建树后的根分组（parentId 为空或父不在当前列表内） */
const rootGroups = computed<DeviceGroup[]>(() => {
  const ids = new Set(groups.value.map((g) => g.id))
  return groups.value.filter((g) => !g.parentId || !ids.has(g.parentId))
})

/** 搜索过滤：命中分组保留，其祖先链一并显示 */
function filterTree(nodes: DeviceGroup[]): DeviceGroup[] {
  const kw = searchKeyword.value.trim()
  const out: DeviceGroup[] = []
  for (const g of nodes) {
    const children = filterTree(g.children ?? [])
    const selfMatch = !kw || g.name.includes(kw)
    if (selfMatch || children.length > 0) {
      out.push({ ...g, children })
    }
  }
  return out
}

/** 展平树为表格行（按展开状态） */
const visibleRows = computed<TreeRow[]>(() => {
  const rows: TreeRow[] = []
  const walk = (nodes: DeviceGroup[], depth: number) => {
    for (const g of nodes) {
      const hasChildren = (g.children?.length ?? 0) > 0
      const expanded = hasChildren && expandedTreeIds.value.includes(g.id)
      rows.push({ group: g, depth, hasChildren, expanded })
      if (expanded) walk(g.children ?? [], depth + 1)
    }
  }
  walk(filterTree(rootGroups.value), 0)
  return rows
})

/** 可添加成员：测试设备中未入当前展开分组的 */
const addableDevices = computed(() => {
  const memberIds = new Set((groups.value.find(g => g.id === expandedId.value)?.deviceIds ?? []).map(String))
  return (props.testDevices ?? []).filter(d => !memberIds.has(String(d.id)))
})

/** 新建/编辑表单的父分组选项：编辑时排除自身与后代（防环） */
const parentOptions = computed(() => {
  if (!editingId.value) return groups.value
  const excluded = collectDescendantIds(editingId.value)
  return groups.value.filter((g) => !excluded.has(g.id))
})

/** 移动目标父分组选项：排除被移动分组自身与后代（防环） */
const moveTargetOptions = computed(() => {
  if (!movingGroupId.value) return []
  const excluded = collectDescendantIds(movingGroupId.value)
  return groups.value.filter((g) => !excluded.has(g.id))
})

const movingGroupName = computed(() =>
  groups.value.find((g) => g.id === movingGroupId.value)?.name ?? ''
)

/** 收集某分组自身 + 全部后代 id（防环/防自引用） */
function collectDescendantIds(rootId: string): Set<string> {
  const set = new Set<string>()
  const walk = (id: string) => {
    set.add(id)
    const node = groups.value.find((g) => g.id === id)
    ;(node?.children ?? []).forEach((c) => walk(c.id))
  }
  walk(rootId)
  return set
}

watch(() => props.visible, (val) => {
  if (val) fetchGroups()
})

async function fetchGroups() {
  loading.value = true
  try {
    const page = await devicesPort.getGroups({ per_page: 200 })
    groups.value = page.items
  } catch (error) {
    console.error('加载设备分组失败:', error)
    notification.error('加载设备分组失败')
  } finally {
    loading.value = false
  }
}

function close() {
  emit('update:visible', false)
  cancelEdit()
  cancelMove()
  expandedId.value = null
  expandedTreeIds.value = []
}

function startCreate() {
  editing.value = true
  editingId.value = null
  form.value = { name: '', description: '', groupType: 'test', parentId: '' }
}

function startEdit(group: DeviceGroup) {
  editing.value = true
  editingId.value = group.id
  form.value = {
    name: group.name,
    description: group.description ?? '',
    groupType: group.groupType ?? 'test',
    parentId: group.parentId ?? '',
  }
}

function cancelEdit() {
  editing.value = false
  editingId.value = null
}

function toggleTreeExpand(id: string) {
  expandedTreeIds.value = expandedTreeIds.value.includes(id)
    ? expandedTreeIds.value.filter((x) => x !== id)
    : [...expandedTreeIds.value, id]
}

function startMove(group: DeviceGroup) {
  cancelEdit()
  movingGroupId.value = group.id
  moveParentId.value = group.parentId ?? ''
}

function cancelMove() {
  movingGroupId.value = null
  moveParentId.value = ''
}

async function confirmMove() {
  if (!movingGroupId.value) return
  moving.value = true
  try {
    await devicesPort.moveGroup(movingGroupId.value, moveParentId.value || null)
    notification.success('分组已移动')
    cancelMove()
    await fetchGroups()
    emit('changed')
  } catch (error) {
    console.error('移动分组失败:', error)
    notification.error(error instanceof Error ? error.message : '移动分组失败')
  } finally {
    moving.value = false
  }
}

async function saveGroup() {
  saving.value = true
  try {
    if (editingId.value) {
      await devicesPort.updateGroup(editingId.value, form.value)
      notification.success('分组已更新')
    } else {
      await devicesPort.createGroup(form.value)
      notification.success('分组已创建')
    }
    cancelEdit()
    await fetchGroups()
    emit('changed')
  } catch (error) {
    console.error('保存分组失败:', error)
    notification.error(error instanceof Error ? error.message : '保存分组失败')
  } finally {
    saving.value = false
  }
}

async function deleteGroup(group: DeviceGroup) {
  const hasMembers = (group.deviceCount ?? 0) > 0
  const childCount = group.children?.length ?? 0
  let message: string
  if (childCount > 0) {
    // INT-863：含子分组文案升级（cascade=true 软删整棵子树，设备保留）
    message = `分组「${group.name}」包含 ${group.deviceCount ?? 0} 个设备与 ${childCount} 个子分组。删除分组会把设备移出分组、子分组一并删除（设备本身保留），确定删除吗？`
  } else if (hasMembers) {
    message = `分组「${group.name}」包含 ${group.deviceCount} 个设备。删除分组会把设备移出分组（设备本身保留），确定删除吗？`
  } else {
    message = `确定删除分组「${group.name}」吗？`
  }
  // INT-286：删除分组改 BASIC_CONFIRM（danger）模态，替换原生 window.confirm
  let confirmed: unknown = null
  try {
    confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '删除设备分组',
      content: message,
      confirmText: '删除',
      cancelText: '取消',
      danger: true,
    })
  } catch {
    return // 异常路径兜底：视为取消
  }
  if (!confirmed) return // 用户取消
  try {
    await devicesPort.deleteGroup(group.id, true)
    notification.success('分组已删除')
    if (expandedId.value === group.id) expandedId.value = null
    expandedTreeIds.value = expandedTreeIds.value.filter((x) => x !== group.id)
    await fetchGroups()
    emit('changed')
  } catch (error) {
    console.error('删除分组失败:', error)
    notification.error(error instanceof Error ? error.message : '删除分组失败')
  }
}

async function toggleExpand(group: DeviceGroup) {
  if (expandedId.value === group.id) {
    expandedId.value = null
    expandedDevices.value = []
    return
  }
  expandedId.value = group.id
  addMemberId.value = ''
  try {
    const detail = await devicesPort.getGroup(group.id)
    const memberIds = detail.deviceIds ?? []
    const all = props.testDevices ?? []
    expandedDevices.value = all.filter(d => memberIds.map(String).includes(String(d.id))) as TestDeviceView[]
  } catch (error) {
    console.error('加载分组详情失败:', error)
    expandedDevices.value = []
  }
}

async function addMember(group: DeviceGroup) {
  if (!addMemberId.value) return
  try {
    await devicesPort.addDevicesToGroup(group.id, [addMemberId.value])
    addMemberId.value = ''
    await toggleExpand(group)
    await fetchGroups()
    emit('changed')
  } catch (error) {
    console.error('添加设备到分组失败:', error)
    notification.error(error instanceof Error ? error.message : '添加设备失败')
  }
}

async function removeMember(group: DeviceGroup, deviceId: string | number) {
  try {
    await devicesPort.removeDevicesFromGroup(group.id, [deviceId])
    await toggleExpand(group)
    await fetchGroups()
    emit('changed')
  } catch (error) {
    console.error('移除分组设备失败:', error)
    notification.error(error instanceof Error ? error.message : '移除设备失败')
  }
}
</script>

<style scoped>
.dg-overlay {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--color-black) 45%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}
.dg-modal {
  background: var(--background-primary, #fff);
  border-radius: var(--border-radius-lg, 12px);
  width: min(760px, 92vw);
  max-height: 82vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-dialog, 0 12px 40px rgba(0, 0, 0, 0.25));
}
.dg-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color, #eee);
}
.dg-header h3 {
  margin: 0;
  font-size: 1.05rem;
  color: var(--primary-color);
}
.dg-close {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 1rem;
  color: var(--text-secondary, #888);
}
.dg-body {
  padding: 16px 20px;
  overflow-y: auto;
}
.dg-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}
.dg-search {
  flex: 1;
}
.dg-form {
  border: 1px solid var(--border-color, #eee);
  border-radius: var(--radius-control, 8px);
  padding: 12px;
  margin-bottom: 12px;
  display: grid;
  gap: 8px;
}
.dg-form-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.dg-form-row label {
  width: 96px;
  font-size: 0.88rem;
  color: var(--text-secondary, #666);
  flex-shrink: 0;
}
.dg-form-row .form-input {
  flex: 1;
}
.dg-move-source {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--primary-color);
}
.dg-form-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
.dg-table {
  width: 100%;
  border-collapse: collapse;
}
.dg-table th,
.dg-table td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-color, #eee);
  font-size: 0.9rem;
}
.dg-tree-indent {
  display: inline-block;
}
.dg-chevron {
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 0 4px;
  color: var(--text-secondary, #666);
  font-size: 0.8rem;
  vertical-align: middle;
}
.dg-chevron-spacer {
  display: inline-block;
  width: 22px;
}
.dg-name {
  vertical-align: middle;
}
.dg-root {
  font-weight: 600;
}
.dg-type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 0.78rem;
}
.dg-type-badge.is-test {
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  color: var(--primary-color);
}
.dg-type-badge.is-playback {
  background: color-mix(in srgb, var(--success-color) 10%, transparent);
  color: var(--success-color);
}
.dg-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.btn-sm {
  padding: 4px 8px;
  font-size: 0.8rem;
}
.dg-members-cell {
  background: var(--background-secondary, #fafafa);
}
.dg-members {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.dg-member-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--background-primary, #fff);
  border: 1px solid var(--border-color, #ddd);
  border-radius: var(--radius-card, 16px);
  padding: 3px 10px;
  font-size: 0.82rem;
}
.dg-remove {
  cursor: pointer;
  color: var(--danger-color, #d33);
  font-size: 0.75rem;
}
.dg-empty {
  color: var(--text-secondary, #999);
  font-size: 0.85rem;
}
.dg-add-member {
  display: flex;
  gap: 8px;
}
.dg-add-member .form-input {
  max-width: 320px;
}
.dg-empty-state {
  text-align: center;
  color: var(--text-secondary, #999);
  padding: 32px 0;
}
</style>
