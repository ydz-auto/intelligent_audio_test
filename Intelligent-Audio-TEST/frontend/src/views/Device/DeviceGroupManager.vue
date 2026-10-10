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

        <table class="dg-table" v-if="groups.length > 0">
          <thead>
            <tr>
              <th>分组名称</th>
              <th>类型</th>
              <th>设备数</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="group in filteredGroups" :key="group.id">
              <tr>
                <td>{{ group.name }}</td>
                <td>{{ group.groupType === 'playback' ? '播放设备组' : '测试设备组' }}</td>
                <td>{{ group.deviceCount ?? 0 }}</td>
                <td class="dg-actions">
                  <button class="btn btn-secondary btn-sm" @click="toggleExpand(group)">
                    <i class="fas" :class="expandedId === group.id ? 'fa-eye-slash' : 'fa-eye'"></i>
                    {{ expandedId === group.id ? '收起' : '成员' }}
                  </button>
                  <button class="btn btn-secondary btn-sm" @click="startEdit(group)">
                    <i class="fas fa-edit"></i> 编辑
                  </button>
                  <button class="btn btn-danger btn-sm" @click="deleteGroup(group)">
                    <i class="fas fa-trash"></i> 删除
                  </button>
                </td>
              </tr>
              <tr v-if="expandedId === group.id">
                <td colspan="4" class="dg-members-cell">
                  <div class="dg-members">
                    <span class="dg-member-tag" v-for="device in expandedDevices" :key="device.id">
                      {{ device.name }}
                      <i class="fas fa-times dg-remove" @click="removeMember(group, device.id)"></i>
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
                    <button class="btn btn-primary btn-sm" :disabled="!addMemberId" @click="addMember(group)">
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
/**
 * 设备分组管理弹窗（INT-80 设备分组）
 * 与用例分组（TestCaseManager）相互独立：走 /test-devices/device-groups 契约。
 */
import { ref, computed, watch } from 'vue'
import { devicesPort } from '../../composables/device/devicesPort'
import type { DeviceGroup, TestDeviceView } from '../../domain/model/device'
import { useNotification } from '../../composables/modal/useNotification'

const props = defineProps<{ visible: boolean; testDevices?: TestDeviceView[] }>()
const emit = defineEmits<{ (e: 'update:visible', value: boolean): void; (e: 'changed'): void }>()

const notification = useNotification()

const groups = ref<DeviceGroup[]>([])
const loading = ref(false)
const saving = ref(false)
const searchKeyword = ref('')
const editing = ref(false)
const editingId = ref<string | null>(null)
const form = ref({ name: '', description: '', groupType: 'test' })

const expandedId = ref<string | null>(null)
const expandedDevices = ref<TestDeviceView[]>([])
const addMemberId = ref<string | number | ''>('')

const filteredGroups = computed(() =>
  groups.value.filter(g => !searchKeyword.value.trim() || g.name.includes(searchKeyword.value.trim()))
)

/** 可添加成员：测试设备中未入当前展开分组的 */
const addableDevices = computed(() => {
  const memberIds = new Set((groups.value.find(g => g.id === expandedId.value)?.deviceIds ?? []).map(String))
  return (props.testDevices ?? []).filter(d => !memberIds.has(String(d.id)))
})

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
  expandedId.value = null
}

function startCreate() {
  editing.value = true
  editingId.value = null
  form.value = { name: '', description: '', groupType: 'test' }
}

function startEdit(group: DeviceGroup) {
  editing.value = true
  editingId.value = group.id
  form.value = { name: group.name, description: group.description ?? '', groupType: group.groupType ?? 'test' }
}

function cancelEdit() {
  editing.value = false
  editingId.value = null
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
  const message = hasMembers
    ? `分组「${group.name}」包含 ${group.deviceCount} 个设备。删除分组会把设备移出分组（设备本身保留），确定删除吗？`
    : `确定删除分组「${group.name}」吗？`
  if (!window.confirm(message)) return
  try {
    await devicesPort.deleteGroup(group.id, true)
    notification.success('分组已删除')
    if (expandedId.value === group.id) expandedId.value = null
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
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}
.dg-modal {
  background: var(--background-primary, #fff);
  border-radius: var(--border-radius-lg, 12px);
  width: min(720px, 92vw);
  max-height: 82vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
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
  border-radius: 8px;
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
  width: 72px;
  font-size: 0.88rem;
  color: var(--text-secondary, #666);
}
.dg-form-row .form-input {
  flex: 1;
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
.dg-actions {
  display: flex;
  gap: 6px;
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
  border-radius: 12px;
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
