<template>
  <div class="tg-category-sidebar">
    <div class="tg-card">
      <div class="tg-card-header">
        <h3 class="tg-card-title">
          <i class="fas fa-folder"></i>
          标签分类
          <span class="tg-total-count">共 {{ categoryTotal }} 个</span>
        </h3>
        <button class="tg-btn tg-btn-text tg-btn-primary" @click="emit('open-category-modal')">
          <i class="fas fa-plus tg-btn-icon"></i>
          新建
        </button>
      </div>
      <div class="tg-card-search">
        <div class="tg-search-box">
          <i class="fas fa-search tg-search-icon"></i>
          <input
            type="text"
            v-model="categorySearchKeyword"
            placeholder="搜索分类..."
            class="tg-search-input"
            @input="handleCategorySearchInput"
          />
        </div>
      </div>
      <div
        class="tg-card-body tg-category-scroll-container"
        ref="scrollContainer"
        @scroll="handleCategoryScroll"
      >
        <div class="tg-category-list">
          <div
            v-for="cat in categories"
            :key="cat.id"
            :class="['tg-category-item', { 'tg-active': selectedCategoryId === cat.id }]"
            @click="emit('select-category', cat.id)"
          >
            <div class="tg-category-info">
              <span class="tg-category-color" :style="{ backgroundColor: cat.color || 'var(--color-indigo-500)' }"></span>
              <span class="tg-category-name">{{ cat.name }}</span>
              <span class="tg-tag-count-badge">{{ cat.tagCount }}</span>
            </div>
            <div class="tg-category-actions" v-if="selectedCategoryId === cat.id">
              <button class="tg-btn tg-btn-text tg-btn-primary" @click.stop="emit('open-category-modal', cat)" title="编辑">
                <i class="fas fa-edit"></i>
              </button>
              <button class="tg-btn tg-btn-text tg-btn-danger" @click.stop="emit('confirm-delete-category', cat)" title="删除">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>

          <div
            :class="['tg-category-item', { 'tg-active': selectedCategoryId === null }]"
            @click="emit('select-category', null)"
          >
            <div class="tg-category-info">
              <span class="tg-category-color" :style="{ backgroundColor: 'var(--color-slate-400)' }"></span>
              <span class="tg-category-name">未分类</span>
              <span class="tg-tag-count-badge">{{ uncategorizedCount }}</span>
            </div>
          </div>

          <div v-if="categoryLoading" class="tg-loading-more-categories">
            <i class="fas fa-spinner fa-spin"></i>
            <span>加载中...</span>
          </div>

          <div v-if="!categoryHasMore && categories.length > 0 && !categoryLoading" class="tg-no-more-categories">
            <span>已加载全部</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<style scoped>

/* tg-category-actions - 自全局样式就近迁移 */
.tg-category-actions {
    display: flex;
    gap: var(--spacing-sm);
}

.tg-category-actions {
    display: flex ;
    gap: 8px ;
}

.tg-category-actions {
    display: flex;
    gap: 8px;
}
</style>

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

import { ref } from 'vue'
import type { TagCategory } from '@/domain/model/tag'

const props = defineProps<{
  categories: TagCategory[]
  selectedCategoryId: number | null
  categoryTotal: number
  categoryLoading: boolean
  categoryHasMore: boolean
  uncategorizedCount: number
}>()

const emit = defineEmits<{
  (e: 'select-category', id: number | null): void
  (e: 'open-category-modal', cat?: TagCategory): void
  (e: 'confirm-delete-category', cat: TagCategory): void
  (e: 'search-categories', keyword: string): void
  (e: 'category-scroll'): void
}>()

const categorySearchKeyword = ref('')
const scrollContainer = ref<HTMLElement | null>(null)

let categorySearchDebounceTimer: ReturnType<typeof setTimeout> | null = null

function handleCategorySearchInput() {
  if (categorySearchDebounceTimer) {
    clearTimeout(categorySearchDebounceTimer)
  }
  categorySearchDebounceTimer = setTimeout(() => {
    emit('search-categories', categorySearchKeyword.value)
  }, 300)
}

function handleCategoryScroll(event: Event) {
  const container = event.target as HTMLElement
  const { scrollTop, scrollHeight, clientHeight } = container
  if (scrollHeight - scrollTop - clientHeight < 50 && props.categoryHasMore && !props.categoryLoading) {
    emit('category-scroll')
  }
}
</script>
