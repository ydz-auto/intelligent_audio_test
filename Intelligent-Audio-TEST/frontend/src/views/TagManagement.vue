<template>
  <div class="tag-management-view">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-tags"></i>
          标签管理
        </h2>
        <p class="page-description">管理标签分类和标签，用于用例筛选和报告统计</p>
      </div>
      <div class="header-right">
        <button class="btn btn-primary" @click="openTagModal()">
          <i class="fas fa-plus btn-icon"></i>
          新建标签
        </button>
      </div>
    </div>

    <div class="tag-content-layout">
      <div class="category-sidebar">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">
              <i class="fas fa-folder"></i>
              标签分类
              <span class="total-count">共 {{ categoryTotal }} 个</span>
            </h3>
            <button class="btn btn-text btn-primary" @click="openCategoryModal()">
              <i class="fas fa-plus btn-icon"></i>
              新建
            </button>
          </div>
          <div class="card-search">
            <div class="search-box">
              <i class="fas fa-search search-icon"></i>
              <input 
                type="text" 
                v-model="categorySearchKeyword" 
                placeholder="搜索分类..." 
                class="search-input"
                @input="handleCategorySearchInput"
              />
            </div>
          </div>
          <div class="card-body">
            <div class="category-list">
              <div 
                v-for="cat in categories" 
                :key="cat.id"
                :class="['category-item', { active: selectedCategoryId === cat.id }]"
                @click="selectCategory(cat.id)"
              >
                <div class="category-info">
                  <span class="category-color" :style="{ backgroundColor: cat.color || '#6366f1' }"></span>
                  <span class="category-name">{{ cat.name }}</span>
                  <span class="tag-count-badge">{{ cat.tagCount }}</span>
                </div>
                <div class="category-actions" v-if="selectedCategoryId === cat.id">
                  <button class="btn btn-text btn-primary" @click.stop="openCategoryModal(cat)" title="编辑">
                    <i class="fas fa-edit"></i>
                  </button>
                  <button class="btn btn-text btn-danger" @click.stop="confirmDeleteCategory(cat)" title="删除">
                    <i class="fas fa-trash"></i>
                  </button>
                </div>
              </div>

              <div 
                :class="['category-item', { active: selectedCategoryId === null }]"
                @click="selectCategory(null)"
              >
                <div class="category-info">
                  <span class="category-color" style="backgroundColor: #94a3b8"></span>
                  <span class="category-name">未分类</span>
                  <span class="tag-count-badge">{{ uncategorizedCount }}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="card-footer" v-if="categoryTotalPages > 1">
            <PaginationComponent
              :current-page="categoryPage"
              :page-size="categoryPageSize"
              :total-items="categoryTotal"
              @prev-page="handleCategoryPrevPage"
              @next-page="handleCategoryNextPage"
              @go-to-page="handleCategoryGoToPage"
              @page-size-change="handleCategoryPageSizeChange"
            />
          </div>
        </div>
      </div>

      <div class="tag-main-content">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">
              <i class="fas fa-tag"></i>
              {{ currentCategoryName }}
              <span class="tag-total-count">共 {{ tagTotal }} 个标签</span>
            </h3>
            <div class="card-actions">
              <div class="search-box">
                <i class="fas fa-search search-icon"></i>
                <input 
                  type="text" 
                  v-model="searchKeyword" 
                  placeholder="搜索标签..." 
                  class="search-input"
                  @input="handleSearchInput"
                />
              </div>
            </div>
          </div>
          <div 
            class="card-body tag-scroll-container" 
            ref="tagScrollContainer"
            @scroll="handleTagScroll"
          >
            <div v-if="tags.length === 0 && !tagLoading" class="empty-state">
              <i class="fas fa-inbox"></i>
              <p>{{ searchKeyword ? '没有找到匹配的标签' : '暂无标签' }}</p>
              <button v-if="!searchKeyword" class="btn btn-primary" @click="openTagModal()">
                <i class="fas fa-plus btn-icon"></i>
                创建第一个标签
              </button>
            </div>
            
            <div v-else class="tag-grid">
              <div 
                v-for="tag in tags" 
                :key="tag.id"
                class="tag-card"
              >
                <div class="tag-color-bar" :style="{ backgroundColor: tag.color || '#6366f1' }"></div>
                <div class="tag-card-content">
                  <div class="tag-header">
                    <span class="tag-name">{{ tag.name }}</span>
                    <div class="tag-actions">
                      <button class="btn btn-text btn-primary" @click="openTagModal(tag)" title="编辑">
                        <i class="fas fa-edit"></i>
                      </button>
                      <button class="btn btn-text btn-danger" @click="confirmDeleteTag(tag)" title="删除">
                        <i class="fas fa-trash"></i>
                      </button>
                    </div>
                  </div>
                  <p v-if="tag.description" class="tag-description">{{ tag.description }}</p>
                  <div class="tag-meta">
                    <span v-if="tag.categoryName" class="tag-category">
                      <i class="fas fa-folder"></i> {{ tag.categoryName }}
                    </span>
                  </div>
                </div>
              </div>
              
              <div v-if="tagLoading" class="loading-more">
                <i class="fas fa-spinner fa-spin"></i>
                <span>加载中...</span>
              </div>
              
              <div v-if="!tagHasMore && tags.length > 0 && !tagLoading" class="no-more-data">
                <span>已加载全部 {{ tagTotal }} 个标签</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showCategoryModal" class="modal-overlay" @click.self="closeCategoryModal">
      <div class="modal">
        <div class="modal-header">
          <h3>
            <i class="fas fa-folder"></i>
            {{ editingCategory ? '编辑分类' : '新建分类' }}
          </h3>
          <button class="btn-close" @click="closeCategoryModal">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>分类名称 <span class="required">*</span></label>
            <input 
              type="text" 
              v-model="categoryForm.name" 
              placeholder="如：人数、场景、语种"
              :maxlength="50"
              class="form-input"
            />
            <span class="char-count">{{ categoryForm.name.length }}/50</span>
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea 
              v-model="categoryForm.description" 
              placeholder="分类描述"
              :maxlength="500"
              class="form-input"
            ></textarea>
            <span class="char-count">{{ categoryForm.description.length }}/500</span>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>颜色</label>
              <div class="color-picker">
                <input type="color" v-model="categoryForm.color" />
                <span class="color-value">{{ categoryForm.color }}</span>
              </div>
            </div>
            <div class="form-group">
              <label>排序</label>
              <input type="number" v-model="categoryForm.sortOrder" min="0" class="form-input" />
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeCategoryModal">取消</button>
          <button class="btn btn-primary" @click="saveCategory" :disabled="!isCategoryFormValid || saving">
            {{ saving ? '保存中...' : (editingCategory ? '保存' : '创建') }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="showTagModal" class="modal-overlay" @click.self="closeTagModal">
      <div class="modal">
        <div class="modal-header">
          <h3>
            <i class="fas fa-tag"></i>
            {{ editingTag ? '编辑标签' : '新建标签' }}
          </h3>
          <button class="btn-close" @click="closeTagModal">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>标签名称 <span class="required">*</span></label>
            <input 
              type="text" 
              v-model="tagForm.name" 
              placeholder="如：1人、2人、会议室"
              :maxlength="50"
              class="form-input"
            />
            <span class="char-count">{{ tagForm.name.length }}/50</span>
          </div>
          <div class="form-group">
            <label>所属分类</label>
            <select v-model="tagForm.categoryId" class="form-input">
              <option :value="null">未分类</option>
              <option v-for="cat in allCategories" :key="cat.id" :value="cat.id">
                {{ cat.name }}
              </option>
            </select>
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea 
              v-model="tagForm.description" 
              placeholder="标签描述"
              :maxlength="500"
              class="form-input"
            ></textarea>
            <span class="char-count">{{ tagForm.description.length }}/500</span>
          </div>
          <div class="form-group">
            <label>颜色</label>
            <div class="color-picker">
              <input type="color" v-model="tagForm.color" />
              <span class="color-value">{{ tagForm.color }}</span>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeTagModal">取消</button>
          <button class="btn btn-primary" @click="saveTag" :disabled="!isTagFormValid || saving">
            {{ saving ? '保存中...' : (editingTag ? '保存' : '创建') }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="showConfirmDialog" class="modal-overlay">
      <div class="confirm-dialog">
        <div class="confirm-icon">
          <i :class="confirmType === 'delete' ? 'fas fa-exclamation-triangle' : 'fas fa-question-circle'"></i>
        </div>
        <h3>{{ confirmTitle }}</h3>
        <p>{{ confirmMessage }}</p>
        <div class="confirm-actions">
          <button class="btn btn-secondary" @click="cancelConfirm">取消</button>
          <button class="btn" :class="confirmType === 'delete' ? 'btn-danger' : 'btn-primary'" @click="executeConfirm">
            确认
          </button>
        </div>
      </div>
    </div>

    <Notification ref="notificationRef" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue';
import api from '@/utils/api';
import type { TagCategory, TagItem } from '@/utils/api';
import Notification from '@/components/common/modal/Notification.vue';
import PaginationComponent from '@/components/common/PaginationComponent.vue';

const notificationRef = ref<InstanceType<typeof Notification> | null>(null);

function showNotification(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info') {
  notificationRef.value?.show(message, type);
}

const categories = ref<TagCategory[]>([]);
const allCategories = ref<TagCategory[]>([]);
const tags = ref<TagItem[]>([]);
const selectedCategoryId = ref<number | null>(null);
const searchKeyword = ref('');
const categorySearchKeyword = ref('');
const saving = ref(false);

const categoryPage = ref(1);
const categoryPageSize = ref(10);
const categoryTotal = ref(0);

const tagPage = ref(1);
const tagPageSize = ref(20);
const tagTotal = ref(0);
const tagLoading = ref(false);
const tagHasMore = ref(true);
const tagScrollContainer = ref<HTMLElement | null>(null);

const categoryTotalPages = computed(() => Math.ceil(categoryTotal.value / categoryPageSize.value) || 1);

const showCategoryModal = ref(false);
const editingCategory = ref<TagCategory | null>(null);
const categoryForm = ref({
  name: '',
  description: '',
  color: '#6366f1',
  sortOrder: 0
});

const showTagModal = ref(false);
const editingTag = ref<TagItem | null>(null);
const tagForm = ref({
  name: '',
  description: '',
  color: '#10b981',
  categoryId: null as number | null
});

const showConfirmDialog = ref(false);
const confirmTitle = ref('');
const confirmMessage = ref('');
const confirmCallback = ref<(() => void) | null>(null);
const confirmType = ref<'delete' | 'confirm'>('confirm');

const isCategoryFormValid = computed(() => {
  const name = categoryForm.value.name.trim();
  return name.length > 0 && name.length <= 50;
});

const isTagFormValid = computed(() => {
  const name = tagForm.value.name.trim();
  return name.length > 0 && name.length <= 50;
});

const currentCategoryName = computed(() => {
  if (selectedCategoryId.value === null) return '未分类';
  const cat = allCategories.value.find(c => c.id === selectedCategoryId.value);
  return cat ? cat.name : '标签';
});

const uncategorizedCount = computed(() => {
  return tagTotal.value - tags.value.filter(t => t.categoryId).length;
});

let categorySearchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;

function handleCategorySearchInput() {
  if (categorySearchDebounceTimer) {
    clearTimeout(categorySearchDebounceTimer);
  }
  categorySearchDebounceTimer = setTimeout(() => {
    categoryPage.value = 1;
    loadCategories();
  }, 300);
}

function handleSearchInput() {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer);
  }
  searchDebounceTimer = setTimeout(() => {
    resetTagList();
    loadTags();
  }, 300);
}

function resetTagList() {
  tags.value = [];
  tagPage.value = 1;
  tagHasMore.value = true;
}

async function loadAllCategories() {
  try {
    const res = await api.tags.getCategories({ page: 1, per_page: 1000 });
    allCategories.value = res.items || [];
  } catch (e: any) {
    console.error('加载全部分类失败:', e);
  }
}

async function loadCategories() {
  try {
    const params: any = {
      page: categoryPage.value,
      per_page: categoryPageSize.value
    };
    
    if (categorySearchKeyword.value.trim()) {
      params.keyword = categorySearchKeyword.value.trim();
    }
    
    const res = await api.tags.getCategories(params);
    categories.value = res.items || [];
    categoryTotal.value = res.total || 0;
  } catch (e: any) {
    showNotification(e.message || '加载分类失败', 'error');
  }
}

async function loadTags(append: boolean = false) {
  if (tagLoading.value) return;
  
  tagLoading.value = true;
  try {
    const params: any = {
      page: tagPage.value,
      per_page: tagPageSize.value
    };
    
    if (selectedCategoryId.value !== null) {
      params.category_id = selectedCategoryId.value;
    }
    
    if (searchKeyword.value.trim()) {
      params.keyword = searchKeyword.value.trim();
    }
    
    const res = await api.tags.getTags(params);
    const newTags = res.items || [];
    
    if (append) {
      tags.value = [...tags.value, ...newTags];
    } else {
      tags.value = newTags;
    }
    
    tagTotal.value = res.total || 0;
    tagHasMore.value = tags.value.length < tagTotal.value;
  } catch (e: any) {
    showNotification(e.message || '加载标签失败', 'error');
  } finally {
    tagLoading.value = false;
  }
}

function handleTagScroll(event: Event) {
  const container = event.target as HTMLElement;
  const scrollTop = container.scrollTop;
  const scrollHeight = container.scrollHeight;
  const clientHeight = container.clientHeight;
  
  if (scrollHeight - scrollTop - clientHeight < 100 && tagHasMore.value && !tagLoading.value) {
    tagPage.value++;
    loadTags(true);
  }
}

function selectCategory(id: number | null) {
  selectedCategoryId.value = id;
  resetTagList();
  loadTags();
}

function handleCategoryPrevPage() {
  if (categoryPage.value > 1) {
    categoryPage.value--;
    loadCategories();
  }
}

function handleCategoryNextPage() {
  if (categoryPage.value < categoryTotalPages.value) {
    categoryPage.value++;
    loadCategories();
  }
}

function handleCategoryGoToPage(page: number) {
  categoryPage.value = page;
  loadCategories();
}

function handleCategoryPageSizeChange(size: number) {
  categoryPageSize.value = size;
  categoryPage.value = 1;
  loadCategories();
}

function openCategoryModal(cat?: TagCategory) {
  editingCategory.value = cat || null;
  if (cat) {
    categoryForm.value = {
      name: cat.name,
      description: cat.description || '',
      color: cat.color || '#6366f1',
      sortOrder: cat.sortOrder || 0
    };
  } else {
    categoryForm.value = {
      name: '',
      description: '',
      color: '#6366f1',
      sortOrder: allCategories.value.length + 1
    };
  }
  showCategoryModal.value = true;
}

function closeCategoryModal() {
  showCategoryModal.value = false;
  editingCategory.value = null;
}

async function saveCategory() {
  if (!isCategoryFormValid.value || saving.value) return;
  
  saving.value = true;
  try {
    const data = {
      name: categoryForm.value.name.trim(),
      description: categoryForm.value.description.trim(),
      color: categoryForm.value.color,
      sortOrder: categoryForm.value.sortOrder
    };
    
    if (editingCategory.value) {
      await api.tags.updateCategory(editingCategory.value.id, data);
      showNotification('分类更新成功', 'success');
    } else {
      await api.tags.createCategory(data);
      showNotification('分类创建成功', 'success');
    }
    
    await loadCategories();
    await loadAllCategories();
    closeCategoryModal();
  } catch (e: any) {
    showNotification(e.message || '保存失败', 'error');
  } finally {
    saving.value = false;
  }
}

function confirmDeleteCategory(cat: TagCategory) {
  if (cat.tagCount > 0) {
    showNotification(`该分类下还有 ${cat.tagCount} 个标签，请先移除或迁移标签`, 'warning');
    return;
  }
  
  confirmTitle.value = '删除分类';
  confirmMessage.value = `确定删除分类「${cat.name}」吗？此操作不可恢复。`;
  confirmType.value = 'delete';
  confirmCallback.value = async () => {
    try {
      await api.tags.deleteCategory(cat.id);
      showNotification('分类删除成功', 'success');
      await loadCategories();
      await loadAllCategories();
      if (selectedCategoryId.value === cat.id) {
        selectedCategoryId.value = null;
        resetTagList();
        loadTags();
      }
    } catch (e: any) {
      showNotification(e.message || '删除失败', 'error');
    }
  };
  showConfirmDialog.value = true;
}

function openTagModal(tag?: TagItem) {
  editingTag.value = tag || null;
  if (tag) {
    tagForm.value = {
      name: tag.name,
      description: tag.description || '',
      color: tag.color || '#10b981',
      categoryId: tag.categoryId || null
    };
  } else {
    tagForm.value = {
      name: '',
      description: '',
      color: '#10b981',
      categoryId: selectedCategoryId.value
    };
  }
  showTagModal.value = true;
}

function closeTagModal() {
  showTagModal.value = false;
  editingTag.value = null;
}

async function saveTag() {
  if (!isTagFormValid.value || saving.value) return;
  
  saving.value = true;
  try {
    const data = {
      name: tagForm.value.name.trim(),
      description: tagForm.value.description.trim(),
      color: tagForm.value.color,
      categoryId: tagForm.value.categoryId
    };
    
    if (editingTag.value) {
      await api.tags.updateTag(editingTag.value.id, data);
      showNotification('标签更新成功', 'success');
    } else {
      await api.tags.createTag(data);
      showNotification('标签创建成功', 'success');
    }
    
    resetTagList();
    await loadTags();
    await loadCategories();
    await loadAllCategories();
    closeTagModal();
  } catch (e: any) {
    showNotification(e.message || '保存失败', 'error');
  } finally {
    saving.value = false;
  }
}

function confirmDeleteTag(tag: TagItem) {
  confirmTitle.value = '删除标签';
  confirmMessage.value = `确定删除标签「${tag.name}」吗？`;
  confirmType.value = 'delete';
  confirmCallback.value = async () => {
    try {
      await api.tags.deleteTag(tag.id);
      showNotification('标签删除成功', 'success');
      resetTagList();
      await loadTags();
      await loadCategories();
      await loadAllCategories();
    } catch (e: any) {
      showNotification(e.message || '删除失败', 'error');
    }
  };
  showConfirmDialog.value = true;
}

function cancelConfirm() {
  showConfirmDialog.value = false;
  confirmCallback.value = null;
}

async function executeConfirm() {
  if (confirmCallback.value) {
    await confirmCallback.value();
  }
  cancelConfirm();
}

onMounted(() => {
  loadCategories();
  loadAllCategories();
  loadTags();
});
</script>

<style scoped>
.tag-management-view {
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-color, #f5f7fa);
  min-height: 100vh;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
}

.page-title i {
  font-size: 24px;
}

.page-description {
  margin: 0;
  color: var(--text-secondary, #64748b);
  font-size: 14px;
}

.header-right {
  display: flex;
  gap: 12px;
}

.tag-content-layout {
  display: flex;
  gap: 20px;
  flex: 1;
  min-height: 0;
}

.category-sidebar {
  width: 320px;
  flex-shrink: 0;
}

.tag-main-content {
  flex: 1;
  min-width: 0;
}

.card {
  background: var(--card-bg, #fff);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  height: 100%;
}

.card-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color, #e2e8f0);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary, #334155);
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.card-title i {
  color: var(--primary-color, #6366f1);
}

.total-count,
.tag-total-count {
  font-size: 13px;
  color: var(--text-muted, #94a3b8);
  font-weight: 400;
  margin-left: 8px;
}

.card-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.card-search {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color, #e2e8f0);
}

.card-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.tag-scroll-container {
  max-height: calc(100vh - 280px);
}

.card-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border-color, #e2e8f0);
  background: var(--card-footer-bg, #f8fafc);
}

.category-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.category-item {
  padding: 12px 14px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.category-item:hover {
  background: var(--hover-bg, #f1f5f9);
}

.category-item.active {
  background: var(--active-bg, #eef2ff);
  border-color: var(--primary-color, #6366f1);
}

.category-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.category-color {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  flex-shrink: 0;
}

.category-name {
  font-weight: 500;
  color: var(--text-primary, #334155);
  font-size: 14px;
}

.tag-count-badge {
  font-size: 11px;
  color: var(--text-muted, #64748b);
  background: var(--badge-bg, #f1f5f9);
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}

.category-actions {
  display: flex;
  gap: 4px;
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
}

.search-icon {
  position: absolute;
  left: 12px;
  font-size: 14px;
  color: var(--text-muted, #94a3b8);
}

.search-input {
  padding: 8px 12px 8px 36px;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 6px;
  font-size: 14px;
  width: 100%;
  transition: all 0.2s;
  background: var(--input-bg, #fff);
}

.search-input:focus {
  outline: none;
  border-color: var(--primary-color, #6366f1);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.empty-state {
  text-align: center;
  color: var(--text-muted, #94a3b8);
  padding: 60px 20px;
}

.empty-state i {
  font-size: 48px;
  margin-bottom: 16px;
  display: block;
  color: var(--text-muted, #cbd5e1);
}

.empty-state p {
  margin-bottom: 20px;
  font-size: 15px;
}

.tag-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.tag-card {
  background: var(--card-bg, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.2s;
}

.tag-card:hover {
  border-color: var(--border-hover, #cbd5e1);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.tag-color-bar {
  height: 4px;
}

.tag-card-content {
  padding: 14px;
}

.tag-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.tag-name {
  font-weight: 600;
  color: var(--text-primary, #1e293b);
  font-size: 14px;
}

.tag-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.tag-card:hover .tag-actions {
  opacity: 1;
}

.tag-description {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  margin: 0 0 10px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.tag-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
}

.tag-category {
  display: flex;
  align-items: center;
  gap: 4px;
}

.loading-more {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px;
  color: var(--text-muted, #94a3b8);
  font-size: 14px;
}

.loading-more i {
  font-size: 16px;
}

.no-more-data {
  grid-column: 1 / -1;
  text-align: center;
  padding: 16px;
  color: var(--text-muted, #94a3b8);
  font-size: 13px;
}

.btn {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn-icon {
  font-size: 12px;
}

.btn-primary {
  background: var(--primary-color, #6366f1);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover, #4f46e5);
}

.btn-primary:disabled {
  background: var(--disabled-bg, #cbd5e1);
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--btn-secondary-bg, #f1f5f9);
  color: var(--text-secondary, #475569);
  border: 1px solid var(--border-color, #e2e8f0);
}

.btn-secondary:hover {
  background: var(--btn-secondary-hover, #e2e8f0);
}

.btn-danger {
  background: var(--danger-color, #ef4444);
  color: #fff;
}

.btn-danger:hover {
  background: var(--danger-hover, #dc2626);
}

.btn-text {
  background: transparent;
  padding: 4px 8px;
}

.btn-text.btn-primary {
  color: var(--primary-color, #6366f1);
}

.btn-text.btn-primary:hover {
  background: var(--primary-light, rgba(99, 102, 241, 0.1));
}

.btn-text.btn-danger {
  color: var(--danger-color, #ef4444);
}

.btn-text.btn-danger:hover {
  background: var(--danger-light, rgba(239, 68, 68, 0.1));
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(15, 23, 42, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal {
  background: var(--card-bg, #fff);
  border-radius: 12px;
  width: 500px;
  max-width: 90%;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
}

.modal-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color, #e2e8f0);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary, #1e293b);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.modal-header h3 i {
  color: var(--primary-color, #6366f1);
}

.btn-close {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-muted, #94a3b8);
  width: 32px;
  height: 32px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.btn-close:hover {
  color: var(--text-secondary, #475569);
  background: var(--hover-bg, #f1f5f9);
}

.modal-body {
  padding: 20px;
}

.modal-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--border-color, #e2e8f0);
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  background: var(--modal-footer-bg, #f8fafc);
}

.form-group {
  margin-bottom: 16px;
  position: relative;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: var(--text-primary, #334155);
  font-size: 14px;
}

.required {
  color: var(--danger-color, #ef4444);
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
  transition: all 0.2s;
  background: var(--input-bg, #fff);
}

.form-input:focus {
  outline: none;
  border-color: var(--primary-color, #6366f1);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

textarea.form-input {
  min-height: 80px;
  resize: vertical;
}

.char-count {
  position: absolute;
  right: 0;
  bottom: -16px;
  font-size: 11px;
  color: var(--text-muted, #94a3b8);
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-row .form-group {
  flex: 1;
}

.color-picker {
  display: flex;
  align-items: center;
  gap: 12px;
}

input[type="color"] {
  height: 36px;
  padding: 2px;
  width: 50px;
  cursor: pointer;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 6px;
}

.color-value {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  font-family: monospace;
}

.confirm-dialog {
  background: var(--card-bg, #fff);
  border-radius: 12px;
  width: 400px;
  max-width: 90%;
  padding: 24px;
  text-align: center;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
}

.confirm-icon {
  margin-bottom: 16px;
}

.confirm-icon i {
  font-size: 48px;
  color: var(--warning-color, #f59e0b);
}

.confirm-dialog h3 {
  margin: 0 0 12px;
  font-size: 16px;
  color: var(--text-primary, #1e293b);
}

.confirm-dialog p {
  margin: 0 0 20px;
  color: var(--text-secondary, #64748b);
  font-size: 14px;
  line-height: 1.6;
}

.confirm-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}
</style>
