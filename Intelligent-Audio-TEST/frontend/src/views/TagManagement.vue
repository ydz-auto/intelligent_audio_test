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
          <div 
            class="card-body category-scroll-container" 
            ref="categoryScrollContainer"
            @scroll="handleCategoryScroll"
          >
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
              
              <div v-if="categoryLoading" class="loading-more-categories">
                <i class="fas fa-spinner fa-spin"></i>
                <span>加载中...</span>
              </div>
              
              <div v-if="!categoryHasMore && categories.length > 0 && !categoryLoading" class="no-more-categories">
                <span>已加载全部</span>
              </div>
            </div>
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

    <Notification ref="notificationRef" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import api from '@/utils/api';
import type { TagCategory, TagItem } from '@/utils/api';
import Notification from '@/components/common/modal/Notification.vue';
import { useModalControl } from '@/composables/useModal';
import { MODAL_TYPES } from '@/shared/types';

const { open, close } = useModalControl();

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

const categoryPage = ref(1);
const categoryPageSize = ref(20);
const categoryTotal = ref(0);
const categoryLoading = ref(false);
const categoryHasMore = ref(true);
const categoryScrollContainer = ref<HTMLElement | null>(null);

const tagPage = ref(1);
const tagPageSize = ref(20);
const tagTotal = ref(0);
const tagLoading = ref(false);
const tagHasMore = ref(true);
const tagScrollContainer = ref<HTMLElement | null>(null);

const currentCategoryName = computed(() => {
  if (selectedCategoryId.value === null) return '未分类';
  const cat = allCategories.value.find(c => c.id === selectedCategoryId.value);
  return cat ? cat.name : '标签';
});

const uncategorizedCount = computed(() => {
  if (selectedCategoryId.value !== null) return 0;
  const categorizedCount = allCategories.value.reduce((sum, c) => sum + (c.tagCount || 0), 0);
  return Math.max(0, tagTotal.value - categorizedCount);
});

let categorySearchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;

function handleCategorySearchInput() {
  if (categorySearchDebounceTimer) {
    clearTimeout(categorySearchDebounceTimer);
  }
  categorySearchDebounceTimer = setTimeout(() => {
    resetCategoryList();
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

function resetCategoryList() {
  categories.value = [];
  categoryPage.value = 1;
  categoryHasMore.value = true;
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

async function loadCategories(append: boolean = false) {
  if (categoryLoading.value) return;
  
  categoryLoading.value = true;
  try {
    const params: any = {
      page: categoryPage.value,
      per_page: categoryPageSize.value
    };
    
    if (categorySearchKeyword.value.trim()) {
      params.keyword = categorySearchKeyword.value.trim();
    }
    
    const res = await api.tags.getCategories(params);
    const newCategories = res.items || [];
    
    if (append) {
      categories.value = [...categories.value, ...newCategories];
    } else {
      categories.value = newCategories;
    }
    
    categoryTotal.value = res.total || 0;
    categoryHasMore.value = categories.value.length < categoryTotal.value;
  } catch (e: any) {
    showNotification(e.message || '加载分类失败', 'error');
  } finally {
    categoryLoading.value = false;
  }
}

function handleCategoryScroll(event: Event) {
  const container = event.target as HTMLElement;
  const scrollTop = container.scrollTop;
  const scrollHeight = container.scrollHeight;
  const clientHeight = container.clientHeight;
  
  if (scrollHeight - scrollTop - clientHeight < 50 && categoryHasMore.value && !categoryLoading.value) {
    categoryPage.value++;
    loadCategories(true);
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

function openCategoryModal(cat?: TagCategory) {
  open(MODAL_TYPES.TAG_CATEGORY, {
    category: cat || null,
    sortOrder: allCategories.value.length + 1
  }).then((result: TagCategory) => {
    showNotification(cat ? '分类更新成功' : '分类创建成功', 'success');
    resetCategoryList();
    loadCategories();
    loadAllCategories();
  }).catch(() => {
    // 用户取消
  });
}

async function confirmDeleteCategory(cat: TagCategory) {
  if (cat.tagCount > 0) {
    showNotification(`该分类下还有 ${cat.tagCount} 个标签，请先移除或迁移标签`, 'warning');
    return;
  }
  
  open(MODAL_TYPES.DELETE_CONFIRM, {
    title: '删除分类',
    content: `确定删除分类「${cat.name}」吗？此操作不可恢复。`
  }).then(async () => {
    try {
      await api.tags.deleteCategory(cat.id);
      showNotification('分类删除成功', 'success');
      resetCategoryList();
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
  }).catch(() => {
    // 用户取消
  });
}

function openTagModal(tag?: TagItem) {
  open(MODAL_TYPES.TAG_EDIT, {
    tag: tag || null,
    categoryId: selectedCategoryId.value,
    categories: allCategories.value
  }).then((result: TagItem) => {
    showNotification(tag ? '标签更新成功' : '标签创建成功', 'success');
    resetTagList();
    loadTags();
    resetCategoryList();
    loadCategories();
    loadAllCategories();
  }).catch(() => {
    // 用户取消
  });
}

async function confirmDeleteTag(tag: TagItem) {
  open(MODAL_TYPES.DELETE_CONFIRM, {
    title: '删除标签',
    content: `确定删除标签「${tag.name}」吗？`
  }).then(async () => {
    try {
      await api.tags.deleteTag(tag.id);
      showNotification('标签删除成功', 'success');
      resetTagList();
      await loadTags();
      resetCategoryList();
      await loadCategories();
      await loadAllCategories();
    } catch (e: any) {
      showNotification(e.message || '删除失败', 'error');
    }
  }).catch(() => {
    // 用户取消
  });
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

.category-scroll-container {
  max-height: calc(100vh - 280px);
}

.tag-scroll-container {
  max-height: calc(100vh - 280px);
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

.loading-more-categories {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
  color: var(--text-muted, #94a3b8);
  font-size: 13px;
}

.loading-more-categories i {
  font-size: 14px;
}

.no-more-categories {
  text-align: center;
  padding: 12px;
  color: var(--text-muted, #94a3b8);
  font-size: 12px;
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
</style>
