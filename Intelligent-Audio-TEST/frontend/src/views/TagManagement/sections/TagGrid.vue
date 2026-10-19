<template>
  <div class="tg-tag-main-content">
    <div class="tg-card">
      <div class="tg-card-header">
        <h3 class="tg-card-title">
          <input
            type="checkbox"
            class="tg-select-all-checkbox"
            :checked="allVisibleSelected"
            :indeterminate.prop="someVisibleSelected"
            @change="toggleSelectAll"
            title="全选当前标签"
          >
          <i class="fas fa-tag"></i>
          {{ currentCategoryName }}
          <span class="tg-tag-total-count">共 {{ tagTotal }} 个标签</span>
        </h3>
        <div class="tg-card-actions">
          <div class="tg-search-box">
            <i class="fas fa-search tg-search-icon"></i>
            <input
              type="text"
              v-model="searchKeyword"
              placeholder="搜索标签..."
              class="tg-search-input"
              @input="handleSearchInput"
            />
          </div>
        </div>
      </div>
      <div
        class="tg-card-body tg-tag-scroll-container"
        ref="scrollContainer"
        @scroll="handleTagScroll"
      >
        <div v-if="tags.length === 0 && !tagLoading" class="tg-empty-state">
          <i class="fas fa-inbox"></i>
          <p>{{ searchKeyword ? '没有找到匹配的标签' : '暂无标签' }}</p>
          <button v-if="!searchKeyword" class="tg-btn tg-btn-primary" @click="emit('open-tag-modal')">
            <i class="fas fa-plus tg-btn-icon"></i>
            创建第一个标签
          </button>
        </div>

        <div v-else class="tg-tag-grid">
          <div
            v-for="tag in tags"
            :key="tag.id"
            :class="['tg-tag-card', { 'tg-tag-card--selected': isSelected(tag.id) }]"
          >
            <div class="tg-tag-color-bar" :style="{ backgroundColor: tag.color || 'var(--color-indigo-500)' }"></div>
            <div class="tg-tag-card-content">
              <div class="tg-tag-header">
                <div class="tg-tag-name-wrap">
                  <input
                    type="checkbox"
                    class="tg-tag-checkbox"
                    :checked="isSelected(tag.id)"
                    @change="toggleTag(tag)"
                    :title="`勾选「${tag.name}」用于批量操作`"
                  >
                  <span class="tg-tag-name">{{ tag.name }}</span>
                </div>
                <div class="tg-tag-actions">
                  <button class="tg-btn tg-btn-text tg-btn-primary" @click="emit('open-tag-modal', tag)" title="编辑">
                    <i class="fas fa-edit"></i>
                  </button>
                  <button class="tg-btn tg-btn-text tg-btn-danger" @click="emit('confirm-delete-tag', tag)" title="删除">
                    <i class="fas fa-trash"></i>
                  </button>
                </div>
              </div>
              <p v-if="tag.description" class="tg-tag-description">{{ tag.description }}</p>
              <div class="tg-tag-meta">
                <span v-if="tag.categoryName" class="tg-tag-category">
                  <i class="fas fa-folder"></i> {{ tag.categoryName }}
                </span>
              </div>
            </div>
          </div>

          <div v-if="tagLoading" class="tg-loading-more">
            <i class="fas fa-spinner fa-spin"></i>
            <span>加载中...</span>
          </div>

          <div v-if="!tagHasMore && tags.length > 0 && !tagLoading" class="tg-no-more-data">
            <span>已加载全部 {{ tagTotal }} 个标签</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/progress.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

import { ref, computed } from 'vue'
import type { TagItem } from '@/domain/model/tag'

const props = defineProps<{
  tags: TagItem[]
  tagTotal: number
  tagLoading: boolean
  tagHasMore: boolean
  currentCategoryName: string
  /** INT-739：批量改分类勾选集（当前已加载标签中勾选的 id 集合） */
  selectedTagIds?: number[]
}>()

const emit = defineEmits<{
  (e: 'open-tag-modal', tag?: TagItem): void
  (e: 'confirm-delete-tag', tag: TagItem): void
  (e: 'search-tags', keyword: string): void
  (e: 'tag-scroll'): void
  // INT-739：批量勾选
  (e: 'toggle-tag-selection', tag: TagItem): void
  (e: 'toggle-select-all'): void
}>()

const searchKeyword = ref('')
const scrollContainer = ref<HTMLElement | null>(null)

let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null

/** 当前标签是否已勾选 */
function isSelected(id: number): boolean {
  return (props.selectedTagIds || []).includes(id)
}

/** 全部可见（已加载）标签是否都已勾选 */
const allVisibleSelected = computed(() =>
  props.tags.length > 0 && props.tags.every(t => isSelected(t.id))
)

/** 部分勾选（半选态） */
const someVisibleSelected = computed(() =>
  props.tags.some(t => isSelected(t.id)) && !allVisibleSelected.value
)

function toggleTag(tag: TagItem) {
  emit('toggle-tag-selection', tag)
}

function toggleSelectAll() {
  emit('toggle-select-all')
}

function handleSearchInput() {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }
  searchDebounceTimer = setTimeout(() => {
    emit('search-tags', searchKeyword.value)
  }, 300)
}

function handleTagScroll(event: Event) {
  const container = event.target as HTMLElement
  const { scrollTop, scrollHeight, clientHeight } = container
  if (scrollHeight - scrollTop - clientHeight < 100 && props.tagHasMore && !props.tagLoading) {
    emit('tag-scroll')
  }
}
</script>
