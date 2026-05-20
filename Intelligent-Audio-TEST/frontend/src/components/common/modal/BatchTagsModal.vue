<template>
  <div class="batch-tags-modal">
    <div class="form-row" v-if="action !== 'rename'">
      <span class="description">{{ headerDescription }}</span>
    </div>
    <div class="form-row" v-else>
      <span class="description">修改标签名称</span>
    </div>

    <div class="form-row">
      <label class="form-label">操作类型</label>
      <div class="radio-group">
        <label class="radio-label">
          <input type="radio" v-model="action" value="add" />
          <span>添加标签</span>
        </label>
        <label class="radio-label">
          <input type="radio" v-model="action" value="remove" />
          <span>移除标签</span>
        </label>
        <label class="radio-label">
          <input type="radio" v-model="action" value="rename" />
          <span>修改标签名字</span>
        </label>
      </div>
    </div>

    <div class="form-row" v-if="action === 'rename'">
      <label class="form-label">原标签</label>
      <select v-model="selectedOldTag" class="form-control">
        <option value="">请选择要修改的标签</option>
        <option v-for="tag in existingTags" :key="tag" :value="tag">{{ tag }}</option>
      </select>
      <div class="existing-tags" v-if="existingTags.length > 0">
        <span class="existing-tags-label">已有标签：</span>
        <span
          v-for="tag in paginatedExistingTags"
          :key="tag"
          class="tag-item existing-tag"
          :class="{ 'selected': selectedOldTag === tag }"
          @click="selectOldTag(tag)"
        >
          {{ tag }}
        </span>
        <div class="tag-pagination" v-if="totalRenameTagPages > 1">
          <button type="button" class="page-btn" :disabled="currentRenameTagPage === 1" @click="prevRenameTagPage">
            <i class="fas fa-chevron-left"></i>
          </button>
          <span class="page-info">{{ currentRenameTagPage }} / {{ totalRenameTagPages }}</span>
          <button type="button" class="page-btn" :disabled="currentRenameTagPage === totalRenameTagPages" @click="nextRenameTagPage">
            <i class="fas fa-chevron-right"></i>
          </button>
        </div>
      </div>
    </div>

    <div class="form-row" v-if="action === 'rename'">
      <label class="form-label">新标签名字</label>
      <input
        type="text"
        v-model="newTagName"
        class="form-control"
        placeholder="输入新的标签名称"
      />
    </div>

    <div class="form-row" v-if="action === 'add'">
      <div class="tag-input-wrapper">
          <input
            type="text"
            v-model="tagInput"
            class="form-control"
            placeholder="输入标签后按回车添加"
            @keydown.enter.prevent="addTagFromInput"
            @keydown.tab.prevent="addTagFromInput"
            style="width: 100%;"
          />
        </div>
      <div class="tags-container mt-2" v-if="selectedTags.length > 0">
        <span v-for="tag in selectedTags" :key="tag" class="tag-item">
          {{ tag }}
          <button type="button" class="tag-remove" @click="removeTag(tag)">
            <i class="fas fa-times"></i>
          </button>
        </span>
      </div>
      <div class="existing-tags mt-2" v-if="availableSuggestions.length > 0">
        <span class="existing-tags-label">已有标签（点击添加）：</span>
        <span
          v-for="tag in paginatedSuggestions"
          :key="tag"
          class="tag-item existing-tag"
          @click="addExistingTag(tag)"
        >
          {{ tag }}
        </span>
        <div class="tag-pagination" v-if="totalTagPages > 1">
          <button type="button" class="page-btn" :disabled="currentTagPage === 1" @click="prevTagPage">
            <i class="fas fa-chevron-left"></i>
          </button>
          <span class="page-info">{{ currentTagPage }} / {{ totalTagPages }}</span>
          <button type="button" class="page-btn" :disabled="currentTagPage === totalTagPages" @click="nextTagPage">
            <i class="fas fa-chevron-right"></i>
          </button>
        </div>
      </div>
    </div>

    <div class="form-row" v-if="action === 'remove'">
      <div class="tags-container" v-if="selectedTags.length > 0">
        <span class="existing-tags-label">将要移除的标签：</span>
        <span v-for="tag in selectedTags" :key="tag" class="tag-item tag-item-remove">
          {{ tag }}
          <button type="button" class="tag-remove" @click="removeTag(tag)">
            <i class="fas fa-times"></i>
          </button>
        </span>
      </div>
      <div class="existing-tags mt-2" v-if="existingTags.length > 0">
        <span class="existing-tags-label">已有标签（点击移除）：</span>
        <span
          v-for="tag in paginatedExistingTags"
          :key="tag"
          class="tag-item existing-tag"
          @click="addExistingTag(tag)"
        >
          {{ tag }}
        </span>
        <div class="tag-pagination" v-if="totalRenameTagPages > 1">
          <button type="button" class="page-btn" :disabled="currentRenameTagPage === 1" @click="prevRenameTagPage">
            <i class="fas fa-chevron-left"></i>
          </button>
          <span class="page-info">{{ currentRenameTagPage }} / {{ totalRenameTagPages }}</span>
          <button type="button" class="page-btn" :disabled="currentRenameTagPage === totalRenameTagPages" @click="nextRenameTagPage">
            <i class="fas fa-chevron-right"></i>
          </button>
        </div>
      </div>
    </div>

    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
      <button type="button" class="btn btn-primary" @click="handleConfirm" :disabled="!isValid">确定</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { testcasesApi } from '../../../utils/api'

interface Props {
  modalId: string
  title?: string
  caseCount?: number
}

interface Emits {
  (e: 'close'): void
  (e: 'confirm', data: { action: string; tags?: string[]; oldTagName?: string; newTagName?: string }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '批量管理标签',
  caseCount: 0
})

const emit = defineEmits<Emits>()

const action = ref<'add' | 'remove' | 'rename'>('add')
const tagInput = ref('')
const selectedTags = ref<string[]>([])
const existingTags = ref<string[]>([])
const selectedOldTag = ref('')
const newTagName = ref('')

const TAGS_PER_PAGE = 20
const currentTagPage = ref(1)
const currentRenameTagPage = ref(1)

const headerDescription = computed(() => {
  return `将为 ${props.caseCount} 个用例${actionText.value}标签`
})

const actionText = computed(() => {
  switch (action.value) {
    case 'add': return '添加'
    case 'remove': return '移除'
    case 'rename': return '修改'
    default: return ''
  }
})

const isValid = computed(() => {
  if (action.value === 'rename') {
    return selectedOldTag.value && newTagName.value.trim() && selectedOldTag.value !== newTagName.value.trim()
  }
  return selectedTags.value.length > 0
})

const availableSuggestions = computed(() => {
  return existingTags.value.filter(tag => !selectedTags.value.includes(tag))
})

const totalTagPages = computed(() => {
  return Math.ceil(availableSuggestions.value.length / TAGS_PER_PAGE)
})

const paginatedSuggestions = computed(() => {
  const start = (currentTagPage.value - 1) * TAGS_PER_PAGE
  const end = start + TAGS_PER_PAGE
  return availableSuggestions.value.slice(start, end)
})

const totalRenameTagPages = computed(() => {
  return Math.ceil(existingTags.value.length / TAGS_PER_PAGE)
})

const paginatedExistingTags = computed(() => {
  const start = (currentRenameTagPage.value - 1) * TAGS_PER_PAGE
  const end = start + TAGS_PER_PAGE
  return existingTags.value.slice(start, end)
})

async function loadExistingTags() {
  try {
    const result = await testcasesApi.getAll()
    const cases = (result as any).items || []
    const tagSet = new Set<string>()
    cases.forEach((tc: any) => {
      if (tc.tags && Array.isArray(tc.tags)) {
        tc.tags.forEach((tag: any) => {
          if (typeof tag === 'string') {
            tagSet.add(tag)
          } else if (tag && typeof tag === 'object' && 'name' in tag) {
            tagSet.add(tag.name)
          }
        })
      }
    })
    existingTags.value = Array.from(tagSet).sort()
  } catch (error) {
    console.error('加载已有标签失败:', error)
  }
}

function addTagFromInput() {
  const tag = tagInput.value.trim()
  if (tag && !selectedTags.value.includes(tag)) {
    selectedTags.value.push(tag)
    tagInput.value = ''
  }
}

function addExistingTag(tag: string) {
  if (!selectedTags.value.includes(tag)) {
    selectedTags.value.push(tag)
  }
}

function removeTag(tag: string) {
  const index = selectedTags.value.indexOf(tag)
  if (index > -1) {
    selectedTags.value.splice(index, 1)
  }
}

function selectOldTag(tag: string) {
  selectedOldTag.value = tag
}

function prevTagPage() {
  if (currentTagPage.value > 1) {
    currentTagPage.value--
  }
}

function nextTagPage() {
  if (currentTagPage.value < totalTagPages.value) {
    currentTagPage.value++
  }
}

function prevRenameTagPage() {
  if (currentRenameTagPage.value > 1) {
    currentRenameTagPage.value--
  }
}

function nextRenameTagPage() {
  if (currentRenameTagPage.value < totalRenameTagPages.value) {
    currentRenameTagPage.value++
  }
}

watch(action, () => {
  currentTagPage.value = 1
  currentRenameTagPage.value = 1
})

function handleConfirm() {
  if (action.value === 'rename') {
    emit('confirm', {
      action: action.value,
      oldTagName: selectedOldTag.value,
      newTagName: newTagName.value.trim()
    })
  } else {
    emit('confirm', {
      action: action.value,
      tags: [...selectedTags.value]
    })
  }
}

function handleCancel() {
  emit('cancel')
}

onMounted(() => {
  loadExistingTags()
})
</script>

<style scoped>
.batch-tags-modal {
  padding: 24px;
}

.form-row {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #495057;
  font-size: 14px;
}

.description {
  color: #6c757d;
  font-size: 14px;
}

.radio-group {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-weight: normal;
  color: #495057;
}

.radio-label input[type="radio"] {
  cursor: pointer;
  accent-color: #1677ff;
}

.form-control {
  padding: 10px 12px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  font-size: 14px;
  color: #495057;
  transition: border-color 0.2s, box-shadow 0.2s;
  width: 100%;
  box-sizing: border-box;
}

.form-control:focus {
  outline: none;
  border-color: #1677ff;
  box-shadow: 0 0 0 3px rgba(22, 119, 255, 0.1);
}

.form-control::placeholder {
  color: #adb5bd;
}

select.form-control {
  cursor: pointer;
  background: #fff;
}

.tag-input-wrapper {
  position: relative;
  width: 100%;
}

.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-item {
  background-color: #e3f2fd;
  color: #1976d2;
  padding: 4px 10px;
  border-radius: 16px;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.tag-item-remove {
  background-color: #ffebee;
  color: #c62828;
  border: 1px solid #ffcdd2;
}

.tag-item-remove .tag-remove {
  color: #c62828;
}

.tag-remove {
  background: none;
  border: none;
  color: #1976d2;
  cursor: pointer;
  font-size: 12px;
  padding: 0;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tag-remove:hover {
  color: #0d47a1;
}

.existing-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-top: 12px;
}

.existing-tags-label {
  font-size: 12px;
  color: #6c757d;
  margin-right: 4px;
}

.existing-tag {
  cursor: pointer;
}

.existing-tag:hover {
  background-color: #bbdefb;
  border-color: #1976d2;
}

.existing-tag.selected {
  background-color: #bbdefb;
  border-color: #1976d2;
}

.mt-2 {
  margin-top: 8px;
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
  font-weight: 500;
}

.btn-secondary {
  background: #f5f5f5;
  color: #333;
  border: 1px solid #ddd;
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

.tag-pagination {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  padding-left: 12px;
}

.page-btn {
  width: 28px;
  height: 28px;
  border: 1px solid #d9d9d9;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #666;
  font-size: 12px;
  transition: all 0.2s;
}

.page-btn:hover:not(:disabled) {
  border-color: #1677ff;
  color: #1677ff;
}

.page-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.page-info {
  font-size: 12px;
  color: #666;
  min-width: 50px;
  text-align: center;
}
</style>
