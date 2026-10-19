<template>
  <div class="tg-tag-management-view">
    <div class="tg-page-header">
      <div class="tg-header-left">
        <h2 class="tg-page-title">
          <i class="fas fa-tags"></i>
          标签管理
        </h2>
        <p class="tg-page-description">管理标签分类和标签，用于用例筛选和报告统计</p>
      </div>
      <div class="tg-header-right">
        <button class="tg-btn tg-btn-primary" @click="openTagModal()">
          <i class="fas fa-plus tg-btn-icon"></i>
          新建标签
        </button>
      </div>
    </div>

    <div class="tg-tag-content-layout">
      <CategorySidebar
        :categories="categories"
        :selected-category-id="selectedCategoryId"
        :category-total="categoryTotal"
        :category-loading="categoryLoading"
        :category-has-more="categoryHasMore"
        :uncategorized-count="uncategorizedCount"
        @select-category="selectCategory"
        @open-category-modal="openCategoryModal"
        @confirm-delete-category="confirmDeleteCategory"
        @search-categories="handleCategorySearch"
        @category-scroll="onCategoryScroll"
      />

      <TagGrid
        :tags="tags"
        :tag-total="tagTotal"
        :tag-loading="tagLoading"
        :tag-has-more="tagHasMore"
        :current-category-name="currentCategoryName"
        :selected-tag-ids="selectedTagIds"
        @open-tag-modal="openTagModal"
        @confirm-delete-tag="confirmDeleteTag"
        @search-tags="handleTagSearch"
        @tag-scroll="onTagScroll"
        @toggle-tag-selection="toggleTagSelection"
        @toggle-select-all="toggleSelectAllVisible"
      />
    </div>

    <!-- INT-739：批量改分类浮动条（勾选 ≥1 标签出现，只作用于当前勾选集合） -->
    <Transition name="tg-bulk-fade">
      <div v-if="selectedTagIds.length > 0" class="tg-bulk-bar" aria-live="polite">
        <span class="tg-bulk-count">{{ selectedTagIds.length }} 个标签已选择</span>
        <button class="tg-btn tg-btn-primary" @click="openBatchCategoryModal">
          <i class="fas fa-folder tg-btn-icon"></i>
          批量改分类
        </button>
        <button class="tg-btn tg-btn-text tg-bulk-clear" @click="clearTagSelection" title="清除选择 (Esc)">
          <i class="fas fa-times"></i>
        </button>
      </div>
    </Transition>

    <Notification ref="notificationRef" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { tagsPort } from '@/composables/shared/tagsPort';
import type { TagCategory, TagItem } from '@/domain/model/tag';
import Notification from '@/components/common/modal/Notification.vue';
import { useModalControl } from '@/composables';
import { MODAL_TYPES } from '@/composables/modal/constants';
import CategorySidebar from './sections/CategorySidebar.vue';
import TagGrid from './sections/TagGrid.vue';

const { open, close } = useModalControl();

const notificationRef = ref<InstanceType<typeof Notification> | null>(null);

function showNotification(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info') {
  notificationRef.value?.show(message, type);
}

const categories = ref<TagCategory[]>([]);
const allCategories = ref<TagCategory[]>([]);
const tags = ref<TagItem[]>([]);
const selectedCategoryId = ref<number | null>(null);

const categoryPage = ref(1);
const categoryPageSize = ref(20);
const categoryTotal = ref(0);
const categoryLoading = ref(false);
const categoryHasMore = ref(true);

const tagPage = ref(1);
const tagPageSize = ref(20);
const tagTotal = ref(0);
const tagLoading = ref(false);
const tagHasMore = ref(true);
const totalTagCount = ref(0);

const currentCategoryName = computed(() => {
  if (selectedCategoryId.value === null) return '未分类';
  const cat = allCategories.value.find(c => c.id === selectedCategoryId.value);
  return cat ? cat.name : '标签';
});

const uncategorizedCount = computed(() => {
  const categorizedCount = allCategories.value.reduce((sum, c) => sum + (c.tagCount || 0), 0);
  return Math.max(0, totalTagCount.value - categorizedCount);
});

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
    const res = await tagsPort.getCategories({ page: 1, perPage: 1000 });
    allCategories.value = res.items || [];
  } catch (e: any) {
    // INT-295：与 loadCategories/loadTags 一致，失败走 notification 提示（不再静默 console）
    showNotification(e.message || '加载全部分类失败', 'error');
  }
}

async function loadCategories(append: boolean = false) {
  if (categoryLoading.value) return;

  categoryLoading.value = true;
  try {
    // Domain 查询参数为 camelCase（TagListQuery），API 层负责转 snake_case
    const params: any = {
      page: categoryPage.value,
      perPage: categoryPageSize.value
    };

    const sidebarKeyword = (categorySearchKeywordHolder.value || '').trim();
    if (sidebarKeyword) {
      params.keyword = sidebarKeyword;
    }

    const res = await tagsPort.getCategories(params);
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

// 子组件搜索关键词的临时存储
const categorySearchKeywordHolder = ref('');
const tagSearchKeywordHolder = ref('');

function handleCategorySearch(keyword: string) {
  categorySearchKeywordHolder.value = keyword;
  resetCategoryList();
  loadCategories();
}

function handleTagSearch(keyword: string) {
  tagSearchKeywordHolder.value = keyword;
  resetTagList();
  loadTags();
}

function onCategoryScroll() {
  if (categoryHasMore.value && !categoryLoading.value) {
    categoryPage.value++;
    loadCategories(true);
  }
}

async function loadTags(append: boolean = false) {
  if (tagLoading.value) return;

  tagLoading.value = true;
  try {
    // Domain 查询参数为 camelCase（TagListQuery），API 层负责转 snake_case
    const params: any = {
      page: tagPage.value,
      perPage: tagPageSize.value
    };

    if (selectedCategoryId.value !== null) {
      params.categoryId = selectedCategoryId.value;
    }

    const tagKeyword = (tagSearchKeywordHolder.value || '').trim();
    if (tagKeyword) {
      params.keyword = tagKeyword;
    }

    const res = await tagsPort.getTags(params);
    const newTags = res.items || [];

    if (append) {
      tags.value = [...tags.value, ...newTags];
    } else {
      tags.value = newTags;
    }

    tagTotal.value = res.total || 0;
    if (selectedCategoryId.value === null) {
      totalTagCount.value = tagTotal.value;
    }
    tagHasMore.value = tags.value.length < tagTotal.value;
  } catch (e: any) {
    showNotification(e.message || '加载标签失败', 'error');
  } finally {
    tagLoading.value = false;
  }
}

function onTagScroll() {
  if (tagHasMore.value && !tagLoading.value) {
    tagPage.value++;
    loadTags(true);
  }
}

function selectCategory(id: number | null) {
  selectedCategoryId.value = id;
  resetTagList();
  loadTags();
}

// ===== INT-739：批量改分类（勾选集合只作用于当前勾选，对齐用例域「只认勾选」口径）=====
const selectedTagIds = ref<number[]>([]);

function toggleTagSelection(tag: TagItem) {
  const idx = selectedTagIds.value.indexOf(tag.id);
  if (idx >= 0) {
    selectedTagIds.value.splice(idx, 1);
  } else {
    selectedTagIds.value.push(tag.id);
  }
}

/** 全选当前已加载标签（半选态由 TagGrid computed 呈现，未加载项经滚动追加后再勾选） */
function toggleSelectAllVisible() {
  if (tags.value.length === 0) return;
  const allSelected = tags.value.every(t => selectedTagIds.value.includes(t.id));
  if (allSelected) {
    // 全选态再点 = 全量移除当前已加载
    selectedTagIds.value = selectedTagIds.value.filter(id => !tags.value.some(t => t.id === id));
  } else {
    const existing = new Set(selectedTagIds.value);
    tags.value.forEach(t => existing.add(t.id));
    selectedTagIds.value = Array.from(existing);
  }
}

function clearTagSelection() {
  selectedTagIds.value = [];
}

/** 批量改分类：目标分类选择（null=未分类）→ PUT /tags/batch-category */
function openBatchCategoryModal() {
  open(MODAL_TYPES.BATCH_TAG_CATEGORY, {
    tagCount: selectedTagIds.value.length,
    categories: allCategories.value,
  }).then(async (result: { categoryId: number | null }) => {
    try {
      await tagsPort.batchUpdateCategory(selectedTagIds.value, result.categoryId);
      showNotification('批量改分类成功', 'success');
      clearTagSelection();
      resetTagList();
      await loadTags();
      resetCategoryList();
      await loadCategories();
      await loadAllCategories();
    } catch (e: any) {
      showNotification(e.message || '批量改分类失败', 'error');
    }
  }).catch(() => {
    // 用户取消
  });
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
      await tagsPort.deleteCategory(cat.id);
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
      await tagsPort.deleteTag(tag.id);
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

<!-- INT-277：页面样式走 tg- 前缀命名空间隔离（同 INT-250 pt- 方案），禁止裸 .btn/.card/.page-header 等全站通用类名全局注入污染其他页面 -->
<style src="./tagManagement.css"></style>
