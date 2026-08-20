<template>
  <div class="batch-adjust-group-modal">
    <div class="modal-header">
      <h3>{{ title }}</h3>
      <p class="case-count">将为 {{ caseCount }} 个用例调整分组</p>
    </div>
    
    <div class="modal-body">
      <div class="form-group">
        <label>目标分组 <span class="required">*</span></label>
        <select v-model="selectedGroup" class="form-input custom-select" required @change="onGroupChange">
          <option value="">请选择分组</option>
          <option v-for="group in availableGroups" 
                  :key="group.id" 
                  :value="group.id">
            {{ group.name }}
          </option>
          <option value="__NEW_GROUP__">+ 新建分组</option>
        </select>
      </div>
      
      <div v-if="selectedGroup === '__NEW_GROUP__'" class="form-group new-group-input">
        <label>新分组名称 <span class="required">*</span></label>
        <input 
          type="text" 
          v-model="newGroupName" 
          class="form-input" 
          placeholder="输入新分组名称"
        />
      </div>
      
      <div class="form-group">
        <label>操作方式</label>
        <div class="radio-group">
          <label class="radio-label">
            <input type="radio" v-model="moveMode" value="move" />
            <span>移动到目标分组</span>
          </label>
          <label class="radio-label">
            <input type="radio" v-model="moveMode" value="copy" />
            <span>复制到目标分组（保留原用例）</span>
          </label>
        </div>
      </div>
    </div>
    
    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
      <button type="button" class="btn btn-primary" @click="handleConfirm" :disabled="!canConfirm">
        确定
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { testcasesApi } from '../../../utils/api'

interface GroupInfo {
  id: string
  name: string
}

interface Props {
  modalId: string
  title?: string
  caseCount?: number
  currentGroupId?: string
}

interface Emits {
  (e: 'close'): void
  (e: 'confirm', data: { groupId: string; isCopy: boolean }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '批量调整分组',
  caseCount: 0,
  currentGroupId: '',
  selectionMode: 'all'
})

const emit = defineEmits<Emits>()

const availableGroups = ref<GroupInfo[]>([])
const selectedGroup = ref('')
const newGroupName = ref('')
const moveMode = ref('move')
const isCreatingNewGroup = ref(false)

const canConfirm = computed(() => {
  if (selectedGroup.value === '__NEW_GROUP__') {
    return newGroupName.value.trim().length > 0
  }
  return selectedGroup.value !== ''
})

async function loadGroups() {
  try {
    const result = await testcasesApi.getGroups()
    const groups = (result as any).items || []
    availableGroups.value = groups.filter((g: any) => g.id !== props.currentGroupId)
  } catch (error) {
    console.error('加载分组列表失败:', error)
    availableGroups.value = []
  }
}

function onGroupChange() {
  isCreatingNewGroup.value = selectedGroup.value === '__NEW_GROUP__'
}

async function handleConfirm() {
  if (!canConfirm.value) {
    return
  }

  let targetGroupId = selectedGroup.value

  if (selectedGroup.value === '__NEW_GROUP__') {
    try {
      const result = await testcasesApi.createGroup({ name: newGroupName.value.trim() })
      targetGroupId = (result as any)?.id
      if (!targetGroupId) {
        alert('创建分组失败')
        return
      }
    } catch (error) {
      console.error('创建分组失败:', error)
      alert('创建分组失败')
      return
    }
  }

  emit('confirm', {
    groupId: targetGroupId,
    isCopy: moveMode.value === 'copy'
  })
}

function handleCancel() {
  emit('cancel')
}

onMounted(async () => {
  await loadGroups()
})
</script>

<style scoped>
.batch-adjust-group-modal {
  padding: 20px;
}

.modal-header {
  margin-bottom: 20px;
}

.modal-header h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: #333;
}

.case-count {
  margin: 0;
  color: #666;
  font-size: 14px;
}

.modal-body {
  max-height: 400px;
  overflow-y: auto;
}

.form-group {
  margin-bottom: 16px;
}

.form-group > label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: #333;
}

.required {
  color: #dc3545;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.form-input:focus {
  outline: none;
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.1);
}

.new-group-input {
  margin-top: 12px;
  padding: 12px;
  background: #f5f5f5;
  border-radius: 4px;
}

.radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.radio-label input[type="radio"] {
  width: 16px;
  height: 16px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #eee;
}

.btn {
  padding: 8px 20px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  border: none;
}

.btn-secondary {
  background: #f5f5f5;
  color: #333;
}

.btn-secondary:hover {
  background: #e8e8e8;
}

.btn-primary {
  background: #1677ff;
  color: #fff;
}

.btn-primary:hover {
  background: #4096ff;
}

.btn-primary:disabled {
  background: #ccc;
  cursor: not-allowed;
}
</style>
